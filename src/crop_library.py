"""Global crop library built only from verified local references; nothing is estimated.

Every numeric value comes from an EcoCrop column whose *_valid flag is true; anything else is
null. Botanical family is EcoCrop's own famname (FAO Crop Calendar's crop_family is a use
group such as "OTHER CROPS" and is never used here). FAO-56 Kc is not assigned: Table 12
labels whose text matches a common name are listed as candidates for a human to confirm.

The species list (config/crop_library_species.json) is a declared selection, not a verified
equivalence. The library is global: it holds crop properties, no location is involved.
"""
import json
from pathlib import Path
import pandas as pd
from .pipeline import ROOT, digest
from .audit import write_table
from .store import DataStore
from .water_requirement import verified_tables

SPECIES_CONFIG = 'config/crop_library_species.json'
KC_CONFIG = 'config/crop_library_kc.json'
LEGUME_FAMILIES = {'Leguminosae', 'Fabaceae'}
# EcoCrop column -> library column; each is used only when its *_valid flag is true.
NUMERIC = [('gmin', 'cycle_min_days'), ('gmax', 'cycle_max_days'), ('topmn', 't_opt_min_c'), ('topmx', 't_opt_max_c'),
           ('tmin', 't_abs_min_c'), ('tmax', 't_abs_max_c'), ('ktmp', 'killing_temperature_c'),
           ('rmin', 'annual_rain_min_mm'), ('ropmn', 'annual_rain_opt_min_mm'),
           ('ropmx', 'annual_rain_opt_max_mm'), ('rmax', 'annual_rain_max_mm'), ('phmin', 'ph_min'), ('phmax', 'ph_max'),
           ('altmx', 'max_altitude_m')]


def species_selection(root=ROOT):
    data = json.loads((Path(root) / SPECIES_CONFIG).read_text())
    return data['species'], data['status']


def common_names(value):
    if isinstance(value, str):return [value]
    try:return [str(v) for v in value]
    except TypeError:return []


def fao56_table12(root=ROOT):
    """Every Table 12 row available locally: the audited parquet plus the stage-verified config."""
    frame = DataStore(root).verified_table('data/processed/fao56_kc_verified.parquet')
    rows = {str(r.crop_label): dict(kc_initial=None if pd.isna(r.kc_initial) else float(r.kc_initial),
                                    kc_mid=None if pd.isna(r.kc_mid) else float(r.kc_mid),
                                    kc_end=None if pd.isna(r.kc_end) else float(r.kc_end),
                                    source='data/processed/fao56_kc_verified.parquet') for r in frame.itertuples()}
    for r in verified_tables(root)['table12']:
        end, mid = r['kc_end'], r['kc_mid']
        rows[r['crop_label']] = dict(kc_initial=r['kc_initial'], kc_mid=single(mid),
                                     kc_mid_range=mid if isinstance(mid, list) and mid[0] != mid[1] else None,
                                     kc_end=single(end),
                                     kc_end_range=end if isinstance(end, list) else None,
                                     source='config/fao56_stages_verified.json')
    return rows


def single(value):
    """A scalar, or a [low, high] range with low == high; a true range has no single value (None)."""
    if isinstance(value, list):return value[0] if value[0] == value[1] else None
    return value


def agreed_kc(labels, table12):
    """Kc for one or several Table 12 labels. With several, each coefficient is kept only where
    every label gives the same value: wheat's three labels share Kc_mid 1.15 but not Kc_ini."""
    if labels is None:return None
    labels = [labels] if isinstance(labels, str) else list(labels)
    rows = [table12.get(l) for l in labels]
    if any(r is None for r in rows):return None
    out = {}
    for k in ('kc_initial', 'kc_mid', 'kc_end', 'kc_mid_range', 'kc_end_range'):
        values = [r.get(k) for r in rows]
        out[k] = values[0] if all(v == values[0] for v in values) else None
    return out


def kc_selection(root=ROOT):
    data = json.loads((Path(root) / KC_CONFIG).read_text())
    return data['mapping'], data.get('pending', {}), data['status']


def fao56_labels(root=ROOT):
    return [(label, row['source']) for label, row in fao56_table12(root).items()]


def kc_candidates(names, labels):
    """Table 12 labels containing a whole common name. Text match only: a suggestion, not a mapping."""
    found = []
    for label, source in labels:
        words = set(label.lower().replace(',', ' ').replace('(', ' ').replace(')', ' ').replace('-', ' ').split())
        for name in names:
            token = name.strip().lower()
            if token and (token in words or token + 's' in words or token.rstrip('s') in words):
                found.append(label);break
    return sorted(set(found))


def build_library(root=ROOT):
    selection, status = species_selection(root)
    store = DataStore(root)
    eco = store.verified_table('data/processed/ecocrop_validated.parquet')
    table12 = fao56_table12(root)
    labels = [(label, row['source']) for label, row in table12.items()]
    kc_map, kc_pending, kc_status = kc_selection(root)
    rows = []
    for key, scientific in selection.items():
        match = eco[eco.scientificname.astype(str).str.strip() == scientific]
        row = dict(crop_key=key, scientific_name=scientific, selection_status=status,
                   found_in_ecocrop=len(match) == 1)
        if len(match) != 1:
            row['note'] = 'no unique exact EcoCrop record; all properties unknown'
            rows.append(row);continue
        r = match.iloc[0]
        family_path = str(r.famname)
        family = family_path.split(':')[-1]
        names = common_names(r.comname)
        row.update(ecoportcode=str(r.ecoportcode), family=family, family_path=family_path,
                   family_leguminosae=family in LEGUME_FAMILIES,
                   common_names='; '.join(names[:6]),
                   fao56_table12_candidates='; '.join(kc_candidates(names + [key], labels)) or None)
        for column, name in NUMERIC:
            valid = bool(r.get(column + '_valid', False))
            value = r.get(column + '_usable')
            row[name] = float(value) if valid and pd.notna(value) else None
        mapped = kc_map.get(key)
        kc = agreed_kc(mapped, table12)
        label = ' | '.join(mapped) if isinstance(mapped, list) else mapped
        row.update(fao56_table12_label=label, kc_selection_status=kc_status if label else 'unmapped',
                   kc_initial=(kc or {}).get('kc_initial'), kc_mid=(kc or {}).get('kc_mid'), kc_end=(kc or {}).get('kc_end'),
                   kc_mid_range=str((kc or {}).get('kc_mid_range')) if (kc or {}).get('kc_mid_range') else None,
                   kc_end_range=str((kc or {}).get('kc_end_range')) if (kc or {}).get('kc_end_range') else None,
                   kc_pending_reason=kc_pending.get(key) if not label else None,
                   source='EcoCrop (rangos) + FAO-56 Tabla 12 (Kc)' if label else 'EcoCrop (rangos)')
        rows.append(row)
    frame = pd.DataFrame(rows)
    frame.attrs['ecocrop_sha256'] = eco.attrs['sha256']
    return frame


def write_library(root=ROOT):
    frame = build_library(root)
    path = Path(root) / 'data/processed/crop_library.parquet'
    write_table(frame, path, {
        'scope': 'crop properties only; global, no location or yield',
        'ranges': 'EcoCrop *_usable values, kept only where the matching *_valid flag is true; null otherwise',
        'cycle': 'gmin/gmax range in days; no single representative cycle is chosen',
        'rainfall': 'EcoCrop rmin/rmax are ANNUAL totals; never compare them with a season',
        'family': "EcoCrop famname (botanical); FAO Crop Calendar crop_family is a use group and is not used",
        'nitrogen': 'not stored: family_leguminosae records the botanical family only; nodulation and nitrogen fixation are species and management dependent',
        'kc': 'only from a declared Table 12 label; fao56_table12_candidates are text matches requiring confirmation and are never used as the mapping',
        'species_selection': 'config/crop_library_species.json, declared and pending agronomist review',
        'kc_selection': 'config/crop_library_kc.json, declared and pending agronomist review; null where no verified Table 12 row applies',
        'ecocrop_sha256': frame.attrs['ecocrop_sha256'],
        'fao56_pdf_sha256': verified_tables(root)['pdf_sha256']})
    frame.to_csv(path.with_suffix('.csv'), index=False)
    return path


def missing_properties(frame):
    """What each crop still lacks, so a score never silently treats a null as a zero."""
    columns = [name for _, name in NUMERIC]
    return {r.crop_key: [c for c in columns if pd.isna(getattr(r, c, None))] for r in frame.itertuples()}
