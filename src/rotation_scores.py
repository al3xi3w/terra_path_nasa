"""Water, soil and risk scores for 3-season rotations, with a real Pareto front.

Screening layer, deliberately separate from src/constraints.py: that module abstains when
anything is unknown, which is right for a recommendation but leaves nothing to show. Here every
rotation is scored under stated simplifications, and each score carries the method it used and
the crops whose data is missing. A missing value is never read as a favourable one.

A rotation is three successive campaigns in the point's own growing window, not three crops
squeezed into one year: Iowa has one campaign a year, and forcing three would exclude every
crop. The window is chosen as the four-month block where most crops are eligible, and the same
window is used for all three campaigns.

Eligibility is judged inside that window: an extreme night in 44 years does not disqualify a
crop from a window it is never planted in. Structural limits (altitude, annual rainfall) apply
to the whole point.

Simplifications, all reported in the output:
- Campaigns are four-month blocks; real lengths come from the crop cycle and the local calendar,
  which this layer does not use.
- Where FAO-56 Kc is known, water demand is Kc_mid x ET0 over the season. That is a screening
  figure, not the per-stage ETc of src/water_requirement.py.
- Effective rainfall is not modelled: the deficit compares demand with total rainfall.
"""
from itertools import permutations
import pandas as pd
from .pipeline import ROOT
from .climate_profile import monthly_profile, daily_series, pilots
from .crop_library import build_library
from .terrain import point_elevation

STARTS = {'ene': 1, 'may': 5, 'sep': 9}
FALLOW = 'barbecho'
CAMPAIGNS = 3
COVER = {'clover_red', 'alfalfa', 'oat'}
AXES = ('water', 'soil', 'risk')


def frost_days_by_month(frame, threshold):
    """Mean days per calendar month below `threshold`, over complete months only."""
    d = frame.assign(year=frame.fecha.dt.year, month=frame.fecha.dt.month)
    counts = d.assign(cold=d.T2M_MIN < threshold).groupby(['year', 'month']).agg(cold=('cold', 'sum'), days=('fecha', 'size'))
    expected = pd.Series({k: pd.Period(f'{k[0]}-{k[1]:02d}').days_in_month for k in counts.index})
    counts = counts[counts.days.eq(expected)]
    return counts.groupby(level=1).cold.mean().to_dict()


def window_days(months):
    """Length of the window in days, using a non-leap reference year."""
    return sum(pd.Period(f'2001-{m:02d}').days_in_month for m in months)


def campaign_months(start, cycle_days):
    """Calendar months a campaign occupies: from `start`, as many months as the EcoCrop minimum cycle
    needs (the shortest cultivar). None when the cycle is unknown or longer than a year."""
    if cycle_days is None or pd.isna(cycle_days):return None
    months, days = [], 0.0
    while days < float(cycle_days):
        m = (start - 1 + len(months)) % 12 + 1
        months.append(m);days += window_days([m])
        if len(months) > 12:return None
    return months


def window_eligibility(profile, library, elevation, frost_by_crop, start):
    """One row per crop for campaigns starting in `start`, each over its own cycle: eligible, excluded or unknown."""
    annual_rain = float(profile.rain_mean_mm.sum())
    rows = []
    for crop in library.itertuples():
        checks, missing = {}, []
        months = campaign_months(start, crop.cycle_min_days)
        if pd.isna(crop.cycle_min_days):missing.append('cycle_min_days')
        elif months is None:checks['cycle'] = False  # longer than a year
        window = profile[profile.month.isin(months or [])]
        if pd.isna(crop.annual_rain_min_mm):missing.append('annual_rain_min_mm')
        else:checks['annual_rain'] = annual_rain >= float(crop.annual_rain_min_mm)
        if pd.isna(crop.max_altitude_m):missing.append('max_altitude_m')
        elif elevation is None:missing.append('point elevation')
        else:checks['altitude'] = elevation <= float(crop.max_altitude_m)
        if months:
            if pd.isna(crop.t_abs_max_c):missing.append('t_abs_max_c')
            else:checks['heat'] = float(window.t_max_mean_c.mean()) <= float(crop.t_abs_max_c)
            if pd.isna(crop.t_abs_min_c):missing.append('t_abs_min_c')
            else:checks['cold'] = float(window.t_min_mean_c.mean()) >= float(crop.t_abs_min_c)
            if pd.isna(crop.killing_temperature_c):missing.append('killing_temperature_c')
            else:checks['frost'] = sum(frost_by_crop[crop.crop_key].get(m, 0.0) for m in months) < 1.0
        failed = [k for k, v in checks.items() if v is False]
        rows.append(dict(crop_key=crop.crop_key, state='excluded' if failed else ('eligible' if not missing else 'unknown'),
                         failed=failed, missing=missing, months=months))
    return pd.DataFrame(rows)


def choose_window(profile, library, elevation, frost_by_crop):
    """The start month with most eligible crops; ties go to the earliest start."""
    counts = {}
    for name, start in STARTS.items():
        frame = window_eligibility(profile, library, elevation, frost_by_crop, start)
        counts[name] = dict(eligible=int((frame.state == 'eligible').sum()),
                            unknown=int((frame.state == 'unknown').sum()), table=frame)
    best = max(STARTS, key=lambda n: (counts[n]['eligible'], -list(STARTS).index(n)))
    return best, counts


def families_ok(families):
    """No family twice in a row, counting the wrap from the last campaign back to the first:
    the rotation repeats, so the last crop is followed by the first one."""
    cropped = [f for f in families if f is not None]
    if len(cropped) < 2:return True
    ring = families + families[:1]
    pairs = [(a, b) for a, b in zip(ring, ring[1:]) if a is not None and b is not None]
    if None in families:  # fallow separates its neighbours, but with one fallow in three campaigns the two crops still meet
        pairs.append(tuple(cropped))
    return all(a != b for a, b in pairs)


def rain_position(value, bounds):
    """100 inside the EcoCrop optimal range, falling to 50 at the absolute bounds, 0 outside."""
    low, opt_low, opt_high, high = bounds
    if value < low or value > high:return 0.0
    if opt_low <= value <= opt_high:return 100.0
    if value < opt_low:return round(50 + 50 * (value - low) / (opt_low - low), 1) if opt_low > low else 100.0
    return round(50 + 50 * (high - value) / (high - opt_high), 1) if high > opt_high else 100.0


def water_score(crop, profile, months):
    """0-100 from FAO-56 only: 100 - 100 x deficit/demand over the window. Without Kc the score is None.

    The EcoCrop annual-rainfall position used to stand in for missing Kc, but the two are not
    comparable: a crop without Kc scored higher than one with a measured deficit, so missing data
    became favourable. It is now returned only as a reference (`ecocrop_rain_reference`).
    """
    window = profile[profile.month.isin(months)]
    rain = float(window.rain_mean_mm.sum())
    et0 = window.et0_mean_mm
    if pd.notna(crop.kc_mid) and et0.notna().all():
        demand = float(crop.kc_mid) * float(et0.sum())
        if demand <= 0:return None, 'invalid demand', None
        deficit = max(0.0, demand - rain)
        return round(max(0.0, 100 * (1 - deficit / demand)), 1), 'FAO-56 Kc_mid x ET0 vs rainfall (screening)', round(deficit, 1)
    if pd.isna(crop.kc_mid):return None, 'desconocido: sin Kc FAO-56 verificado', None
    return None, 'desconocido: sin ET0 completa en la ventana', None


def ecocrop_rain_reference(crop, profile):
    """Position of annual rain in the EcoCrop bounds. Reference only: never ranked against a Kc deficit."""
    bounds = [crop.annual_rain_min_mm, crop.annual_rain_opt_min_mm, crop.annual_rain_opt_max_mm, crop.annual_rain_max_mm]
    if not all(pd.notna(b) for b in bounds):return None
    return rain_position(float(profile.rain_mean_mm.sum()), [float(b) for b in bounds])


def soil_score(sequence, library):
    """0-100 from documented rotation facts only: a legume, family changes, a cover crop."""
    rows = {c: library[library.crop_key == c].iloc[0] for c in set(sequence)}
    families = [rows[c].family for c in sequence]
    score, detail = 0, []
    if any(bool(rows[c].family_leguminosae) for c in sequence):
        score += 40;detail.append('leguminosa presente (familia botánica Leguminosae)')
    changes = sum(1 for a, b in zip(families, families[1:]) if a != b)
    score += 20 * changes;detail.append(f'{changes} cambios de familia entre temporadas seguidas')
    if any(c in COVER for c in sequence):score += 20;detail.append('cultivo de cobertura o forraje presente')
    return min(100, score), detail


DROUGHT_FRACTION = 0.5  # declared: a campaign is "dry" when its rain is below half of its own long-term mean


def campaign_rain_by_year(frame, months):
    """Total rain of the campaign months for each campaign year; only years whose months are all complete.
    A campaign that crosses December belongs to the year in which it starts."""
    d = frame[['fecha', 'PRECTOTCORR']].assign(year=frame.fecha.dt.year, month=frame.fecha.dt.month)
    d = d[d.month.isin(months)]
    start = months[0]
    d['campaign'] = d.year - (d.month < start).astype(int)
    g = d.groupby(['campaign', 'year', 'month'])
    full = g.fecha.size().eq(pd.Series({k: pd.Period(f'{k[1]}-{k[2]:02d}').days_in_month for k in g.groups})) & g.PRECTOTCORR.count().eq(g.fecha.size())
    totals = g.PRECTOTCORR.sum()[full].groupby(level=0).agg(['sum', 'count'])
    return totals[totals['count'] == len(months)]['sum']


def drought_share(frame, months):
    """Share of campaign years with rain below DROUGHT_FRACTION x the mean campaign rain; None if no complete year."""
    if not months:return None
    totals = campaign_rain_by_year(frame, months)
    if totals.empty or totals.mean() <= 0:return None
    return float((totals < DROUGHT_FRACTION * totals.mean()).mean())


def risk_score(crop, profile, months, frost_by_month, drought=None):
    """0-100. Penalises expected frost days at the crop's own killing temperature, rain variability and
    dry campaigns (share of years under half the mean campaign rain: -1 point per percentage point, max 30)."""
    window = profile[profile.month.isin(months)]
    cv = window.rain_cv
    variability = float(cv.mean()) if cv.notna().any() else None
    frost = None if frost_by_month is None else float(sum(frost_by_month.get(m, 0.0) for m in months))
    parts, score = {}, 100.0
    if frost is not None:
        parts['frost_days'] = round(frost, 2);score -= min(60.0, frost * 2)
    if variability is not None:
        parts['rain_cv'] = round(variability, 3);score -= min(40.0, variability * 40)
    if drought is not None:
        parts['drought_share'] = round(drought, 3);score -= min(30.0, drought * 100)
    method = ('helada a la temperatura letal del cultivo + variabilidad de lluvia + sequía' if frost is not None
              else 'variabilidad de lluvia + sequía; sin temperatura letal para este cultivo')
    return round(max(0.0, score), 1), method, parts


def pareto_front(rows, keys=AXES):
    """Non-dominated set: no other rotation is at least equal on every axis and better on one."""
    return [a for a in rows
            if not any(all(b[k] >= a[k] for k in keys) and any(b[k] > a[k] for k in keys) for b in rows)]


def weighted_total(row, weights=None):
    """Sum of the three axes, weighted. None means equal weights (the original tie-break)."""
    weights = weights or {k: 1.0 for k in AXES}
    return sum(weights[k] * row[k] for k in AXES)


def pick_routes(front, rows, weights=None):
    """Three routes with different crop sets: best on water, then on soil, then on risk.

    Water and risk do not depend on the order, so the front holds many reorderings of one set;
    requiring a different set keeps the three routes genuinely different for the farmer.
    Ties on the route's own axis are broken by the weighted total (equal weights by default).
    """
    routes, taken = {}, []
    front_sets = {frozenset(r['sequence']) for r in front}
    for axis, name in [('water', 'ruta_agua'), ('soil', 'ruta_suelo'), ('risk', 'ruta_riesgo')]:
        pool = [r for r in front if frozenset(r['sequence']) not in taken]
        source = 'pareto'
        if not pool:  # the front holds fewer than three distinct crop sets
            pool = [r for r in rows if frozenset(r['sequence']) not in taken]
            source = 'dominada: el frente de Pareto no tiene tres conjuntos de cultivos distintos'
        if not pool:routes[name] = None;continue
        best = dict(sorted(pool, key=lambda r: (-r[axis], -weighted_total(r, weights), r['sequence']))[0])
        best['from_pareto_front'] = frozenset(best['sequence']) in front_sets
        best['selection'] = source
        routes[name] = best;taken.append(frozenset(best['sequence']))
    return routes


def score_point(latitude, longitude, label=None, root=ROOT, max_crops=8, start=None, end=None, keep_rows=False):
    """Score every rotation at a point. `start`/`end` restrict the climate period (backtesting
    calibrates on 1981-2015); `keep_rows` adds the full rotation table, needed to re-rank it."""
    library = build_library(root)
    profile, meta = monthly_profile(latitude, longitude, root, start=start, end=end)
    if profile is None:return dict(status='no_data', reason=meta.get('reason'), label=label)
    frame, _ = daily_series(latitude, longitude, root)
    if start:frame = frame[frame.fecha >= pd.Timestamp(start)]
    if end:frame = frame[frame.fecha <= pd.Timestamp(end)]
    meta['climate_period_used'] = [str(frame.fecha.min().date()), str(frame.fecha.max().date())]
    frost_by_crop = {c.crop_key: ({} if pd.isna(c.killing_temperature_c)
                                  else frost_days_by_month(frame, float(c.killing_temperature_c)))
                     for c in library.itertuples()}
    srtm = point_elevation(latitude, longitude, root)
    meta['elevation_for_suitability'] = (dict(srtm, value_m=srtm['value_m']) if srtm else
                                         dict(value_m=meta.get('elevation_m'), source='MERRA-2 (encabezado POWER); sin tile SRTM local',
                                              note='promedio de celda ~50 km, no la altitud del punto'))
    window_name, counts = choose_window(profile, library, meta['elevation_for_suitability']['value_m'], frost_by_crop)
    eligibility = counts[window_name]['table']
    months_of = dict(zip(eligibility.crop_key, eligibility.months))
    all_eligible = eligibility[eligibility.state == 'eligible'].crop_key.tolist()
    universe = all_eligible[:max_crops]
    months = sorted({m for c in universe for m in (months_of[c] or [])})
    base = dict(label=label, point=meta, window=f'inicio {window_name}', window_start=STARTS[window_name], window_months=months,
                window_choice={k: dict(eligible=v['eligible'], unknown=v['unknown']) for k, v in counts.items()},
                eligible=universe, eligible_not_used=all_eligible[max_crops:], eligibility=eligibility.to_dict('records'),
                simplifications=['cada campaña empieza en el mes elegido y dura el ciclo mínimo de EcoCrop (el cultivar más corto); no se usa el calendario local',
                                 'una campaña por año; la regla de familias incluye el paso de la última campaña a la primera porque la rotación se repite',
                                 'el barbecho no tiene agua ni riesgo: sus rutas promedian solo los cultivos y se rankean aparte',
                                 'la demanda de agua es Kc_medio x ET0 por campaña, no la ETc por etapas de src/water_requirement.py',
                                 'el agua solo se puntúa con Kc FAO-56; sin Kc es desconocida y la rotación queda fuera de las rutas',
                                 'no se modela la lluvia efectiva: el déficit compara la demanda con la lluvia total',
                                 'el puntaje de suelo cuenta hechos documentados de rotación; no es un balance de nutrientes',
                                 'la altitud del filtro es SRTM en el punto; la temperatura sigue siendo POWER (celda ~50 km), que en montaña puede no corresponder a esa altitud',
                                 f'sequía: años con lluvia de campaña bajo {DROUGHT_FRACTION:.0%} de la media de la campaña (umbral declarado, no agronómico)',
                                 'la pendiente (terreno.csv) todavía no entra en el puntaje de suelo',
                                 'las campañas usan la misma climatología; no se modelan años distintos'],
                disclaimer='solo tamizaje; no es una recomendación agronómica')
    if len(universe) < 2:
        return dict(status='insufficient_crops', reason=f'solo {len(universe)} cultivos elegibles con inicio en {window_name}', **base)
    scores = {}
    for crop_key in universe:
        crop = library[library.crop_key == crop_key].iloc[0]
        own = months_of[crop_key]
        w, w_method, deficit = water_score(crop, profile, own)
        r, r_method, parts = risk_score(crop, profile, own, frost_by_crop.get(crop_key) or None, drought_share(frame, own))
        scores[crop_key] = dict(months=own, water=w, water_method=w_method, water_deficit_mm=deficit,
                                ecocrop_rain_reference=ecocrop_rain_reference(crop, profile),
                                risk=r, risk_method=r_method, risk_parts=parts)
    family_of = dict(zip(library.crop_key, library.family))

    def rotation(sequence):
        crops = [c for c in sequence if c != FALLOW]
        missing = {f'{c}: agua ({scores[c]["water_method"]})' for c in crops if scores[c]['water'] is None}
        missing |= {f'{c}: helada (sin temperatura letal)' for c in crops if 'sin temperatura letal' in scores[c]['risk_method']}
        water = [scores[c]['water'] for c in crops]
        soil, soil_detail = soil_score(crops, library)
        return dict(sequence=list(sequence), water=None if None in water else round(sum(water) / len(crops), 1), soil=float(soil),
                    risk=round(sum(scores[c]['risk'] for c in crops) / len(crops), 1),
                    soil_detail=soil_detail, missing=sorted(missing), cropped_campaigns=len(crops),
                    methods={'water': sorted({scores[c]['water_method'] for c in crops}),
                             'risk': sorted({scores[c]['risk_method'] for c in crops})})

    rows = [rotation(seq) for seq in permutations(universe, CAMPAIGNS) if families_ok([family_of[c] for c in seq])]
    fallow_rows = [rotation((a, b, FALLOW)) for a, b in permutations(universe, 2)
                   if scores[a]['water'] is not None and scores[b]['water'] is not None and families_ok([family_of[a], family_of[b], None])]
    fallow_front = pareto_front(fallow_rows)
    base['routes_with_fallow'] = pick_routes(fallow_front, fallow_rows) if fallow_rows else None
    base['fallow_note'] = 'rutas de dos cultivos y una campaña de barbecho; se rankean aparte porque promedian solo dos cultivos'
    if not rows:
        return dict(status='no_valid_rotation', crop_scores=scores,
                    reason='ninguna combinación de tres cultivos respeta el cambio de familia, contando el paso de la última campaña a la primera', **base)
    known = [r for r in rows if r['water'] is not None]
    unknown = [r for r in rows if r['water'] is None]
    unknown_sets = sorted({tuple(sorted(r['sequence'])) for r in unknown})
    base.update(unknown_water=dict(rotations=len(unknown), crop_sets=[list(s) for s in unknown_sets],
                                   crops_without_kc=sorted(c for c in universe if scores[c]['water'] is None),
                                   note='fuera del frente y de las rutas: su agua es desconocida, no cero ni favorable'))
    if not known:
        return dict(status='no_known_water', crop_scores=scores, rotations=len(rows),
                    reason='ninguna rotación tiene agua conocida (todas incluyen un cultivo sin Kc FAO-56)', **base)
    front = pareto_front(known)
    result = dict(status='scored', crop_scores=scores, rotations=len(rows), rotations_known_water=len(known), pareto=len(front),
                  routes=pick_routes(front, known), front=sorted(front, key=lambda r: (-sum(r[k] for k in AXES), r['sequence'])), **base)
    if keep_rows:result['rows'] = known
    return result


def score_pilots(root=ROOT):
    return {p['name']: score_point(p['latitude'], p['longitude'], p.get('label'), root) for p in pilots(root)}
