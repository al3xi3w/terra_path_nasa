import copy, json
from pathlib import Path
import pytest
from src import constraints as C
from src.pipeline import digest

CROPS = ['Zea mays', 'Glycine max', 'Triticum aestivum']
DECL = 'Test fixture: explicit declaration, not an agronomic estimate'


@pytest.fixture
def real():
    return json.loads(Path('examples/rotations/california_evidence.input.json').read_text())


@pytest.fixture
def declared(real, monkeypatch):
    """Real California climate + complete explicit declarations; calendar forced (no US FAO calendar)."""
    def calendar(crop, season, country, names, root):
        return C.state(C.ALLOWED, [C.evidence('test', 'synthetic calendar gate for integration test only')])
    monkeypatch.setattr(C, 'calendar_constraint', calendar)
    real['parcel']['current_crop'] = 'Zea mays'
    real['parcel']['soil'] = {'ph': 6.5}
    v = lambda x: dict(value=x, unit='mm', provenance=DECL)
    real['farmer'] = dict(country_iso2='US',
        water_available=[v(100), v(100)],
        irrigation_required={c: [v(50), v(60 + i)] for i, c in enumerate(CROPS)},
        cycle={c: dict(value=100, unit='day', provenance=DECL) for c in CROPS},
        soil_nutrients={c: dict(allowed=True, provenance=DECL) for c in CROPS},
        transitions={a: {b: dict(allowed=a != b, provenance=DECL) for b in CROPS} for a in CROPS},
        history_review=dict(allowed=True, provenance=DECL))
    return real


def test_three_states_unknown_never_allowed():
    a, u, p = (C.state(s, []) for s in [C.ALLOWED, C.UNKNOWN, C.PROHIBITED])
    assert C.combine([a, u])['state'] == C.UNKNOWN
    assert C.combine([a, u, p])['state'] == C.PROHIBITED
    assert C.combine([a, a])['state'] == C.ALLOWED
    assert C.declared({'allowed': True}) is None  # no provenance → not a declaration


def test_name_mapping_exact_only():
    m = C.crop_name_map()
    assert m['mapped']['Zea mays']['fao_crop_id'] == '0338'
    assert m['mapped']['Glycine max']['fao_crop_id'] == '0326'
    assert 'Triticum aestivum' not in m['mapped']  # FAO has 'Triticum aestivum L. subsp. aestivum' only
    assert all(v['match'] == 'exact scientific name string' for v in m['mapped'].values())


def test_california_abstains_and_explains(real):
    r = C.optimize_with_evidence(real)
    assert r['status'] == 'abstained' and r['optimizer'] is None and r['recommendation'] is None
    text = '\n'.join(r['missing'])
    for need in ['verified crop calendar for US', 'declared water availability', 'irrigation requirement',
                 'soil pH', 'documented transition rule', 'current/preceding crop', 'declared cultivar cycle']:
        assert need in text
    climate = r['constraints']['crops']['Zea mays'][0]['climate']
    assert climate['state'] == C.ALLOWED  # only the opt-in temperature screen is computed from data


def test_provenance_complete(real):
    b = C.build_constraints(real)
    ev = b['crops']['Zea mays'][0]['climate']['evidence']
    power, eco = ev[0], ev[1]
    assert power['sha256'] == digest(Path(power['file'])) and power['unit'] == 'C' and power['variable'] == 'T2M'
    assert power['period'] == '2023-03-01/2023-06-30' and power['location']['latitude'] == 36.59
    assert eco['source'] == 'FAO EcoCrop' and eco['value'] == [10.0, 47.0] and eco['reason']
    gpm = [e for e in ev if e['source'].startswith('NASA GPM')]
    assert [e['period'] for e in gpm] == ['2023-03', '2023-04', '2023-05', '2023-06'] and all(e['sha256'] for e in gpm)


def test_temperature_requires_explicit_assumption(real):
    real['parcel']['assumptions'] = {}
    b = C.build_constraints(real)
    assert all(g['climate']['state'] == C.UNKNOWN for s in b['crops'].values() for g in s)


def test_calendar_real_fao_peru():
    names = C.crop_name_map()
    mixed = C.calendar_constraint('Zea mays', {'start': '2023-02-15', 'end': '2023-07-15'}, 'PE', names, C.ROOT)
    assert mixed['state'] == C.UNKNOWN and 'zone' in mixed['needs'][0]
    outside = C.calendar_constraint('Zea mays', {'start': '2023-04-15', 'end': '2023-05-15'}, 'PE', names, C.ROOT)
    assert outside['state'] == C.PROHIBITED and len(outside['evidence']) == 9
    assert all(e['file'].endswith('agronomy-calendar-PE.parquet') and e['sha256'] for e in outside['evidence'])
    unmapped = C.calendar_constraint('Triticum aestivum', {'start': '2023-04-15', 'end': '2023-05-15'}, 'PE', names, C.ROOT)
    assert unmapped['state'] == C.UNKNOWN


def test_integration_feasible_with_declarations(declared):
    r = C.optimize_with_evidence(declared)
    assert r['missing'] == [] and r['status'] == 'feasible' and r['recommendation'] is None
    opt = r['optimizer']
    assert all(s[0] != s[1] for s in (f['sequence'] for f in opt['feasible']))  # declared no-repeat rule
    assert opt['best']['metrics']['min_irrigation'] == 110
    assert r == C.optimize_with_evidence(declared)


def test_prohibited_excludes_without_blocking(declared):
    declared['parcel']['soil']['ph'] = 3.0  # below every candidate's EcoCrop phmin
    declared['farmer']['soil_nutrients'] = {}  # unknown nutrients, but pH already prohibits
    r = C.optimize_with_evidence(declared)
    assert r['missing'] == [] and r['status'] == 'infeasible'
    assert all('soil_nutrients forbidden' in ' '.join(d['reasons']) for d in r['optimizer']['discarded'])


def test_unknown_transition_abstains(declared):
    del declared['farmer']['transitions']['Zea mays']['Glycine max']
    r = C.optimize_with_evidence(declared)
    assert r['status'] == 'abstained' and any('Zea mays -> Glycine max' in m for m in r['missing'])


def test_water_declared_vs_required(declared):
    declared['farmer']['water_available'][1]['value'] = 10
    r = C.optimize_with_evidence(declared)
    assert r['status'] == 'infeasible'
    assert r['constraints']['crops']['Zea mays'][1]['water']['state'] == C.PROHIBITED


def test_cycle_rules(declared):
    declared['farmer']['cycle']['Zea mays']['value'] = 10  # below EcoCrop gmin=65 → conflict, not accepted
    b = C.build_constraints(declared)
    assert b['crops']['Zea mays'][0]['cycle']['state'] == C.UNKNOWN
    short = copy.deepcopy(declared)
    short['seasons'] = [{'start': '2023-03-01', 'end': '2023-03-31'}, {'start': '2023-07-01', 'end': '2023-11-30'}]
    b = C.build_constraints(short)
    assert b['crops']['Zea mays'][0]['cycle']['state'] == C.PROHIBITED  # 31 days < gmin


def test_invalid_request_abstains(real):
    real['farmer']['invented'] = 1
    r = C.optimize_with_evidence(real)
    assert r['status'] == 'abstained' and r['missing'][0].startswith('invalid request')
