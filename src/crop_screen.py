"""Offline climate screening, not yield prediction or rotation recommendation."""
import json
from pathlib import Path
import pandas as pd
from .pipeline import ROOT,digest
from .audit import write_table
from .store import DataStore

LAT,LON=36.59,-119.52


def monthly_climate(root=ROOT):
    root=Path(root)
    p=root/'data/processed/power_california_2021_2025.parquet'
    power=pd.read_parquet(p)
    if not (power.latitude.eq(LAT)&power.longitude.eq(LON)&power.time_standard.eq('LST')).all():
        raise ValueError('Unexpected POWER location/time standard')
    if power.fecha.duplicated().any():raise ValueError('Duplicate POWER days')
    # Verify the local lineage before using the processed point series.
    manifests=list((root/'data/metadata').glob('power-local-*.json'))
    meta=next(json.loads(m.read_text()) for m in manifests if json.loads(m.read_text()).get('processed')==str(p.relative_to(root)))
    if digest(p)!=meta['output_sha256'] or digest(root/meta['path'])!=meta['input_sha256']:raise ValueError('POWER lineage changed')
    expected={'T2M':'C','PRECTOTCORR':'mm/day','ALLSKY_SFC_SW_DWN':'MJ/m^2/day'}
    if any(meta['source']['units'].get(k)!=v for k,v in expected.items()):raise ValueError('Unexpected POWER units')
    g=DataStore(root).gpm_at_point(LAT,LON,'2021-01-01','2025-10-01')
    g['month']=pd.to_datetime(g.period_start,utc=True).dt.strftime('%Y-%m')
    if g.month.duplicated().any():raise ValueError('Duplicate GPM month')
    rows=[]
    for month,d in power.groupby(power.fecha.dt.strftime('%Y-%m')):
        match=g[g.month.eq(month)]
        if match.empty:continue
        r=match.iloc[0];days=pd.Period(month).days_in_month
        full=len(d)==days and d.fecha.dt.day.nunique()==days
        row=dict(month=month,latitude=LAT,longitude=LON,power_days=len(d),expected_days=days,
                 power_calendar_complete=full,power_time_standard='LST',gpm_time_standard='UTC',
                 gpm_cell_latitude=r.cell_latitude,gpm_cell_longitude=r.cell_longitude,
                 gpm_precipitation_rate_mm_hr=r.precipitation,gpm_duration_hours=r.duration_hours,
                 gpm_quality_index=r.precipitationQualityIndex,gpm_random_error_mm_hr=r.randomError,
                 power_source_sha256=meta['input_sha256'],gpm_source_sha256=r.source_sha256)
        for col,label,method in [('T2M','temperature_mean_c','mean'),('T2M_MIN','temperature_min_c','min'),
            ('T2M_MAX','temperature_max_c','max'),('PRECTOTCORR','precipitation_mm','sum'),
            ('RH2M','humidity_mean_percent','mean'),('WS2M','wind_mean_m_s','mean'),
            ('ALLSKY_SFC_SW_DWN','solar_total_mj_m2','sum')]:
            valid=full and d[col].notna().all()
            row['power_'+label]=float(getattr(d[col],method)()) if valid else None
        rows.append(row)
    result=pd.DataFrame(rows)
    write_table(result,root/'data/processed/california_monthly_climate.parquet',{
        'units':'column suffixes','POWER':'modelled point export; meteorology ~0.5x0.625 degrees, solar ~1 degree',
        'GPM':'monthly mean rate in 0.1 degree cell; QA retained, no threshold assumed',
        'time':'LST and UTC calendar months paired approximately; no exact instant alignment',
        'aggregation':'POWER daily means averaged; daily precipitation and radiation summed only if complete; temperature extrema retained; GPM rate not accumulated'})
    return result


def evaluate_crop(climate, crop, root=ROOT, start='2021-01', end='2024-12'):
    """Calendar-year climate screen. Annual rainfall bounds are never compared to monthly sums."""
    if start>end:raise ValueError('Invalid horizon')
    ref=DataStore(root).crop_reference('ecocrop',crop)
    base=dict(crop=crop,status='insufficiently_documented',factors=[],advantages=[],risks=[],
        missing=['crop season and phenology','soil, nutrients and irrigation availability','validated local suitability labels'],
        assumptions={'scope':'annual calendar-year climate screening, not growing-season suitability','temperature_rule':'compare annual mean to EcoCrop temperature bounds; configurable design assumption, not validated biological response'},
        gaez='FAO AgERA5-derived SIX context available via parcel_scenarios; not added to this annual climate score',rotation_recommendation=None)
    if len(ref)!=1:
        base['missing'].append('Unique exact scientific name in EcoCrop');return base
    d=climate[climate.month.between(start,end)].copy();d['year']=d.month.str[:4]
    r=ref.iloc[0];statuses=[]
    for year,months in d.groupby('year'):
        if len(months)!=12 or not months.power_calendar_complete.all():
            base['missing'].append('Complete calendar year '+year);continue
        for variable,cols,value in [
            ('annual_precipitation_mm',['rmin','ropmn','ropmx','rmax'],months.power_precipitation_mm.sum(min_count=12)),
            ('annual_mean_temperature_c',['tmin','topmn','topmx','tmax'],(months.power_temperature_mean_c*months.expected_days).sum(min_count=12)/months.expected_days.sum())]:
            bounds=[r.get(c+'_usable') for c in cols]
            if pd.isna(value) or any(pd.isna(v) or not bool(r.get(c+'_valid',False)) for c,v in zip(cols,bounds)):
                base['missing'].append(year+': valid '+variable+' and all four EcoCrop bounds');continue
            lo,optlo,opthi,hi=map(float,bounds)
            if not lo<=optlo<=opthi<=hi:raise ValueError('Unordered usable bounds')
            status='unfavorable' if value<lo or value>hi else ('favorable' if optlo<=value<=opthi else 'marginal')
            statuses.append(status)
            factor=dict(year=year,variable=variable,value=float(value),bounds=[lo,optlo,opthi,hi],status=status,source='POWER + EcoCrop *_usable',ecocrop_code=str(r.ecoportcode))
            base['factors'].append(factor)
            (base['advantages'] if status=='favorable' else base['risks']).append(f'{year} {variable}: {status}')
    # Favorable only means the evaluated climate rules, never full agronomic suitability.
    base['status']='unfavorable' if 'unfavorable' in statuses else ('favorable' if statuses and all(s=='favorable' for s in statuses) and len(statuses)==2*d.year.nunique() else 'insufficiently_documented')
    if 'marginal' in statuses:base['missing'].append('Local calibration for values outside optimal but inside absolute bounds')
    return base


def rotation_context(current_crop,candidates,latitude,longitude,start,end):
    if not (-90<=latitude<=90 and -180<=longitude<=180) or start>end:raise ValueError('Invalid location/horizon')
    return dict(current_crop=current_crop,candidates=list(candidates),latitude=latitude,longitude=longitude,
        start=start,end=end,recommendation=None,status='insufficiently_documented',
        available_constraints=['valid EcoCrop ranges for exact identified crops','climate coverage and quality flags'],
        required=['verified crop families and transition rules','local calendar and season lengths','soil and nutrient state','previous crop history' if not current_crop else 'validated effects of supplied previous crop','water supply','costs and objectives'])
