import json
from pathlib import Path
import pandas as pd
import pytest
from src import rotation_scores as S
from src.climate_profile import monthly_profile, daily_series
from src.crop_library import build_library

PIURA = (-5.24, -79.45)
IOWA = (42.03, -93.62)


@pytest.fixture(scope='module')
def library():
    return build_library()


def test_pareto_front_is_real():
    rows = [dict(sequence=['a'], water=10, soil=10, risk=10),
            dict(sequence=['b'], water=20, soil=20, risk=20),   # dominates a
            dict(sequence=['c'], water=30, soil=5, risk=5)]     # not dominated: best on water
    front = S.pareto_front(rows)
    assert {r['sequence'][0] for r in front} == {'b', 'c'}
    equal = [dict(sequence=['a'], water=5, soil=5, risk=5), dict(sequence=['b'], water=5, soil=5, risk=5)]
    assert len(S.pareto_front(equal)) == 2  # ties dominate nobody


def test_rain_position_curve():
    bounds = [300.0, 600.0, 1000.0, 1600.0]
    assert S.rain_position(800, bounds) == 100.0          # inside the optimal range
    assert S.rain_position(250, bounds) == 0.0            # below the absolute minimum
    assert S.rain_position(1700, bounds) == 0.0
    assert S.rain_position(300, bounds) == 50.0           # at the absolute bound
    assert 50 < S.rain_position(450, bounds) < 100


def test_window_choice_matches_the_climate(library):
    """Iowa can only start in the warm season; Piura has no frost, so the earliest start wins the tie."""
    for point, expected in [(IOWA, 'may'), (PIURA, 'ene')]:
        profile, meta = monthly_profile(*point)
        frame, _ = daily_series(*point)
        frost = {c.crop_key: ({} if pd.isna(c.killing_temperature_c)
                              else S.frost_days_by_month(frame, float(c.killing_temperature_c)))
                 for c in library.itertuples()}
        name, counts = S.choose_window(profile, library, meta['elevation_m'], frost)
        assert name == expected
        if point == IOWA:
            assert counts['ene']['eligible'] < counts['may']['eligible']


def test_campaign_months_follow_the_cycle():
    assert S.campaign_months(1, 90) == [1, 2, 3]
    assert S.campaign_months(11, 100) == [11, 12, 1, 2]  # wraps into the next year
    assert S.campaign_months(1, 400) is None and S.campaign_months(1, float('nan')) is None


def test_huancabamba_common_sense(library):
    """Potato and tarwi grow in Huancabamba. Cassava's EcoCrop limit is 2000 m: with the SRTM point
    elevation (1921 m) it passes; with the MERRA-2 cell average (2038 m) it did not. The data decide."""
    result = S.score_point(*PIURA)
    state = {r['crop_key']: r for r in result['eligibility']}
    assert state['potato']['state'] == 'eligible' and state['tarwi']['state'] == 'eligible'
    assert state['tarwi']['months'] == [1, 2, 3, 4, 5]  # 150-day minimum cycle, not a fixed 4-month block
    elevation = result['point']['elevation_for_suitability']
    assert elevation['source'].startswith('NASA SRTMGL1') and 1800 < elevation['value_m'] < 2000
    assert state['cassava']['state'] == 'eligible'


def test_suitability_falls_back_to_merra2_without_tile(tmp_path, monkeypatch):
    monkeypatch.setattr(S, 'point_elevation', lambda *a, **k: None)
    result = S.score_point(*IOWA)
    assert result['point']['elevation_for_suitability']['source'].startswith('MERRA-2')


def test_drought_share_counts_dry_campaigns():
    days = pd.date_range('2000-01-01', '2009-12-31')
    rain = [0.0 if (d.year in (2001, 2005) and d.month in (1, 2)) else 1.0 for d in days]
    frame = pd.DataFrame(dict(fecha=days, PRECTOTCORR=rain))
    assert S.drought_share(frame, [1, 2]) == 0.2  # 2 of 10 campaigns with no rain
    assert S.drought_share(frame, []) is None
    totals = S.campaign_rain_by_year(frame, [12, 1])  # crosses the year: belongs to the start year
    assert 2009 not in totals.index and 1999 not in totals.index  # incomplete campaigns are dropped


def test_unknown_never_counts_as_eligible(library):
    result = S.score_point(*PIURA)
    unknown = [r for r in result['eligibility'] if r['state'] == 'unknown']
    assert unknown and all(r['crop_key'] not in result['eligible'] for r in unknown)
    assert all('killing_temperature_c' in r['missing'] for r in unknown if r['crop_key'] in {'maize', 'soybean', 'rice'})


def test_rotations_respect_family_change(library):
    result = S.score_point(*PIURA)
    families = dict(zip(library.crop_key, library.family))
    for row in result['front']:
        chain = [families[c] for c in row['sequence']]
        assert len(set(chain)) == 3  # three campaigns that repeat: the last one meets the first
        assert len(set(row['sequence'])) == 3


def test_family_rule_includes_the_wrap():
    assert S.families_ok(['Gramineae', 'Leguminosae', 'Solanaceae'])
    assert not S.families_ok(['Gramineae', 'Leguminosae', 'Gramineae'])  # last crop meets the first
    assert not S.families_ok(['Gramineae', 'Gramineae', None])  # one fallow does not separate two crops in a 3-ring
    assert S.families_ok(['Gramineae', 'Leguminosae', None])


def test_fallow_routes_are_ranked_apart():
    result = S.score_point(*IOWA)
    for route in result['routes'].values():
        if route:assert S.FALLOW not in route['sequence']
    fallow = [r for r in result['routes_with_fallow'].values() if r]
    assert fallow and all(S.FALLOW in r['sequence'] and r['cropped_campaigns'] == 2 for r in fallow)


def test_routes_have_different_crop_sets():
    result = S.score_point(*IOWA)
    sets = [frozenset(r['sequence']) for r in result['routes'].values() if r]
    assert sets and len(set(sets)) == len(sets)
    assert all('from_pareto_front' in r for r in result['routes'].values() if r)


def test_scores_and_methods_are_reported():
    result = S.score_point(*PIURA)
    assert result['status'] == 'scored' and result['disclaimer'].startswith('solo tamizaje')
    for crop, score in result['crop_scores'].items():
        assert score['water'] is None or 0 <= score['water'] <= 100
        assert 0 <= score['risk'] <= 100 and score['water_method'] and score['risk_method']
    assert any('Kc' in m for score in result['crop_scores'].values() for m in [score['water_method']])


def test_crops_without_kc_never_rank_on_water():
    """Missing Kc is unknown water: not zero, not EcoCrop, and the rotation stays out of the routes."""
    result = S.score_point(*IOWA)
    no_kc = {c for c, s in result['crop_scores'].items() if s['water'] is None}
    assert no_kc and all('sin Kc' in result['crop_scores'][c]['water_method'] for c in no_kc)
    for route in result['routes'].values():
        if route:assert not set(route['sequence']) & no_kc
    assert all(r['water'] is not None for r in result['front'])
    assert result['unknown_water']['rotations'] == result['rotations'] - result['rotations_known_water']
    assert len(result['simplifications']) >= 5


def test_soil_score_counts_documented_facts(library):
    legume_rotation = ['alfalfa', 'potato', 'clover_red']
    score, detail = S.soil_score(legume_rotation, library)
    assert score == 100 and any('Leguminosae' in d for d in detail)
    grass_only = ['wheat', 'potato', 'barley']
    low, _ = S.soil_score(grass_only, library)
    assert low < score  # no legume


def test_exports_written():
    path = Path('data/processed/routes_iowa.json')
    if not path.exists():pytest.skip('rutas no generadas: corre scripts/rotation_routes.py')
    data = json.loads(path.read_text())
    assert data['status'] == 'scored' and len(data['routes']) == 3 and data['window'] == 'inicio may'
