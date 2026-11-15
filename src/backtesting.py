"""Out-of-sample backtest of the 3 routes: calibrate on 1981-2015, test on 2016-2024.

Question: in the test years, did the route calibrated on the past have fewer frost days and less
water deficit than a monoculture at the same point?

Design, all reported in the output:
- Calibration re-runs src/rotation_scores.score_point with the climate cut at 2015-12-31. The
  routes, the window and the eligible crops come only from 1981-2015 (ET0 from 1984-2015, because
  POWER's solar radiation starts in 1984).
- Test: the route is planted as written, one campaign per year in the calibrated window, cycling
  through its three crops. 2016-2024 is nine years, three full cycles, so each crop is counted
  exactly three times and the starting crop does not change the totals.
- A monoculture is the same crop every year in the same window. There is no local source for the
  pilot's *typical* crop (local FAOSTAT has yield only, no harvested area; NASS covers Fresno
  wheat only), so every library crop is evaluated as a monoculture and the typical one is read
  from config/backtesting_baseline.json, where it stays null until a human declares it.

Metrics per test year, each null when its inputs are missing (never zero):
- frost_days: days in the window with T2M_MIN below the crop's own EcoCrop killing temperature.
- deficit_mm: max(0, Kc_mid x ET0 - rain) over the window, the same screening formula the water
  score uses. Needs FAO-56 Kc, so it exists for 5 crops only.
- rain_below_opt: annual rain (climate_annual_<pilot>.csv) below the crop's EcoCrop optimal
  minimum. The proxy the water score itself uses for crops without Kc.

A total over the test period exists only when every year is known. When some years are missing,
the comparison is also given over the paired years where both sides are known, and labelled so.
"""
import json
from pathlib import Path
import pandas as pd
from .pipeline import ROOT, digest
from .climate_profile import daily_series, pilots
from .crop_library import build_library
from .rotation_scores import score_point

CALIBRATION = ('1981-01-01', '2015-12-31')
TEST_YEARS = list(range(2016, 2025))
BASELINE_CONFIG = 'config/backtesting_baseline.json'
METRICS = ('frost_days', 'deficit_mm', 'rain_below_opt')


def window_climate(frame, months, years):
    """Per test year: window rain, ET0 and the window's daily T2M_MIN, or None if any window day is missing."""
    d = frame.assign(year=frame.fecha.dt.year, month=frame.fecha.dt.month)
    out = {}
    for year in years:
        days = d[(d.year == year) & d.month.isin(months)]
        expected = sum(pd.Period(f'{year}-{m:02d}').days_in_month for m in months)
        complete = len(days) == expected
        out[year] = dict(
            rain_mm=float(days.PRECTOTCORR.sum()) if complete and days.PRECTOTCORR.notna().all() else None,
            et0_mm=float(days.et0_mm.sum()) if complete and days.et0_mm.notna().all() else None,
            t_min=days.T2M_MIN.tolist() if complete and days.T2M_MIN.notna().all() else None)
    return out


def crop_year(crop, climate, annual_rain_mm):
    """The three metrics for one crop in one test year. Missing input -> None."""
    killing = crop.killing_temperature_c
    frost = None if pd.isna(killing) or climate['t_min'] is None else int(sum(t < float(killing) for t in climate['t_min']))
    deficit = None
    if pd.notna(crop.kc_mid) and climate['et0_mm'] is not None and climate['rain_mm'] is not None:
        deficit = round(max(0.0, float(crop.kc_mid) * climate['et0_mm'] - climate['rain_mm']), 1)
    opt_min = crop.annual_rain_opt_min_mm
    below = None if pd.isna(opt_min) or annual_rain_mm is None or pd.isna(annual_rain_mm) else bool(annual_rain_mm < float(opt_min))
    return dict(crop=crop.crop_key, frost_days=frost, deficit_mm=deficit, rain_below_opt=below)


NO_CLIMATE = dict(rain_mm=None, et0_mm=None, t_min=None)


def plan_years(plan, library, climate, annual_rain):
    """Metrics year by year for a sequence of crops cycled over the test years.

    `climate` maps crop -> {year: window climate}, because each crop is evaluated over its own
    campaign months. A crop without known months has no climate: its metrics stay null."""
    rows = {c.crop_key: c for c in library.itertuples()}
    years = TEST_YEARS
    return [dict(year=year, **crop_year(rows[plan[i % len(plan)]], (climate.get(plan[i % len(plan)]) or {}).get(year, NO_CLIMATE),
                                        annual_rain.get(year)))
            for i, year in enumerate(years)]


def total(years, metric):
    """Sum over all years, or None when any year is unknown. Booleans count as years."""
    values = [y[metric] for y in years]
    known = [v for v in values if v is not None]
    return dict(total=None if len(known) < len(values) else round(float(sum(known)), 1),
                known_years=len(known), years=len(values))


def compare(route_years, mono_years, metric):
    """Route vs monoculture on one metric: full-period verdict plus the paired-year comparison."""
    r, m = total(route_years, metric), total(mono_years, metric)
    if r['total'] is None or m['total'] is None:
        verdict = 'desconocido'
    else:
        verdict = 'menos' if r['total'] < m['total'] else ('igual' if r['total'] == m['total'] else 'más')
    pairs = [(a[metric], b[metric]) for a, b in zip(route_years, mono_years) if a[metric] is not None and b[metric] is not None]
    paired = None
    if pairs:
        ra, mb = sum(float(a) for a, _ in pairs), sum(float(b) for _, b in pairs)
        paired = dict(years=len(pairs), route=round(ra, 1), monoculture=round(mb, 1),
                      verdict='menos' if ra < mb else ('igual' if ra == mb else 'más'))
    return dict(route=r, monoculture=m, verdict=verdict, paired=paired)


def annual_rain_by_year(pilot_name, root=ROOT):
    path = Path(root) / 'data/processed' / f'climate_annual_{pilot_name}.csv'
    table = pd.read_csv(path)
    return {int(r.year): (None if pd.isna(r.rain_mm) else float(r.rain_mm)) for r in table.itertuples()}, dict(
        file=str(path.relative_to(Path(root))), sha256=digest(path), variable='rain_mm', unit='mm/year')


def baseline_source(root=ROOT):
    path = Path(root) / BASELINE_CONFIG
    return json.loads(path.read_text()).get('source') if path.exists() else None


def declared_baseline(root=ROOT):
    path = Path(root) / BASELINE_CONFIG
    if not path.exists():return {}
    return {k: v for k, v in json.loads(path.read_text())['pilots'].items()}


def backtest_point(name, latitude, longitude, label=None, root=ROOT):
    calibrated = score_point(latitude, longitude, label, root, start=CALIBRATION[0], end=CALIBRATION[1])
    base = dict(pilot=name, label=label, calibration=list(CALIBRATION), test_years=[TEST_YEARS[0], TEST_YEARS[-1]],
                disclaimer='solo tamizaje; no es una recomendación agronómica')
    if calibrated['status'] != 'scored' or not any(calibrated['routes'].values()):
        return dict(status=f"calibration_{calibrated['status']}", reason=calibrated.get('reason'), **base)
    library = build_library(root)
    frame, meta = daily_series(latitude, longitude, root)
    months = calibrated['window_months']
    months_of = {e['crop_key']: e['months'] for e in calibrated['eligibility']}
    by_months = {tuple(m): window_climate(frame, m, TEST_YEARS) for m in months_of.values() if m}
    climate = {c: (by_months[tuple(m)] if m else None) for c, m in months_of.items()}
    annual_rain, annual_source = annual_rain_by_year(name, root)
    routes = {}
    for route_name, route in calibrated['routes'].items():
        if route is None:routes[route_name] = None;continue
        routes[route_name] = dict(sequence=route['sequence'], from_pareto_front=route['from_pareto_front'],
                                  calibration_scores={k: route[k] for k in ('water', 'soil', 'risk')},
                                  years=plan_years(route['sequence'], library, climate, annual_rain))
    monocultures = {c: plan_years([c], library, climate, annual_rain) for c in library.crop_key}
    comparisons = {route_name: {crop: {m: compare(route['years'], mono, m) for m in METRICS}
                                for crop, mono in monocultures.items()}
                   for route_name, route in routes.items() if route is not None}
    declared = declared_baseline(root).get(name) or {}
    typical = declared.get('monoculture')
    full = score_point(latitude, longitude, label, root)
    same = {k: (sorted(full['routes'][k]['sequence']) == sorted(calibrated['routes'][k]['sequence'])
                if full.get('routes') and full['routes'].get(k) and calibrated['routes'].get(k) else None)
            for k in calibrated['routes']}
    return dict(status='tested', **base, window=calibrated['window'], window_months=months, crop_months=months_of,
                eligible_in_calibration=calibrated['eligible'],
                eligibility_in_calibration={e['crop_key']: e['state'] for e in calibrated['eligibility']},
                routes=routes, monocultures=monocultures, comparisons=comparisons,
                typical_monoculture=dict(crop=typical, status=declared.get('status', 'not_declared'),
                                         reason=declared.get('reason'), evidence=declared.get('evidence'),
                                         source=baseline_source(root)),
                calibrated_routes_match_full_period=same,
                provenance=dict(power=dict(source='NASA POWER daily point export', file=meta['file'], sha256=meta['sha256'],
                                           variables={'T2M_MIN': 'C', 'PRECTOTCORR': 'mm/day',
                                                      'et0_mm': 'mm/day (FAO-56 Penman-Monteith, src/water_requirement.py)'},
                                           period=meta['period'], latitude=latitude, longitude=longitude,
                                           elevation_m=meta['elevation_m'], support=meta['support']),
                                annual_rain=annual_source,
                                crops='data/processed/crop_library.csv (EcoCrop ktmp, ropmn; FAO-56 Tabla 12 Kc_mid)'),
                method=dict(frost_days='días de la ventana con T2M_MIN bajo la temperatura letal EcoCrop del cultivo',
                            deficit_mm='max(0, Kc_mid x ET0 - lluvia) en la ventana; solo cultivos con Kc FAO-56',
                            rain_below_opt='años con lluvia anual bajo el mínimo óptimo EcoCrop del cultivo',
                            total='suma 2016-2024; nula si algún año es desconocido',
                            paired='misma suma, restringida a los años en que ambos lados se conocen'))


def backtest_pilots(root=ROOT):
    return {p['name']: backtest_point(p['name'], p['latitude'], p['longitude'], p.get('label'), root) for p in pilots(root)}
