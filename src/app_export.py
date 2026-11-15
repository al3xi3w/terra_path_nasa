"""Export the engine's real outputs for the Terrapath farmer app (app/data/app_data.js).

    python scripts/build_app.py

Everything the app shows comes from here, and everything here comes from the engine:
src/rotation_scores (routes, scores, eligibility, months), src/climate_profile (monthly climate),
src/terrain (SRTM), src/backtesting outputs and the crop library. Nothing is filled in: a value the
engine does not have is exported as null and the app says so in plain words.

Only the pilots with a local NASA POWER series exist in the app; the app never pretends to know a
place it has no data for.
"""
import json, math
from datetime import date
from pathlib import Path
import pandas as pd
from .pipeline import ROOT, digest
from .climate_profile import pilots, monthly_profile, daily_series
from .crop_library import build_library
from .rotation_scores import (score_point, water_score, risk_score, soil_score, drought_share,
                              frost_days_by_month, FALLOW, COVER)
from .terrain import terrain_table

MOUNTAIN_SLOPE_DEG = 5.0      # mean slope within 1 km above which the 50 km grid is flagged
MOUNTAIN_GAP_M = 300.0        # SRTM point vs MERRA-2 cell elevation gap that is flagged


def _num(value, digits=1):
    if value is None or (isinstance(value, float) and math.isnan(value)):return None
    return round(float(value), digits)


def first_frost(frame, profile):
    """Typical first day below 0 C in the cold season, from the daily POWER series.

    The cold season starts the month after the warmest month. Returns the median calendar date over
    the years that had a frost, and how many years had one; None when no year did."""
    warm = int(profile.loc[profile.t_mean_c.idxmax(), 'month'])
    start_month = warm % 12 + 1
    d = frame[['fecha', 'T2M_MIN']].dropna()
    firsts, seasons = [], 0
    for year in sorted(d.fecha.dt.year.unique())[:-1]:
        begin = pd.Timestamp(year=int(year), month=start_month, day=1)
        season = d[(d.fecha >= begin) & (d.fecha < begin + pd.DateOffset(years=1))]
        if len(season) < 360:continue
        seasons += 1
        cold = season[season.T2M_MIN < 0]
        if len(cold):firsts.append((cold.fecha.iloc[0] - begin).days)
    if not firsts:return dict(date=None, years_with_frost=0, seasons=seasons)
    offset = int(pd.Series(firsts).median())
    when = pd.Timestamp(year=2001, month=start_month, day=1) + pd.Timedelta(days=offset)
    return dict(month=int(when.month), day=int(when.day), years_with_frost=len(firsts), seasons=seasons)


def daily_normals(frame):
    """What a normal year looks like on each calendar day, 1981-2024 (POWER daily), for "Mi chacra".

    Index 0..365 = day of a leap year (index 59 = 29 Feb, fewer years). rain_mm, t_min_c and et0_mm are
    means over the years with data; frost is the share of those years with T2M_MIN < 0 C that day.
    These are normals, not a forecast: the app labels them "en un año normal"."""
    d = frame[['fecha', 'PRECTOTCORR', 'T2M_MIN', 'et0_mm']].copy()
    d['doy'] = pd.to_datetime(dict(year=2000, month=d.fecha.dt.month, day=d.fecha.dt.day)).dt.dayofyear - 1
    g = d.groupby('doy')
    frost = g.T2M_MIN.apply(lambda x: (x.dropna() < 0).mean() if x.notna().any() else None)
    full = range(366)
    col = lambda series, digits: [_num(series.get(i), digits) for i in full]
    return dict(rain_mm=col(g.PRECTOTCORR.mean(), 1), t_min_c=col(g.T2M_MIN.mean(), 1),
                et0_mm=col(g.et0_mm.mean(), 2), frost_share=col(frost, 2),
                period=[str(d.fecha.min().date()), str(d.fecha.max().date())],
                source='NASA POWER daily (PRECTOTCORR, T2M_MIN) and FAO-56 Penman-Monteith ET0')


def crop_view(crop, months, state, profile, frame, frost_months, library):
    """What the app needs about one crop at one place. Unknown stays None."""
    rain = demand = water = risk = deficit = None
    parts, frost_eval = {}, pd.notna(crop.killing_temperature_c)
    if months:
        window = profile[profile.month.isin(months)]
        rain = _num(window.rain_mean_mm.sum())
        if pd.notna(crop.kc_mid) and window.et0_mean_mm.notna().all():
            demand = _num(float(crop.kc_mid) * float(window.et0_mean_mm.sum()))
        water, _, deficit = water_score(crop, profile, months)
        risk, _, parts = risk_score(crop, profile, months, frost_months if frost_eval else None, drought_share(frame, months))
    soil_mono, _ = soil_score([crop.crop_key] * 3, library)
    return dict(key=crop.crop_key, scientific=crop.scientific_name, family=crop.family,
                legume=bool(crop.family_leguminosae), cover=crop.crop_key in COVER, months=months, state=state['state'],
                failed=state['failed'], missing=state['missing'],
                rain_mm=rain, demand_mm=demand, deficit_mm=_num(deficit), water=_num(water), risk=_num(risk),
                soil_monoculture=float(soil_mono), frost_evaluable=bool(frost_eval),
                killing_temperature_c=_num(crop.killing_temperature_c),
                frost_days=_num(parts.get('frost_days'), 2) if frost_eval and months else None,
                drought_share=_num(parts.get('drought_share'), 3), rain_cv=_num(parts.get('rain_cv'), 3),
                kc_mid=_num(crop.kc_mid, 2))


def route_view(route, kind):
    return dict(sequence=route['sequence'], water=route['water'], soil=route['soil'], risk=route['risk'],
                soil_detail=route['soil_detail'], kind=kind, from_pareto_front=route['from_pareto_front'],
                missing=route.get('missing', []))


def app_routes(result):
    """Up to three routes: three-crop routes first, then routes with a rest season, no duplicate crop sets."""
    out, seen = [], set()
    for group, kind in [(result.get('routes'), 'tres_cultivos'), (result.get('routes_with_fallow'), 'con_descanso')]:
        for route in (group or {}).values():
            if not route:continue
            key = frozenset(route['sequence'])
            if key in seen:continue
            seen.add(key);out.append(route_view(route, kind))
    return out[:3]


def backtest_view(root, name):
    path = Path(root) / f'data/processed/backtest_{name}.json'
    if not path.exists():return None
    b = json.loads(path.read_text())
    if b.get('status') != 'tested':return dict(status=b.get('status'))
    typical = (b.get('typical_monoculture') or {}).get('crop')
    out = []
    for route_name, route in b['routes'].items():
        if not route or not typical:continue
        c = b['comparisons'][route_name][typical]['deficit_mm']
        out.append(dict(sequence=route['sequence'], route_deficit_mm=c['route']['total'],
                        typical_deficit_mm=c['monoculture']['total'], verdict=c['verdict']))
    return dict(status='tested', typical=typical, test_years=b['test_years'], routes=out)


def pilot_view(p, root, library, terrain):
    lat, lon = p['latitude'], p['longitude']
    result = score_point(lat, lon, p.get('label'), root)
    profile, meta = monthly_profile(lat, lon, root)
    frame, _ = daily_series(lat, lon, root)
    elig = {e['crop_key']: e for e in result['eligibility']}
    crops = []
    for c in library.itertuples():
        frost = frost_days_by_month(frame, float(c.killing_temperature_c)) if pd.notna(c.killing_temperature_c) else None
        crops.append(crop_view(c, elig[c.crop_key]['months'], elig[c.crop_key], profile, frame, frost, library))
    t = terrain.get(p['name'], {})
    # Both altitudes come from the engine's point (routes_<pilot>.json): the farm (SRTM, used for
    # suitability) and the ~50 km climate cell (NASA POWER / MERRA-2 header).
    point = result['point']
    srtm = (point.get('elevation_for_suitability') or {}).get('value_m')
    merra, slope = point.get('elevation_m'), t.get('slope_mean_1km_deg')
    mountain = bool((slope is not None and slope > MOUNTAIN_SLOPE_DEG) or
                    (srtm is not None and merra is not None and abs(srtm - merra) > MOUNTAIN_GAP_M))
    monthly = [dict(month=int(r.month), frost_days=_num(r.frost_days_mean, 2), rain_mm=_num(r.rain_mean_mm),
                    et0_mm=_num(r.et0_mean_mm), t_min_c=_num(r.t_min_mean_c), t_max_c=_num(r.t_max_mean_c))
               for r in profile.itertuples()]
    return dict(id=p['name'], label=p['label'], latitude=lat, longitude=lon, status=result['status'],
                reason=result.get('reason'), start_month=result.get('window_start'),
                routes=app_routes(result), crops=crops, monthly=monthly,
                first_frost=first_frost(frame, profile), daily=daily_normals(frame),
                terrain=dict(srtm_m=_num(srtm, 0), merra2_m=_num(merra, 0), slope_mean_deg=_num(slope),
                             mountain_warning=mountain),
                backtest=backtest_view(root, p['name']),
                provenance=dict(power_file=meta['file'], power_sha256=meta['sha256'], power_period=meta['period'],
                                srtm_file=t.get('file'), srtm_sha256=t.get('sha256'),
                                routes_file=f"data/processed/routes_{p['name']}.json"))


def build(root=ROOT):
    library = build_library(root)
    terrain = {r['pilot']: r for r in terrain_table(root).to_dict('records')}
    return dict(generated=date.today().isoformat(),
                note='Datos de tamizaje del motor Terrapath (NASA POWER, SRTM, EcoCrop, FAO-56). No es una recomendación agronómica.',
                pilots=[pilot_view(p, root, library, terrain) for p in pilots(root)])


def write(root=ROOT):
    data = build(root)
    out = Path(root) / 'app/data/app_data.js'
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text('// Generado por scripts/build_app.py. No editar a mano.\nwindow.APP_DATA = '
                   + json.dumps(data, ensure_ascii=False, indent=1, default=str) + ';\n')
    sw = Path(root) / 'app/sw.js'
    if sw.exists():  # new data or app code -> new cache name, so phones drop the old copy
        import re, hashlib
        app_files = [out] + [Path(root) / 'app' / f for f in ('index.html', 'app.js', 'i18n.js', 'i18n_more.js', 'styles.css', 'manifest.webmanifest')]
        version = 'terrapath-' + hashlib.sha256(''.join(digest(f) for f in app_files if f.exists()).encode()).hexdigest()[:10]
        sw.write_text(re.sub(r"const VERSION = '[^']*';", f"const VERSION = '{version}';", sw.read_text()))
    return out, data
