import copy, json, math
from pathlib import Path
import pandas as pd
import pytest
from src import constraints as C
from src import water_requirement as W
from src.pipeline import digest

WHEAT = dict(table11_id='T11-ww-1', table12_label='Winter Wheat - with non-frozen soils', provenance='test selection')
MAIZE = dict(table11_id='T11-mz-5', table12_label='Maize, Field (grain)', provenance='test selection')


def test_et0_fao56_example_18():
    """FAO-56 Example 18 (Uccle, 6 July): ET0 = 3.9 mm/day; ea=1.409 kPa reproduced via RHmean (eq. 19)."""
    sat = lambda t: 0.6108 * math.exp(17.27 * t / (t + 237.3))
    rh = 1.409 / ((sat(21.5) + sat(12.3)) / 2) * 100
    d = pd.DataFrame(dict(fecha=[pd.Timestamp('2023-07-06')], T2M_MAX=[21.5], T2M_MIN=[12.3], RH2M=[rh], WS2M=[2.078], ALLSKY_SFC_SW_DWN=[22.07]))
    assert W.et0_penman_monteith(d, 50.8, 100).iloc[0] == pytest.approx(3.9, abs=0.05)


def test_tables_verified_and_parsing():
    t = W.verified_tables()
    assert t['pdf_sha256'] == digest(Path('data/raw/fao56/FAO56.pdf'))
    row = next(r for r in t['table11'] if r['id'] == 'T11-ww-1')
    assert [row[k] for k in ['L_ini', 'L_dev', 'L_mid', 'L_late', 'total']] == [20, 60, 70, 30, 180]  # not "202/602" footnote merges
    assert all(r['L_ini'] + r['L_dev'] + r['L_mid'] + r['L_late'] == r['total'] for r in t['table11'] if r['L_dev'] is not None)
    assert W.plant_months('March/Apr') == [3, 4] and W.plant_months('Dec/Jan') == [1, 12] and W.plant_months('35-45 °L') == []


def test_kc_curve_and_adjustment():
    k = W.kc_curve([2, 2, 2, 2], 0.3, 1.2, 0.6)
    assert k[:2] == [0.3, 0.3] and k[3] == 1.2 and k[4:6] == [1.2, 1.2] and k[7] == pytest.approx(0.6)
    lo, hi = W.kc_adjust_bounds(1.15, 2.0, 45.0, [1, 1])
    assert lo == pytest.approx(1.15) and hi > lo  # RHmin ≤ RHmean only raises the adjustment
    assert W.kc_adjust_bounds(None, 2, 45, [1, 1]) is None


def test_wheat_requirement_real_power():
    r = W.crop_requirement(WHEAT, '2023-12-01', 36.59, -119.52)
    assert r['status'] == 'computed' and r['total_days'] == 180
    lo, hi = r['etc_mm']
    assert 0 < lo < hi
    p = pd.read_parquet('data/processed/power_california_2021_2025.parquet')
    assert r['rainfall_mm'] == pytest.approx(p[p.fecha.between('2023-12-01', '2024-05-28')].PRECTOTCORR.sum(), abs=0.01)
    power = [e for e in r['evidence'] if e['source'] == 'NASA POWER']
    assert all(e['sha256'] == digest(Path(e['file'])) and e['period'] == '2023-12-01/2024-05-28' for e in power)
    assert power[0]['location']['elevation_m'] == 249.47


def test_annex7_example():
    """FAO-56 Annex 7 / Example 25: tw 3.5 d, ET0 5 mm/d, coarse soil, 20 mm events.

    Fig. 30a = 0.75 as printed. Fig. 29: eq. 7-3 gives 0.533; Example 25 reads ≈0.55 from the figure and
    Example 7-1 prints 0.57, an arithmetic slip (its own inputs give 0.533). Eq. 59 → 0.60 as in Example 25.
    """
    assert W.kc_ini_figure(3.5, 5, '30a') == pytest.approx(0.75, abs=0.005)
    assert W.kc_ini_figure(3.5, 5, '29') == pytest.approx(0.55, abs=0.02)
    assert W.kc_ini_interpolated(3.5, 5, 20, '30a') == pytest.approx(0.60, abs=0.01)
    assert W.kc_ini_figure(0.1, 5, '29') == 1.15 and W.kc_ini_figure(1, 1, '30b') <= 1.15  # eq. 7-4 and cap


def test_wetting_events_rules():
    # 0.2·ET0 = 1 mm threshold; adjoining wet days merge; dry day splits
    assert W.wetting_events([0.5, 3, 4, 0, 0, 10, 0.9], 5) == [7, 10]
    assert W.wetting_events([0, 0], 5) == []


def test_maize_kc_ini_computed_from_rain_and_irrigation():
    rainfed = dict(MAIZE, initial_irrigation=dict(events=[], provenance='test: no initial irrigation'))
    r = W.crop_requirement(rainfed, '2023-04-01', 36.59, -119.52)
    assert r['status'] == 'computed' and r['etc_mm'][0] < r['etc_mm'][1]
    kc = next(e for e in r['evidence'] if e['source'].startswith('FAO-56 Annex 7'))
    assert kc['value'][0] <= kc['value'][1] <= 1.15 and kc['period'] == '2023-04-01/2023-04-30'
    wet = dict(MAIZE, initial_irrigation=dict(events=[{'day': 0, 'depth_mm': 60}, {'day': 10, 'depth_mm': 40}, {'day': 20, 'depth_mm': 40}], provenance='t'))
    any_soil = W.crop_requirement(wet, '2023-04-01', 36.59, -119.52)['etc_mm']
    medium = W.crop_requirement(wet, '2023-04-01', 36.59, -119.52, texture='medium')['etc_mm']
    assert any_soil[0] <= medium[0] and medium[1] <= any_soil[1] and medium[0] > r['etc_mm'][0]  # texture narrows; irrigation raises
    bad = dict(MAIZE, initial_irrigation=dict(events=[{'day': 99, 'depth_mm': 10}], provenance='t'))
    assert W.crop_requirement(bad, '2023-04-01', 36.59, -119.52)['status'] == 'unknown'


def test_requirement_unknowns():
    assert 'Kc ini' in W.crop_requirement(MAIZE, '2023-04-01', 36.59, -119.52)['needs'][0]  # blank, nothing declared
    off = W.crop_requirement(MAIZE, '2023-06-01', 36.59, -119.52)
    assert off['status'] == 'unknown' and off['total_days'] is None  # row is for April plantings
    soy = W.crop_requirement(dict(table11_id='T11-soy-2', table12_label='Soybeans', provenance='t'), '2023-05-01', 36.59, -119.52)
    assert soy['status'] == 'unknown'  # L_dev printed "30/35"
    assert W.crop_requirement(WHEAT, '2023-12-01', 0.0, 0.0)['status'] == 'unknown'  # no series at exact coordinates
    assert W.crop_requirement({**WHEAT, 'provenance': None}, '2023-12-01', 36.59, -119.52)['status'] == 'unknown'


def test_tampered_pdf_fails_closed(monkeypatch):
    monkeypatch.setattr(W, 'digest', lambda p: 'x')
    with pytest.raises(ValueError):W.verified_tables()


def test_water_states_from_bounds():
    req = W.crop_requirement(WHEAT, '2023-12-01', 36.59, -119.52)
    lo_etc, hi_etc = req['etc_mm']
    eff, soil = 0.8, 0.0
    lower, upper = W.irrigation_bounds(req, eff, soil)
    assert lower == pytest.approx(max(0, lo_etc - req['rainfall_mm'])) and upper == pytest.approx(hi_etc / eff)
    assert C.water_constraint(upper, None, 0, req, eff, soil)[0]['state'] == C.ALLOWED
    between = C.water_constraint((lower + upper) / 2, None, 0, req, eff, soil)[0]
    assert between['state'] == C.UNKNOWN
    no_eff = C.water_constraint(10 ** 6, None, 0, req, None, soil)[0]
    assert no_eff['state'] == C.UNKNOWN and any('efficiency' in n for n in no_eff['needs'])
    if lower > 0:assert C.water_constraint(lower - 1, None, 0, req, eff, soil)[0]['state'] == C.PROHIBITED


@pytest.fixture
def wheat_request(monkeypatch):
    """Wheat-only real request: computed water feeds the optimizer; calendar forced (no US FAO calendar)."""
    monkeypatch.setattr(C, 'calendar_constraint', lambda *a: C.state(C.ALLOWED, [C.evidence('test', 'synthetic calendar gate')]))
    v = lambda x, u='mm': dict(value=x, unit=u, provenance='test declaration')
    return dict(parcel=dict(latitude=36.59, longitude=-119.52, current_crop='Triticum aestivum', previous_crops=[],
                            sowing_date='2022-12-01', horizon_end='2024-05-31', soil={'ph': 7.0},
                            candidates=[{'crop': 'Triticum aestivum'}], assumptions={'screen_season_mean_temperature': True}),
                seasons=[{'start': '2022-12-01', 'end': '2023-05-31'}, {'start': '2023-12-01', 'end': '2024-05-31'}],
                farmer=dict(country_iso2='US', fao56={'Triticum aestivum': WHEAT}, water_available=[v(2000), v(2000)],
                            irrigation_efficiency=v(0.7, 'fraction'), initial_soil_water_mm=[v(0), v(0)],
                            soil_nutrients={'Triticum aestivum': dict(allowed=True, provenance='test')},
                            transitions={'Triticum aestivum': {'Triticum aestivum': dict(allowed=True, provenance='test')}},
                            history_review=dict(allowed=True, provenance='test')),
                objectives=['min_irrigation'])


def test_integration_computed_water(wheat_request):
    r = C.optimize_with_evidence(wheat_request)
    assert r['missing'] == [] and r['status'] == 'feasible'
    best = r['optimizer']['best']
    uppers = [W.crop_requirement(WHEAT, s['start'], 36.59, -119.52)['etc_mm'][1] / 0.7 for s in wheat_request['seasons']]
    assert best['metrics']['min_irrigation'] == pytest.approx(sum(round(u, 2) for u in uppers))
    assert r['constraints']['crops']['Triticum aestivum'][0]['cycle']['evidence'][0]['source'].startswith('FAO-56 Table 11')


def test_integration_budget_below_lower_bound(wheat_request):
    wheat_request['farmer']['water_available'][1]['value'] = 0
    req = W.crop_requirement(WHEAT, '2023-12-01', 36.59, -119.52)
    assert req['etc_mm'][0] > req['rainfall_mm']  # 2023-24 data: lower bound > 0
    r = C.optimize_with_evidence(wheat_request)
    assert r['status'] == 'infeasible'
    assert r['constraints']['crops']['Triticum aestivum'][1]['water']['state'] == C.PROHIBITED


def _power_root(tmp_path, periods):
    """Copy the real export into a temporary root once per period, truncated to that period."""
    source = Path('data/raw/power/POWER_Point_Daily_20210101_20251231_036d59N_0119d52W_LST.csv')
    header, body = source.read_text().split('-END HEADER-')
    columns, *rows = body.strip().splitlines()
    (tmp_path / 'data/raw/power').mkdir(parents=True)
    for start, end in periods:
        kept = [r for r in rows if start[:4] <= r.split(',')[0] <= end[:4]]
        text = header.replace('01/01/2021 through 12/31/2025', f'01/01/{start[:4]} through 12/31/{end[:4]}')
        name = f"POWER_Point_Daily_{start}_{end}_036d59N_0119d52W_LST.csv"
        (tmp_path / 'data/raw/power' / name).write_text(f"{text}-END HEADER-\n{columns}\n" + '\n'.join(kept) + '\n')
    return tmp_path


def test_longest_power_series_wins_over_filename_order(tmp_path):
    """Two downloads of the same point must not be resolved by alphabetical filename."""
    from src.pipeline import power_csv_for
    root = _power_root(tmp_path, [('20210101', '20251231'), ('20230101', '20251231')])
    path, df, quality = power_csv_for(36.59, -119.52, root)
    assert path.name.startswith('POWER_Point_Daily_20210101') and quality['period'][0] == '2021-01-01'
    assert W.power_series(36.59, -119.52, root)[1]['period'] == ['2021-01-01', '2025-12-31']
    assert power_csv_for(0.0, 0.0, root)[0] is None


def test_identical_periods_are_refused(tmp_path):
    from src.pipeline import power_csv_for
    root = _power_root(tmp_path, [('20210101', '20251231')])
    duplicate = next((root / 'data/raw/power').glob('*.csv'))
    duplicate.with_name('copy_' + duplicate.name).write_text(duplicate.read_text())
    with pytest.raises(ValueError, match='same period'):power_csv_for(36.59, -119.52, root)
