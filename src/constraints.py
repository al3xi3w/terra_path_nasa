"""Evidence-based rotation constraints: allowed / prohibited / unknown, never inferred.

Builds, from verified local NASA/FAO data plus explicit farmer declarations, the gates the
deterministic optimizer needs. Unknown is never converted to allowed: any unknown in a
non-excluded crop-season or transition makes the system abstain and list what is missing.
"""
import json
from pathlib import Path
import pandas as pd
from .pipeline import ROOT, digest
from .store import DataStore
from .parcel_scenarios import validate_input, day, seasonal_climate
from .rotation_optimizer import optimize
from .water_requirement import crop_requirement, irrigation_bounds

ALLOWED, PROHIBITED, UNKNOWN = 'allowed', 'prohibited', 'unknown'
GATES = ['cycle', 'calendar', 'climate', 'soil_nutrients', 'water']
FARMER_FIELDS = {'country_iso2', 'water_available', 'irrigation_required', 'cycle', 'soil_nutrients',
                 'transitions', 'history_review', 'fao56', 'irrigation_efficiency', 'initial_soil_water_mm'}


def evidence(source, reason, *, file=None, sha256=None, variable=None, unit=None, period=None, location=None, value=None):
    return dict(source=source, file=file, sha256=sha256, variable=variable, unit=unit,
                period=period, location=location, value=value, reason=reason)


def state(value, items, needs=None):
    return dict(state=value, evidence=items, needs=needs or [])


def combine(parts):
    """Prohibited dominates; any unknown keeps the whole gate unknown."""
    states = [p['state'] for p in parts]
    value = PROHIBITED if PROHIBITED in states else (UNKNOWN if UNKNOWN in states else ALLOWED)
    return state(value, [e for p in parts for e in p['evidence']], [n for p in parts for n in p['needs']])


def declared(value, unit=None):
    """Explicit farmer/agronomist statement with provenance; never filled in."""
    if not isinstance(value, dict) or not value.get('provenance'):return None
    if unit is not None:
        v = value.get('value')
        if value.get('unit') != unit or isinstance(v, bool) or not isinstance(v, (int, float)) or v < 0:return None
        return v
    return value['allowed'] if type(value.get('allowed')) is bool else None


# ---------- crop name correspondence ----------

def crop_name_map(root=ROOT):
    """EcoCrop scientificname ↔ FAO Crop Calendar crop_scientific_name, exact string only.

    No authority stripping, synonyms, parents or families: 'Zea mays L.' is not 'Zea mays'.
    Names matching several FAO ids, or FAO ids duplicated in the catalog, stay unmapped.
    """
    store = DataStore(root)
    eco = store.verified_table('data/processed/ecocrop_validated.parquet')
    fao = store.verified_table('data/processed/agronomy-crops.parquet')
    fao = fao.assign(sci=fao.crop_scientific_name.astype('string').str.strip())
    fao = fao[fao.sci.notna() & fao.sci.ne('')]
    duplicated_ids = set(fao.id[fao.id.duplicated(keep=False)])
    names = set(eco.scientificname.astype(str).str.strip())
    mapped, ambiguous = {}, {}
    for sci, rows in fao[fao.sci.isin(names)].groupby('sci'):
        ids = sorted(set(rows.id))
        if len(ids) != 1 or ids[0] in duplicated_ids:ambiguous[sci] = ids;continue
        r = rows.iloc[0]
        mapped[sci] = dict(fao_crop_id=str(r.id), fao_name=str(r['name']), match='exact scientific name string')
    return dict(mapped=mapped, ambiguous=ambiguous,
                files={'ecocrop': ('data/processed/ecocrop_validated.parquet', eco.attrs['sha256']),
                       'fao_crops': ('data/processed/agronomy-crops.parquet', fao.attrs['sha256'])},
                rule='exact string equality; FAO crop_family is a use group, not a taxonomic family, and is not used')


# ---------- individual constraints ----------

def _ecocrop(crop, root):
    ref = DataStore(root).crop_reference('ecocrop', crop)
    return (ref.iloc[0], ref.attrs['fieldshift_lineage'][0]) if len(ref) == 1 else (None, None)


def _eco_ev(lineage, variable, unit, value, reason):
    return evidence('FAO EcoCrop', reason, file='data/processed/ecocrop_validated.parquet',
                    sha256=lineage.get('output_sha256'), variable=variable, unit=unit, value=value)


def cycle_constraint(row, lineage, season, declared_cycle=None):
    """Season length vs EcoCrop crop-cycle range (gmin–gmax days).

    < gmin: prohibited (shortest documented cycle does not fit); ≥ gmax: allowed;
    in between: unknown unless the farmer declares the cultivar cycle.
    """
    length = (day(season['end']) - day(season['start'])).days + 1
    period = f"{season['start']}/{season['end']}"
    if row is None or not (bool(row.get('gmin_valid')) and bool(row.get('gmax_valid'))):
        return state(UNKNOWN, [], ['valid EcoCrop crop-cycle range (gmin/gmax) or declared cultivar cycle']), None
    lo, hi = float(row.gmin_usable), float(row.gmax_usable)
    ev = [_eco_ev(lineage, 'gmin/gmax', 'day', [lo, hi], f'season length {length} days ({period})')]
    if length < lo:return state(PROHIBITED, ev), hi
    if declared_cycle is not None:
        ev.append(evidence('farmer declaration', 'declared cultivar cycle', variable='cycle', unit='day', value=declared_cycle))
        if not lo <= declared_cycle <= hi:
            return state(UNKNOWN, ev, ['review: declared cycle outside EcoCrop range']), None
        return state(ALLOWED if declared_cycle <= length else PROHIBITED, ev), declared_cycle
    if length >= hi:return state(ALLOWED, ev), hi
    return state(UNKNOWN, ev, ['declared cultivar cycle (days): season length is between EcoCrop gmin and gmax']), None


def temperature_constraint(row, lineage, parcel, season, root):
    """NASA POWER season mean temperature vs EcoCrop absolute tmin–tmax (opt-in screening rule)."""
    if not parcel.get('assumptions', {}).get('screen_season_mean_temperature', False):
        return state(UNKNOWN, [], ['explicit assumption screen_season_mean_temperature (season mean is only a screening statistic)'])
    climate = seasonal_climate(parcel['latitude'], parcel['longitude'], season['start'], season['end'], root)
    loc = dict(latitude=parcel['latitude'], longitude=parcel['longitude'], support=climate.get('support'))
    ev = [evidence('NASA POWER', climate.get('reason', 'season mean of complete daily series'), file=climate.get('source_path'),
                   sha256=climate.get('sha256'), variable='T2M', unit='C', period=f"{season['start']}/{season['end']}",
                   location=loc, value=climate.get('temperature_mean_c'))]
    t = climate.get('temperature_mean_c')
    if t is None:return state(UNKNOWN, ev, ['complete NASA POWER daily series at exact parcel coordinates for the season'])
    if row is None or not (bool(row.tmin_valid) and bool(row.tmax_valid)):
        return state(UNKNOWN, ev, ['valid EcoCrop absolute temperature bounds'])
    lo, hi = float(row.tmin_usable), float(row.tmax_usable)
    ev.append(_eco_ev(lineage, 'tmin/tmax', 'C', [lo, hi], 'absolute temperature range; rule = season mean inside range (design assumption)'))
    return state(ALLOWED if lo <= t <= hi else PROHIBITED, ev)


def gpm_evidence(parcel, season, root):
    """GPM IMERG monthly rates, reported as cross-check only (rates are not accumulated, no gate)."""
    path = Path(root) / 'data/processed/california_monthly_climate.parquet'
    if not path.exists():return []
    d = pd.read_parquet(path)
    d = d[d.latitude.eq(parcel['latitude']) & d.longitude.eq(parcel['longitude'])]
    months = pd.period_range(season['start'][:7], season['end'][:7], freq='M').astype(str)
    d = d[d.month.isin(months)]
    return [evidence('NASA GPM IMERG monthly (via california_monthly_climate)',
                     'context only; rainfall gating is unknown because EcoCrop rainfall bounds are annual',
                     file=str(path.relative_to(root)), sha256=r.gpm_source_sha256, variable='precipitation',
                     unit='mm/hr (monthly mean rate)', period=r.month,
                     location=dict(cell_latitude=r.gpm_cell_latitude, cell_longitude=r.gpm_cell_longitude),
                     value=None if pd.isna(r.gpm_precipitation_rate_mm_hr) else float(r.gpm_precipitation_rate_mm_hr))
            for r in d.itertuples()]


def calendar_constraint(crop, season, country, names, root):
    """FAO Crop Calendar windows; zone-free verification across all AEZ sessions of the country.

    Season start is compared with the sowing window and season end with the harvest window.
    All valid sessions contain both → allowed; none → prohibited; mixed → unknown (AEZ needed,
    no local AEZ geometry). Unmapped crop or country without calendar → unknown.
    """
    if not country:return state(UNKNOWN, [], ['country ISO2 declared by farmer (not derivable offline)'])
    countries = DataStore(root).verified_table('data/processed/agronomy-countries.parquet')
    src = evidence('FAO Crop Calendar', '', file='data/processed/agronomy-countries.parquet', sha256=countries.attrs['sha256'],
                   variable='id', location=dict(country_iso2=country))
    if country.upper() not in set(countries.id.astype(str)):
        src['reason'] = 'country absent from local FAO Crop Calendar dataset'
        return state(UNKNOWN, [src], [f'verified crop calendar for {country.upper()} (FAO dataset has none)'])
    m = names['mapped'].get(crop)
    if m is None:
        return state(UNKNOWN, [], [f'verifiable FAO calendar crop for {crop} (no exact scientific-name match)'])
    frame = DataStore(root).crop_reference('calendar', m['fao_crop_id'], area=country)
    rel = f'data/processed/agronomy-calendar-{country.upper()}.parquet'
    if not frame.empty:frame = frame[~frame.seasonal_date_invalid.astype(bool)]
    checks = []
    for _, r in frame.iterrows():
        try:
            def inside(early, late, target):
                low = (int(r['session_' + early + '_month']), int(r['session_' + early + '_day']))
                high = (int(r['session_' + late + '_month']), int(r['session_' + late + '_day']))
                d = day(target);p = (d.month, d.day)
                return low <= p <= high if low <= high else (p >= low or p <= high)
            checks.append((r, inside('early_sowing', 'later_sowing', season['start']) and inside('early_harvest', 'late_harvest', season['end'])))
        except (TypeError, ValueError):continue  # missing endpoints stay unknown
    ev = [evidence('FAO Crop Calendar', f"session {r.source_record}/{r.session_index} AEZ {r.aez_id}: {'contains' if ok else 'excludes'} season",
                   file=rel, sha256=digest(Path(root) / rel), variable='sowing/harvest windows', unit='month-day',
                   period=f"{season['start']}/{season['end']}", location=dict(country_iso2=country, aez_id=str(r.aez_id)),
                   value=m['fao_crop_id']) for r, ok in checks]
    if not checks:return state(UNKNOWN, ev, [f'valid FAO calendar session for {crop} in {country}'])
    if all(ok for _, ok in checks):return state(ALLOWED, ev)
    if not any(ok for _, ok in checks):return state(PROHIBITED, ev)
    return state(UNKNOWN, ev, ['parcel agro-ecological zone (sessions disagree; no local AEZ geometry)'])


def soil_constraint(row, lineage, parcel, declared_gate):
    """Farmer pH vs EcoCrop absolute pH range; nutrients only from an explicit declaration."""
    parts = []
    ph = parcel.get('soil', {}).get('ph')
    if ph is None or row is None or not (bool(row.phmin_valid) and bool(row.phmax_valid)):
        parts.append(state(UNKNOWN, [], ['soil pH declared/measured for the parcel and valid EcoCrop pH bounds']))
    else:
        lo, hi = float(row.phmin_usable), float(row.phmax_usable)
        parts.append(state(ALLOWED if lo <= ph <= hi else PROHIBITED,
                           [evidence('farmer declaration', 'parcel soil pH', variable='ph', unit='pH', value=ph),
                            _eco_ev(lineage, 'phmin/phmax', 'pH', [lo, hi], 'absolute pH range')]))
    allowed = declared(declared_gate)
    if allowed is None:
        parts.append(state(UNKNOWN, [evidence('local datasets', 'no validated soil nutrient data (SMAP is moisture; empty original)')],
                           ['soil nutrient assessment (lab/agronomist) declared with provenance']))
    else:
        parts.append(state(ALLOWED if allowed else PROHIBITED,
                           [evidence('farmer declaration', declared_gate['provenance'], variable='soil_nutrients', value=allowed)]))
    return combine(parts)


def water_constraint(available, required, season_index, computed=None, efficiency=None, soil_water=None):
    """Declared availability vs requirement. Returns (state, irrigation value for the optimizer or None).

    A declared requirement (with provenance) is used as stated. Otherwise the FAO-56 computed ETc
    interval gives: available < lower bound → prohibited; available ≥ upper bound → allowed; else unknown.
    """
    ev, needs = [], []
    if available is None:needs.append(f'declared water availability for season {season_index + 1} (mm)')
    else:ev.append(evidence('farmer declaration', 'declared availability', variable='water_available', unit='mm', value=available))
    if required is not None:
        ev.append(evidence('farmer/agronomist declaration', 'declared requirement, not computed', variable='irrigation_required', unit='mm', value=required))
        if needs:return state(UNKNOWN, ev, needs), None
        return state(ALLOWED if required <= available else PROHIBITED, ev), dict(value=required, status='declared', provenance='declared requirement')
    if computed is None or computed['status'] != 'computed':
        needs += (computed or {}).get('needs') or ['irrigation requirement: declared (mm, with provenance) or FAO-56 selection (Table 11 row, Table 12 label) to compute it']
        return state(UNKNOWN, ev + (computed or {}).get('evidence', []), needs), None
    ev += computed['evidence']
    lo, hi = irrigation_bounds(computed, efficiency, soil_water)
    ev.append(evidence('FAO-56 water balance bounds', 'lower = ETc_low − rainfall − initial soil water (net); upper = ETc_high / efficiency (gross); no leaching requirement',
                       variable='irrigation_requirement [lower, upper]', unit='mm', value=[None if lo is None else round(lo, 2), None if hi is None else round(hi, 2)]))
    if available is not None and lo is not None and available < lo:  # optimizer re-checks budget < lower bound
        return state(PROHIBITED, ev), dict(value=round(lo, 2), status='derived', provenance='FAO-56 ETc lower bound − rainfall − declared soil water')
    if available is not None and hi is not None and available >= hi:
        return state(ALLOWED, ev), dict(value=round(hi, 2), status='derived', provenance='FAO-56 ETc upper bound / declared efficiency (conservative)')
    if hi is None:needs.append('declared irrigation efficiency (0–1] to bound gross requirement')
    if lo is None:needs.append(f'declared initial plant-available soil water for season {season_index + 1} (mm) to bound net requirement')
    if not needs:needs.append(f'availability between computed bounds [{lo:.0f}, {hi:.0f}] mm: needs effective rainfall and soil water balance')
    return state(UNKNOWN, ev, needs), None


def fao56_cycle(row_days, season, row, lineage):
    """Cycle from the selected FAO-56 Table 11 row vs season length, checked against EcoCrop range."""
    length = (day(season['end']) - day(season['start'])).days + 1
    ev = [evidence('FAO-56 Table 11 (declared row)', f'total stage length vs season length {length} days', variable='total', unit='day', value=row_days)]
    if row is not None and bool(row.get('gmin_valid')) and bool(row.get('gmax_valid')) and not float(row.gmin_usable) <= row_days <= float(row.gmax_usable):
        return state(UNKNOWN, ev, ['review: FAO-56 row length outside EcoCrop gmin–gmax']), None
    return state(ALLOWED if row_days <= length else PROHIBITED, ev), row_days


# ---------- assembly and optimizer integration ----------

def build_constraints(request, root=ROOT):
    parcel = validate_input(request['parcel'])
    seasons = request['seasons'];farmer = request.get('farmer', {})
    if set(farmer) - FARMER_FIELDS:raise ValueError('Unknown farmer fields: ' + str(set(farmer) - FARMER_FIELDS))
    available = farmer.get('water_available') or [None] * len(seasons)
    required = farmer.get('irrigation_required', {})
    soil_water = farmer.get('initial_soil_water_mm') or [None] * len(seasons)
    efficiency = farmer.get('irrigation_efficiency')
    if len(available) != len(seasons) or len(soil_water) != len(seasons) or any(len(v) != len(seasons) for v in required.values()):
        raise ValueError('Water declarations must list one entry per season')
    if efficiency is not None and not (isinstance(efficiency, dict) and isinstance(efficiency.get('value'), (int, float)) and 0 < efficiency['value'] <= 1):
        raise ValueError('irrigation_efficiency must be {value in (0, 1], unit "fraction", provenance}')
    names = crop_name_map(root)
    crops = [c['crop'] for c in parcel['candidates']]
    out = dict(seasons=seasons, crops={}, transitions={}, history=None, names=names)
    for crop in crops:
        row, lineage = _ecocrop(crop, root)
        per_season = []
        for i, s in enumerate(seasons):
            selection = farmer.get('fao56', {}).get(crop)
            computed = crop_requirement(selection, s['start'], parcel['latitude'], parcel['longitude'], root,
                                        parcel.get('soil', {}).get('texture')) if selection else None
            if computed and computed.get('total_days'):
                cycle, cycle_days = fao56_cycle(computed['total_days'], s, row, lineage)
            else:
                cycle, cycle_days = cycle_constraint(row, lineage, s, declared(farmer.get('cycle', {}).get(crop), 'day'))
            climate = temperature_constraint(row, lineage, parcel, s, root)
            climate['evidence'] += gpm_evidence(parcel, s, root)
            water, irrigation = water_constraint(declared(available[i], 'mm'), declared(need[i], 'mm') if (need := required.get(crop)) else None, i,
                                                 computed, declared(efficiency, 'fraction'), declared(soil_water[i], 'mm'))
            soil_decl = farmer.get('soil_nutrients', {}).get(crop)
            per_season.append(dict(cycle=cycle, cycle_days=cycle_days, climate=climate, irrigation=irrigation,
                                   calendar=calendar_constraint(crop, s, farmer.get('country_iso2'), names, root),
                                   soil_nutrients=soil_constraint(row, lineage, parcel, soil_decl), water=water))
        if row is None:
            for g in per_season:g['climate']['needs'].append(f'unique exact EcoCrop record for {crop}')
        out['crops'][crop] = per_season
    previous = parcel.get('current_crop')
    rules = farmer.get('transitions', {})
    for a in sorted(set(crops) | ({previous} if previous else set())):
        for b in crops:
            v = declared(rules.get(a, {}).get(b))
            out['transitions'][f'{a} -> {b}'] = (state(ALLOWED if v else PROHIBITED,
                [evidence('farmer/agronomist declaration', rules[a][b]['provenance'], variable='transition', value=v)])
                if v is not None else state(UNKNOWN, [], [f'documented transition rule {a} -> {b} (no local rotation-rule dataset)']))
    h = declared(farmer.get('history_review'))
    out['history'] = (state(ALLOWED if h else PROHIBITED, [evidence('farmer declaration', farmer['history_review']['provenance'], variable='history_review', value=h)])
                      if h is not None else state(UNKNOWN, [], ['reviewed crop history with provenance']))
    if not previous:out['history']['needs'].append('current/preceding crop')
    return out


def missing_information(built, parcel):
    """Unknowns that block a decision. Crop-seasons with a prohibited gate are excluded, not missing."""
    missing = []
    live = {}
    for crop, per_season in built['crops'].items():
        live[crop] = False
        for i, g in enumerate(per_season):
            states = [g[k]['state'] for k in GATES]
            if PROHIBITED in states:continue
            live[crop] = True
            missing += [f'{crop} / season {i + 1} / {k}: {n}' for k in GATES for n in g[k]['needs'] if g[k]['state'] == UNKNOWN]
    previous = parcel.get('current_crop')
    for pair, t in built['transitions'].items():
        a, b = pair.split(' -> ')
        if t['state'] == UNKNOWN and live.get(b) and (a == previous or live.get(a)):missing += t['needs']
    if built['history']['state'] == UNKNOWN or not previous:missing += built['history']['needs']
    return sorted(set(missing))


def _gate(c):
    return dict(allowed=c['state'] == ALLOWED, status='derived' if any(e['source'].startswith(('NASA', 'FAO')) for e in c['evidence']) else 'declared',
                provenance='; '.join(sorted({f"{e['source']}: {e['reason']}" for e in c['evidence']})) or 'no evidence')


def to_optimizer_input(request, built):
    parcel = request['parcel'];farmer = request.get('farmer', {})
    seasons = [dict(start=s['start'], end=s['end'], irrigation_budget=dict(value=farmer['water_available'][i]['value'], unit='mm',
                    status='declared', provenance=farmer['water_available'][i]['provenance'])) for i, s in enumerate(request['seasons'])]
    crops = {}
    for crop, per_season in built['crops'].items():
        days = {g['cycle_days'] for g in per_season if g['cycle_days'] is not None}
        if len(days) > 1:raise ValueError('Inconsistent cycle for ' + crop)
        # Optimizer re-checks cycle ≤ season length with this value (EcoCrop gmax or declared cycle).
        entry = dict(cycle=dict(value=days.pop(), unit='day', status='derived', provenance='EcoCrop gmax or declared cultivar cycle')
                     if days else None, seasons=[])
        for i, g in enumerate(per_season):
            e = dict(calendar=_gate(g['calendar']), climate=_gate(g['climate']), soil_nutrients=_gate(g['soil_nutrients']))
            if g['irrigation'] is not None:e['irrigation_required'] = dict(unit='mm', **g['irrigation'])
            entry['seasons'].append(e)
        crops[crop] = entry
    transitions = {}
    for pair, t in built['transitions'].items():
        a, b = pair.split(' -> ')
        transitions.setdefault(a, {})[b] = dict(allowed=t['state'] == ALLOWED, status='declared',
                                                provenance=(t['evidence'][0]['reason'] if t['evidence'] else 'not determined; crop excluded'))
    h = built['history']
    return dict(parcel=parcel, seasons=seasons, crops=crops, transitions=transitions, objectives=request.get('objectives', []),
                history_review=dict(allowed=h['state'] == ALLOWED, status='declared', provenance=h['evidence'][0]['reason'] if h['evidence'] else 'none'))


def optimize_with_evidence(request, root=ROOT):
    """Build evidence-based constraints, then optimize only if nothing mandatory is unknown."""
    result = dict(status='abstained', evaluation='experimental_not_agronomically_validated', recommendation=None,
                  constraints=None, missing=[], optimizer=None)
    try:
        built = build_constraints(request, root)
    except (KeyError, ValueError, TypeError) as error:
        result['missing'] = ['invalid request: ' + str(error)];return result
    result['constraints'] = {k: v for k, v in built.items() if k != 'names'}
    result['name_mapping'] = {c: built['names']['mapped'].get(c) for c in built['crops']}
    result['missing'] = missing_information(built, request['parcel'])
    if result['missing']:return result
    opt = optimize(to_optimizer_input(request, built))
    result['optimizer'] = opt
    result['status'] = opt['status']
    result['recommendation'] = None  # outputs are evaluations of supplied/derived constraints, not agronomic advice
    return result


def summary(built):
    """Compact table: crop × season × gate → state."""
    return {crop: [{k: g[k]['state'] for k in GATES} for g in per_season] for crop, per_season in built['crops'].items()}
