"""Monthly climate profile for any coordinate, from the local NASA POWER daily series.

Works anywhere POWER has been downloaded for the exact point: no spatial extrapolation and no
nearest-point substitution. A calendar month enters an aggregate only when every one of its days
is present and the variable is not missing, so a short month never looks like a dry month.

POWER's meteorology starts in 1981 but its solar radiation starts in 1984, so ET0 is reported with
its own year count: frost and rainfall statistics may rest on more years than ET0 does.
"""
import json
from pathlib import Path
import pandas as pd
from .pipeline import ROOT, digest, read_power_csv
from .water_requirement import et0_penman_monteith

PILOTS_CONFIG = 'config/pilots.json'
VARIABLES = ['T2M', 'T2M_MAX', 'T2M_MIN', 'PRECTOTCORR', 'RH2M', 'WS2M', 'ALLSKY_SFC_SW_DWN']


def pilots(root=ROOT):
    return json.loads((Path(root) / PILOTS_CONFIG).read_text())['pilots']


def power_file(latitude, longitude, root=ROOT):
    """The widest-covering POWER export for these exact coordinates; None when there is none.

    Several files can share a point (a 1981 and a 1984 download). Picking the widest period
    deterministically avoids silently profiling fewer years than are on disk.
    """
    best = None
    for path in sorted((Path(root) / 'data/raw/power').glob('*.csv')):
        frame, quality = read_power_csv(path)
        if quality['coordinates']['latitude'] != latitude or quality['coordinates']['longitude'] != longitude:continue
        span = (pd.Timestamp(quality['period'][1]) - pd.Timestamp(quality['period'][0])).days
        if best is None or span > best[0]:best = (span, path, frame, quality)
    if best is None:return None
    _, path, frame, quality = best
    meta = dict(file=str(path.relative_to(Path(root))), sha256=digest(path), latitude=latitude, longitude=longitude,
                period=quality['period'], rows=quality['rows'], missing_days=quality['missing_days'],
                time_standard=quality['time_standard'], units=quality['units'],
                missing_percent={k: round(v, 3) for k, v in quality['missing_percent'].items() if v},
                support='POWER point export; meteorology ~0.5x0.625 degrees, solar ~1 degree, not a station')
    import re
    elevation = re.search(r'elevation from MERRA-2:.*?=\s*([-\d.]+)\s*meters', quality['header_original'])
    meta['elevation_m'] = float(elevation[1]) if elevation else None
    return frame, meta


def daily_series(latitude, longitude, root=ROOT):
    """Daily frame with an et0_mm column, null on any day lacking a Penman-Monteith input."""
    found = power_file(latitude, longitude, root)
    if found is None:return None, None
    frame, meta = found
    frame = frame.sort_values('fecha').reset_index(drop=True)
    complete = frame[VARIABLES].notna().all(axis=1)
    frame['et0_mm'] = None
    if meta['elevation_m'] is not None and complete.any():
        frame.loc[complete, 'et0_mm'] = et0_penman_monteith(frame[complete], latitude, meta['elevation_m']).values
    frame['et0_mm'] = pd.to_numeric(frame['et0_mm'], errors='coerce')
    return frame, meta


def _complete_months(frame, column):
    """(year, month) groups where every calendar day is present and the column has no gap."""
    d = frame[['fecha', column]].copy()
    d['year'] = d.fecha.dt.year;d['month'] = d.fecha.dt.month
    grouped = d.groupby(['year', 'month'])
    size = grouped.fecha.size();present = grouped[column].count()
    expected = pd.Series({k: pd.Period(f'{k[0]}-{k[1]:02d}').days_in_month for k in size.index})
    return size.eq(expected) & present.eq(expected)


def monthly_profile(latitude, longitude, root=ROOT, start=None, end=None, frost_threshold=0.0):
    """Climatology by calendar month, plus frost and rainfall variability. One row per month."""
    frame, meta = daily_series(latitude, longitude, root)
    if frame is None:return None, dict(reason='no POWER series at these exact coordinates')
    if start:frame = frame[frame.fecha >= pd.Timestamp(start)]
    if end:frame = frame[frame.fecha <= pd.Timestamp(end)]
    if frame.empty:return None, dict(reason='no days inside the requested period', **meta)
    frame = frame.assign(year=frame.fecha.dt.year, month=frame.fecha.dt.month)
    rows = []
    for variable, label in [('PRECTOTCORR', 'rain'), ('et0_mm', 'et0'), ('T2M_MIN', 'temperature')]:
        usable = _complete_months(frame, variable)
        rows.append((label, usable[usable].index))
    usable = dict(rows)
    out = []
    for month in range(1, 13):
        record = dict(month=month)
        keys = {k for k in usable['temperature'] if k[1] == month}
        days = frame[frame.month.eq(month) & frame.set_index(['year', 'month']).index.isin(keys)]
        record['years_temperature'] = len(keys)
        if len(keys):
            record.update(t_min_mean_c=round(float(days.T2M_MIN.mean()), 2), t_max_mean_c=round(float(days.T2M_MAX.mean()), 2),
                          t_mean_c=round(float(days.T2M.mean()), 2), t_min_absolute_c=round(float(days.T2M_MIN.min()), 2))
            frost = days.assign(cold=days.T2M_MIN < frost_threshold).groupby('year').cold.sum()
            record.update(frost_threshold_c=frost_threshold, frost_days_mean=round(float(frost.mean()), 2),
                          frost_days_max=int(frost.max()), frost_year_probability=round(float((frost > 0).mean()), 3))
        rain_keys = {k for k in usable['rain'] if k[1] == month}
        totals = frame[frame.set_index(['year', 'month']).index.isin(rain_keys)].groupby('year').PRECTOTCORR.sum()
        record['years_rain'] = len(totals)
        if len(totals):
            record.update(rain_mean_mm=round(float(totals.mean()), 2), rain_p10_mm=round(float(totals.quantile(0.1)), 2),
                          rain_p90_mm=round(float(totals.quantile(0.9)), 2),
                          rain_cv=round(float(totals.std() / totals.mean()), 3) if totals.mean() else None)
        et0_keys = {k for k in usable['et0'] if k[1] == month}
        et0 = frame[frame.set_index(['year', 'month']).index.isin(et0_keys)].groupby('year').et0_mm.sum()
        record['years_et0'] = len(et0)
        if len(et0):record['et0_mean_mm'] = round(float(et0.mean()), 2)
        out.append(record)
    profile = pd.DataFrame(out)
    meta['frost_threshold_c'] = frost_threshold
    meta['completeness_rule'] = 'a calendar month counts only when every day is present and the variable has no gap'
    meta['et0_note'] = 'ET0 needs solar radiation, which POWER serves from 1984; years_et0 can be lower than years_rain'
    return profile, meta


def annual_series(latitude, longitude, root=ROOT, frost_threshold=0.0):
    """One row per calendar year: rain, ET0 and frost days, with the completeness counts."""
    frame, meta = daily_series(latitude, longitude, root)
    if frame is None:return None, dict(reason='no POWER series at these exact coordinates')
    frame = frame.assign(year=frame.fecha.dt.year)
    rows = []
    for year, days in frame.groupby('year'):
        expected = 366 if pd.Period(f'{year}').is_leap_year else 365
        complete = len(days) == expected
        rows.append(dict(year=int(year), days=len(days), complete_year=complete,
                         rain_mm=round(float(days.PRECTOTCORR.sum()), 2) if complete and days.PRECTOTCORR.notna().all() else None,
                         et0_mm=round(float(days.et0_mm.sum()), 2) if complete and days.et0_mm.notna().all() else None,
                         frost_days=int((days.T2M_MIN < frost_threshold).sum()) if complete and days.T2M_MIN.notna().all() else None,
                         t_min_absolute_c=round(float(days.T2M_MIN.min()), 2) if days.T2M_MIN.notna().any() else None))
    return pd.DataFrame(rows), meta


def frost_risk_by_crop(profile, library, months=None):
    """Mean frost days per crop using its own killing temperature; unknown when EcoCrop has none.

    The profile is built with one threshold, so this recomputes nothing: it reports which crops
    can be evaluated at all. A null killing temperature never becomes zero.
    """
    result = {}
    for row in library.itertuples():
        value = getattr(row, 'killing_temperature_c', None)
        result[row.crop_key] = dict(killing_temperature_c=None if pd.isna(value) else float(value),
                                    evaluable=bool(pd.notna(value)),
                                    reason=None if pd.notna(value) else 'EcoCrop has no valid killing temperature for this species')
    return result
