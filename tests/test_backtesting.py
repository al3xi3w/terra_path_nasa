from types import SimpleNamespace
import pandas as pd
import pytest
from src import backtesting as B
from src import rotation_scores as S
from src.climate_profile import annual_series

IOWA = ('iowa', 42.03, -93.62, 'Iowa central (US)')


def crop(**kw):
    base = dict(crop_key='x', killing_temperature_c=0.0, kc_mid=1.0, annual_rain_opt_min_mm=500.0)
    base.update(kw)
    return SimpleNamespace(**base)


def test_missing_inputs_stay_null_never_zero():
    climate = dict(rain_mm=100.0, et0_mm=300.0, t_min=[-1.0, 2.0, -3.0])
    full = B.crop_year(crop(), climate, 400.0)
    assert full == dict(crop='x', frost_days=2, deficit_mm=200.0, rain_below_opt=True)
    unknown = B.crop_year(crop(killing_temperature_c=float('nan'), kc_mid=float('nan'), annual_rain_opt_min_mm=float('nan')),
                          climate, 400.0)
    assert unknown['frost_days'] is None and unknown['deficit_mm'] is None and unknown['rain_below_opt'] is None
    gap = B.crop_year(crop(), dict(rain_mm=None, et0_mm=None, t_min=None), None)
    assert gap['frost_days'] is None and gap['deficit_mm'] is None and gap['rain_below_opt'] is None


def test_deficit_is_never_negative():
    assert B.crop_year(crop(), dict(rain_mm=500.0, et0_mm=100.0, t_min=[5.0]), 900.0)['deficit_mm'] == 0.0


def test_total_is_null_when_any_year_is_unknown():
    years = [dict(m=1), dict(m=None), dict(m=2)]
    assert B.total(years, 'm') == dict(total=None, known_years=2, years=3)
    assert B.total([dict(m=True), dict(m=False), dict(m=True)], 'm')['total'] == 2


def test_compare_full_and_paired():
    route = [dict(m=None), dict(m=10.0), dict(m=0.0)]
    mono = [dict(m=5.0), dict(m=20.0), dict(m=1.0)]
    c = B.compare(route, mono, 'm')
    assert c['verdict'] == 'desconocido'  # route misses a year: no full-period verdict
    assert c['paired'] == dict(years=2, route=10.0, monoculture=21.0, verdict='menos')
    assert B.compare([dict(m=0)], [dict(m=0)], 'm')['verdict'] == 'igual'
    assert B.compare([dict(m=None)], [dict(m=1)], 'm')['paired'] is None


def test_window_climate_requires_every_day():
    days = pd.date_range('2016-01-01', '2016-02-29')
    frame = pd.DataFrame(dict(fecha=days, PRECTOTCORR=1.0, et0_mm=2.0, T2M_MIN=5.0))
    out = B.window_climate(frame, [1, 2], [2016])
    assert out[2016]['rain_mm'] == 60.0 and out[2016]['et0_mm'] == 120.0 and len(out[2016]['t_min']) == 60
    gap = B.window_climate(frame.drop(index=10), [1, 2], [2016])[2016]
    assert gap == dict(rain_mm=None, et0_mm=None, t_min=None)
    no_et0 = B.window_climate(frame.assign(et0_mm=[None] + [2.0] * 59), [1, 2], [2016])[2016]
    assert no_et0['et0_mm'] is None and no_et0['rain_mm'] == 60.0


def test_plan_cycles_crops_over_the_test_years():
    library = pd.DataFrame([dict(crop_key=k, killing_temperature_c=0.0, kc_mid=None, annual_rain_opt_min_mm=None) for k in 'abc'])
    by_year = {y: dict(rain_mm=1.0, et0_mm=1.0, t_min=[1.0]) for y in B.TEST_YEARS}
    years = B.plan_years(['a', 'b', 'c'], library, {'a': by_year, 'b': by_year, 'c': None}, {})
    assert all(y['frost_days'] is None for y in years if y['crop'] == 'c')  # no campaign months: unknown, not zero
    assert [y['crop'] for y in years] == list('abc') * 3  # 9 years = 3 full cycles


def test_calibration_uses_only_the_calibration_period():
    result = S.score_point(*IOWA[1:3], start=B.CALIBRATION[0], end=B.CALIBRATION[1])
    assert result['point']['climate_period_used'] == ['1981-01-01', '2015-12-31']


def test_weights_default_keeps_original_selection():
    rows = [dict(sequence=['a', 'b', 'c'], water=90, soil=60, risk=50),
            dict(sequence=['a', 'b', 'd'], water=90, soil=40, risk=80)]
    assert S.pick_routes(rows, rows)['ruta_agua']['sequence'] == ['a', 'b', 'd']  # equal-weight tie-break: 210 > 200
    heavy_soil = dict(water=1, soil=10, risk=1)
    assert S.pick_routes(rows, rows, heavy_soil)['ruta_agua']['sequence'] == ['a', 'b', 'c']


@pytest.fixture(scope='module')
def iowa():
    return B.backtest_point(*IOWA)


def test_iowa_backtest_shape_and_provenance(iowa):
    assert iowa['status'] == 'tested'
    prov = iowa['provenance']
    assert prov['power']['sha256'] and prov['power']['file'].startswith('data/raw/power/')
    assert prov['annual_rain']['sha256'] and prov['annual_rain']['file'] == 'data/processed/climate_annual_iowa.csv'
    assert set(prov['power']['variables']) == {'T2M_MIN', 'PRECTOTCORR', 'et0_mm'}
    for route in iowa['routes'].values():
        if route:assert [y['year'] for y in route['years']] == B.TEST_YEARS
    assert set(iowa['monocultures']) == set(iowa['eligibility_in_calibration'])
    typical = iowa['typical_monoculture']
    assert typical['crop'] == 'maize' and typical['status'] == 'declared_from_source'
    assert typical['source']['sha256'] and typical['source']['element'].startswith('Area harvested')
    assert typical['evidence']['mean_area_ha'] > typical['evidence']['runner_up']['mean_area_ha']


def test_crops_without_data_stay_unknown(iowa):
    """Maize has no EcoCrop killing temperature: frost against it is unknown, never zero."""
    assert all(y['frost_days'] is None for y in iowa['monocultures']['maize'])
    assert all(y['deficit_mm'] is None for y in iowa['monocultures']['clover_red'])  # no FAO-56 Kc
    route = iowa['comparisons']['ruta_agua']['maize']
    assert route['frost_days']['verdict'] == 'desconocido'


def test_routes_only_use_crops_with_kc(iowa):
    """Since water is scored only with FAO-56 Kc, every route deficit is known over the test period."""
    for name, route in iowa['routes'].items():
        if route is None:continue
        assert all(y['deficit_mm'] is not None for y in route['years']), name
        assert iowa['comparisons'][name]['maize']['deficit_mm']['verdict'] in {'menos', 'igual', 'más'}


def test_rain_flag_agrees_with_annual_csv(iowa):
    """The rain metric reads climate_annual_<pilot>.csv; it must match the POWER series it was built from."""
    annual, _ = annual_series(*IOWA[1:3])
    rain = dict(zip(annual.year, annual.rain_mm))
    for y in iowa['monocultures']['alfalfa']:
        assert y['rain_below_opt'] == (rain[y['year']] < 600.0)  # alfalfa EcoCrop optimal minimum
