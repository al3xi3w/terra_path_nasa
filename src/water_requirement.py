"""FAO-56 crop water requirement from local NASA POWER + visually verified FAO-56 tables.

ET0: FAO Penman-Monteith daily (eq. 6), actual vapour pressure from RHmean (eq. 19, the
FAO-accepted fallback when only mean humidity exists). ETc: single Kc curve (Tables 11–12,
eq. 66) with the eq. 62 climate adjustment expressed as bounds, because POWER gives RHmean,
not RHmin. Output is an interval [low, high], never a point estimate dressed up as exact.
Effective rainfall, initial soil water and irrigation efficiency are never assumed.
"""
import json, math, re
from pathlib import Path
import pandas as pd
from .pipeline import ROOT, digest, power_csv_for
from .parcel_scenarios import day

CONFIG = 'config/fao56_stages_verified.json'
MONTHS = {m: i + 1 for i, m in enumerate(['jan', 'feb', 'mar', 'apr', 'may', 'jun', 'jul', 'aug', 'sep', 'oct', 'nov', 'dec'])}


def verified_tables(root=ROOT):
    root = Path(root)
    data = json.loads((root / CONFIG).read_text())
    if digest(root / 'data/raw/fao56/FAO56.pdf') != data['pdf_sha256']:raise ValueError('FAO56.pdf differs from verified tables')
    return data


def plant_months(text):
    """Months named in a Table 11 'Plant Date' cell ('March/Apr', 'Dec/Jan', 'April/May')."""
    found = {MONTHS[t[:3].lower()] for t in re.split(r'[/,\s.]+', text) if t[:3].lower() in MONTHS}
    return sorted(found)


def power_series(latitude, longitude, root=ROOT):
    """Exact-coordinate POWER export (no spatial extrapolation) plus header elevation."""
    path, df, q = power_csv_for(latitude, longitude, root)
    if path is None:return None, None
    expected = {'T2M_MAX': 'C', 'T2M_MIN': 'C', 'RH2M': '%', 'WS2M': 'm/s', 'ALLSKY_SFC_SW_DWN': 'MJ/m^2/day', 'PRECTOTCORR': 'mm/day'}
    if any(q['units'][k] != v for k, v in expected.items()):raise ValueError('Unexpected POWER units')
    z = re.search(r'elevation from MERRA-2:.*?=\s*([-\d.]+)\s*meters', q['header_original'])
    return df, dict(file=str(path.relative_to(root)), sha256=digest(path), elevation_m=float(z[1]) if z else None,
                    elevation_support='MERRA-2 0.5x0.625 degree region average, not parcel elevation',
                    period=q['period'])


def et0_penman_monteith(df, latitude, elevation):
    """Daily FAO-56 PM ET0 (mm/day). Inputs: T2M_MAX/MIN (C), RH2M (%), WS2M (m/s at 2 m), Rs (MJ m-2 d-1)."""
    tmax, tmin, rh, u2, rs = df.T2M_MAX, df.T2M_MIN, df.RH2M, df.WS2M, df.ALLSKY_SFC_SW_DWN
    sat = lambda t: 0.6108 * (17.27 * t / (t + 237.3)).map(math.exp)          # eq. 11
    tmean = (tmax + tmin) / 2                                                 # eq. 9
    es = (sat(tmax) + sat(tmin)) / 2                                          # eq. 12
    ea = rh / 100 * es                                                        # eq. 19
    delta = 4098 * sat(tmean) / (tmean + 237.3) ** 2                          # eq. 13
    gamma = 0.000665 * 101.3 * ((293 - 0.0065 * elevation) / 293) ** 5.26     # eq. 7–8
    j = df.fecha.dt.dayofyear
    phi = math.radians(latitude)
    dr = 1 + 0.033 * (2 * math.pi * j / 365).map(math.cos)                    # eq. 23
    dec = 0.409 * (2 * math.pi * j / 365 - 1.39).map(math.sin)                # eq. 24
    ws = (-math.tan(phi) * dec.map(math.tan)).map(math.acos)                  # eq. 25
    ra = 24 * 60 / math.pi * 0.0820 * dr * (ws * math.sin(phi) * dec.map(math.sin)
         + math.cos(phi) * dec.map(math.cos) * ws.map(math.sin))              # eq. 21
    rso = (0.75 + 2e-5 * elevation) * ra                                      # eq. 37
    rnl = 4.903e-9 * ((tmax + 273.16) ** 4 + (tmin + 273.16) ** 4) / 2 * (0.34 - 0.14 * ea ** 0.5) \
        * (1.35 * (rs / rso).clip(upper=1.0) - 0.35)                          # eq. 39
    rn = 0.77 * rs - rnl                                                      # eq. 38, 40; G = 0 daily (eq. 42)
    return (0.408 * delta * rn + gamma * 900 / (tmean + 273) * u2 * (es - ea)) / (delta + gamma * (1 + 0.34 * u2))


def kc_adjust_bounds(kc, u2, rhmean, heights):
    """Eq. 62 adjustment as an interval. RHmin is unobserved: RHmin ≤ RHmean, limited to FAO's 20–80 %."""
    if kc is None:return None
    u = min(max(u2, 1.0), 6.0)
    rh_hi = min(max(rhmean, 20.0), 80.0)
    values = [kc + (0.04 * (u - 2) - 0.004 * (r - 45)) * (min(max(h, 0.1), 10) / 3) ** 0.3
              for r in (20.0, rh_hi) for h in heights]
    return min(values), max(values)


# ---------- Kc ini: FAO-56 Annex 7 numerical form of Figures 29–30 (PDF pp. 289–294) ----------

def kc_ini_figure(tw, et0, figure):
    """Eq. 7-1, 7-3, 7-4 with the Annex 7 parameters for Figure 29, 30a (coarse) or 30b (medium/fine)."""
    eso = 1.15 * et0                                                        # eq. 7-1
    if figure == '29':
        tew = 10.0;rew = min(max(2.5, 6 / et0 ** 0.5), 7.0)
    elif figure == '30a':
        tew = min(15.0, 7 * et0 ** 0.5);rew = min(6.0, tew - 0.01)
    elif figure == '30b':
        tew = min(28.0, 13 * et0 ** 0.5);rew = min(9.0, tew - 0.01)
    else:raise ValueError('figure must be 29, 30a or 30b')
    t1 = rew / eso
    if tw < t1:return 1.15                                                  # eq. 7-4
    k = (tew - (tew - rew) * math.exp(-(tw - t1) * eso * (1 + rew / (tew - rew)) / tew)) / (tw * et0)   # eq. 7-3
    return min(k, 1.15)


def kc_ini_interpolated(tw, et0, depth, figure30):
    """Eq. 59: light (≤10 mm) → Fig. 29; heavy (≥40 mm) → Fig. 30; linear in between."""
    k29 = kc_ini_figure(tw, et0, '29')
    if depth <= 10:return k29
    k30 = kc_ini_figure(tw, et0, figure30)
    return k30 if depth >= 40 else k29 + (depth - 10) / 30 * (k30 - k29)


def wetting_events(water, et0_mean):
    """Annex 7: daily water (rain + irrigation, mm) < 0.2·ET0 ignored; adjoining wet days form one event."""
    events, current = [], 0.0
    for w in list(water) + [0.0]:
        if w >= 0.2 * et0_mean and w > 0:current += w
        elif current:events.append(current);current = 0.0
    return events


def kc_ini_bounds(rain, et0, irrigation, texture=None):
    """Kc ini interval for the initial period from daily rainfall/ET0 and declared irrigation.

    irrigation: daily depths (mm, full-surface wetting fw = 1) aligned with rain; zeros = no irrigation.
    Infiltrated rain is unknown (runoff), so two scenarios bracket it: rain fully infiltrated and rain
    ignored (irrigation only). In each, eq. 59 (Fig. 29 ↔ Fig. 30a/30b, both if texture unknown) is
    evaluated; the interval is their envelope.
    """
    et0_mean = float(sum(et0) / len(et0))
    irr = list(irrigation) + [0.0] * (len(rain) - len(irrigation))
    figures = {'coarse': ['30a'], 'medium': ['30b'], 'fine': ['30b']}.get(texture, ['30a', '30b'])
    values, scenarios = [], {}
    for name, water in [('rain_infiltrated', [r + i for r, i in zip(rain, irr)]), ('rain_ignored', irr)]:
        events = wetting_events(water, et0_mean)
        nw = len(events);tw = len(rain) / (nw + 0.5)                       # eq. 7-7
        depth = sum(events) / nw if nw else 0.0                            # eq. 7-8
        values += [kc_ini_interpolated(tw, et0_mean, depth, f) for f in figures]  # eq. 59 equals Fig. 29 when depth ≤ 10 mm
        scenarios[name] = dict(events=nw, tw_days=round(tw, 2), mean_depth_mm=round(depth, 2))
    return dict(low=round(min(values), 3), high=round(max(values), 3), scenarios=scenarios,
                et0_mean_mm_d=round(et0_mean, 3), figures=['29'] + figures)


def kc_curve(lengths, kc_ini, kc_mid, kc_end):
    """Eq. 66 piecewise-linear daily Kc for days 1..total."""
    li, ld, lm, ll = lengths;out = []
    for i in range(1, li + ld + lm + ll + 1):
        if i <= li:out.append(kc_ini)
        elif i <= li + ld:out.append(kc_ini + (i - li) / ld * (kc_mid - kc_ini))
        elif i <= li + ld + lm:out.append(kc_mid)
        else:out.append(kc_mid + (i - li - ld - lm) / ll * (kc_end - kc_mid))
    return out


def crop_requirement(selection, planting, latitude, longitude, root=ROOT, texture=None):
    """ETc interval and rainfall for one crop planted on `planting`, from an explicit FAO-56 selection.

    selection: {'table11_id', 'table12_label', optional 'kc_ini': {value, provenance},
    optional 'kc_end': {value, provenance}, optional 'initial_irrigation': {events: [{day, depth_mm}], provenance}
    (used to compute a blank Table 12 Kc ini with Annex 7), 'provenance'} — the crop ↔ FAO-56 row choice is declared.
    texture: parcel soil texture 'coarse' | 'medium' | 'fine' (selects Fig. 30a/30b); None → both, as an interval.
    Returns dict(status, etc_mm=[lo, hi], rainfall_mm, total_days, evidence, needs).
    """
    needs, tables = [], verified_tables(root)
    ev = [dict(source='FAO-56 selection (declared)', reason=selection.get('provenance'), variable='table11_id/table12_label',
               value=[selection.get('table11_id'), selection.get('table12_label')])]
    row = next((r for r in tables['table11'] if r['id'] == selection.get('table11_id')), None)
    kc = next((r for r in tables['table12'] if r['crop_label'] == selection.get('table12_label')), None)
    if not selection.get('provenance') or row is None or kc is None:
        return dict(status='unknown', needs=['valid declared FAO-56 Table 11 row and Table 12 label'], evidence=ev)
    lengths = [row['L_ini'], row['L_dev'], row['L_mid'], row['L_late']]
    page = dict(source='FAO-56', file=CONFIG, sha256=tables['pdf_sha256'])
    ev.append({**page, 'reason': f"Table 11 row {row['id']} ({row['plant_date']}, {row['region'] or 'no region'}), PDF p.{row['pdf_page']}",
               'variable': 'L_ini/L_dev/L_mid/L_late', 'unit': 'day', 'value': lengths})
    if None in lengths or sum(lengths) != row['total']:
        return dict(status='unknown', needs=[f"usable stage lengths ({row['notes']})"], evidence=ev, total_days=None)
    if day(planting).month not in plant_months(row['plant_date']):
        # Stage lengths are tied to the row's planting period; not applicable (no cycle either).
        return dict(status='unknown', evidence=ev, total_days=None,
                    needs=[f"Table 11 row whose plant date ({row['plant_date']}) includes planting month {day(planting).month}"])
    kc_ini = kc['kc_initial'];kc_ini_source = 'Table 12'
    irrigation = selection.get('initial_irrigation')
    if kc_ini is None:
        d = selection.get('kc_ini')
        if isinstance(d, dict) and d.get('provenance') and isinstance(d.get('value'), (int, float)):
            kc_ini, kc_ini_source = d['value'], 'declared'
        elif not (isinstance(irrigation, dict) and irrigation.get('provenance') and isinstance(irrigation.get('events'), list)):
            needs.append(f"initial-stage irrigation events (day after planting, mm; [] if none) to compute Kc ini of {kc['crop_label']} "
                         "with FAO-56 Annex 7 (Table 12 blank), or a declared Kc ini")
        else:
            kc_ini_source = 'Annex 7'
    end_lo, end_hi = kc['kc_end']
    d = selection.get('kc_end')
    if isinstance(d, dict) and d.get('provenance') and isinstance(d.get('value'), (int, float)):
        if not end_lo <= d['value'] <= end_hi:needs.append('declared Kc end outside Table 12 range')
        end_lo = end_hi = d['value']
    ev.append({**page, 'reason': f"Table 12 '{kc['crop_label']}', PDF p.{kc['pdf_page']}: {kc['notes']}", 'variable': 'Kc ini/mid/end, h',
               'unit': 'dimensionless, m', 'value': [kc['kc_initial'], kc['kc_mid'], kc['kc_end'], kc['max_height_m']]})
    df, meta = power_series(latitude, longitude, root)
    if df is None:
        return dict(status='unknown', needs=needs + ['NASA POWER series at exact parcel coordinates'], evidence=ev, total_days=row['total'])
    dates = pd.date_range(day(planting), periods=row['total'])
    d = df[df.fecha.isin(dates)].sort_values('fecha')
    cols = ['T2M_MAX', 'T2M_MIN', 'RH2M', 'WS2M', 'ALLSKY_SFC_SW_DWN', 'PRECTOTCORR']
    if len(d) != len(dates) or d.fecha.duplicated().any() or d[cols].isna().any().any() or meta['elevation_m'] is None:
        return dict(status='unknown', needs=needs + [f'complete POWER days {dates[0].date()}–{dates[-1].date()} and elevation'],
                    evidence=ev, total_days=row['total'])
    et0 = et0_penman_monteith(d, latitude, meta['elevation_m'])
    period = f'{dates[0].date()}/{dates[-1].date()}'
    ev.append(dict(source='NASA POWER', file=meta['file'], sha256=meta['sha256'], variable='ET0 (FAO-56 PM, ea from RHmean)', unit='mm',
                   period=period, location=dict(latitude=latitude, longitude=longitude, elevation_m=meta['elevation_m'],
                   elevation_support=meta['elevation_support']), value=round(float(et0.sum()), 2),
                   reason='inputs T2M_MAX, T2M_MIN, RH2M, WS2M, ALLSKY_SFC_SW_DWN; G=0; albedo 0.23'))
    if needs:return dict(status='unknown', needs=needs, evidence=ev, total_days=row['total'])
    li, ld, lm, ll = lengths
    if kc_ini_source == 'Annex 7':
        daily = [0.0] * li
        for e in irrigation['events']:
            if not (isinstance(e, dict) and isinstance(e.get('day'), int) and 0 <= e['day'] < li and isinstance(e.get('depth_mm'), (int, float)) and e['depth_mm'] >= 0):
                return dict(status='unknown', needs=['valid initial irrigation events: {day: 0..L_ini-1, depth_mm ≥ 0}, full-surface wetting'],
                            evidence=ev, total_days=row['total'])
            daily[e['day']] += e['depth_mm']
        b = kc_ini_bounds(d.PRECTOTCORR.iloc[:li].tolist(), et0.iloc[:li].tolist(), daily, texture)
        kc_ini = (b['low'], b['high'])
        ev.append(dict(source='FAO-56 Annex 7 (eq. 7-1…7-8, 59)', file=meta['file'], sha256=meta['sha256'], period=f"{dates[0].date()}/{dates[li - 1].date()}",
                       variable='Kc ini [lo, hi]', unit='dimensionless', value=[b['low'], b['high']],
                       reason=f"wetting scenarios {b['scenarios']} (POWER rain + declared irrigation: {irrigation['provenance']}); "
                              f"ET0 {b['et0_mean_mm_d']} mm/d; figures {b['figures']}; envelope over rain infiltrated/ignored; "
                              'furrow/trickle partial wetting not supported'))
    else:
        kc_ini = (kc_ini, kc_ini)
    mid = d.iloc[li + ld:li + ld + lm];late = d.iloc[li + ld + lm:]
    h = kc['max_height_m']
    mid_b = kc_adjust_bounds(kc['kc_mid'], mid.WS2M.mean(), mid.RH2M.mean(), h)
    # FAO-56: no eq. 62 adjustment when Kc end < 0.45.
    end_b = [kc_adjust_bounds(e, late.WS2M.mean(), late.RH2M.mean(), h) if e >= 0.45 else (e, e) for e in (end_lo, end_hi)]
    lo = kc_curve(lengths, kc_ini[0], mid_b[0], end_b[0][0]);hi = kc_curve(lengths, kc_ini[1], mid_b[1], end_b[1][1])
    etc = [float((et0.values * pd.Series(k).values).sum()) for k in (lo, hi)]
    rain = float(d.PRECTOTCORR.sum())
    ev.append(dict(source='FAO-56 eq. 62/66', reason='Kc mid/end adjusted with stage-mean u2 and RHmin ∈ [20, min(RHmean, 80)] %; interval over height range',
                   variable='Kc mid adjusted [lo, hi]; Kc end adjusted [lo, hi]', unit='dimensionless',
                   value=[[round(float(x), 3) for x in mid_b], [round(float(end_b[0][0]), 3), round(float(end_b[1][1]), 3)]]))
    ev.append(dict(source='FAO-56 single Kc', reason='sum of daily Kc × ET0 over the crop period', variable='ETc [lo, hi]', unit='mm',
                   period=period, value=[round(etc[0], 2), round(etc[1], 2)]))
    ev.append(dict(source='NASA POWER', file=meta['file'], sha256=meta['sha256'], variable='PRECTOTCORR', unit='mm', period=period,
                   value=round(rain, 2), reason='total rainfall during crop period; effective share unknown'))
    return dict(status='computed', etc_mm=[round(etc[0], 2), round(etc[1], 2)], rainfall_mm=round(rain, 2),
                total_days=row['total'], evidence=ev, needs=[])


def irrigation_bounds(req, efficiency=None, initial_soil_water=None):
    """Seasonal irrigation interval from ETc bounds; each bound only exists when its inputs are declared.

    lower (net, mm): ETc_low − all rainfall − initial plant-available soil water (≥ 0). Valid only with a
    declared initial soil water (including any capillary contribution); otherwise unknown.
    upper (gross, mm): ETc_high / efficiency (rainfall and soil water taken as zero). Needs declared efficiency.
    Leaching requirement is not included; saline water would raise the upper bound.
    """
    lo = None if initial_soil_water is None else max(0.0, req['etc_mm'][0] - req['rainfall_mm'] - initial_soil_water)
    hi = None if not efficiency else req['etc_mm'][1] / efficiency
    return lo, hi
