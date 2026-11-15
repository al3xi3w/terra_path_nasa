import json
from pathlib import Path
import h5py
import numpy as np
import pandas as pd
import pytest
from src.audit import clean_sentinel, clean_nass, month_coverage, extract_gpm, write_table
from src.pipeline import ROOT, digest
from src.store import DataStore


def test_sentinel_flags_without_repair(tmp_path):
    original=pd.read_csv(ROOT/'data/raw/ndvi_s2_mensual_todos.csv').iloc[:2].copy()
    original.loc[0,'ndvi_min']=0.8;original.loc[0,'ndvi_max']=0.2
    original.loc[1,'month']='2026-11-01'
    path=tmp_path/'s.csv';original.to_csv(path,index=False);before=digest(path)
    result,q=clean_sentinel(path)
    assert result.loc[0,'ndvi_inconsistent_summary']
    assert not result.loc[0,'ndvi_usable']
    assert result.loc[0,'ndvi_min']==0.8
    assert result.loc[1,'incomplete_or_future_month']
    assert digest(path)==before


def test_sentinel_duplicates_and_missing(tmp_path):
    d=pd.read_csv(ROOT/'data/raw/ndvi_s2_mensual_todos.csv').iloc[:1]
    d=pd.concat([d,d],ignore_index=True);d.loc[0,'ndvi_mean']=np.nan
    p=tmp_path/'s.csv';d.to_csv(p,index=False)
    result,_=clean_sentinel(p)
    assert result.duplicate_key.all()
    assert not result.ndvi_usable.any()
    assert pd.isna(result.loc[0,'ndvi_mean'])


def test_nass_suppression_units_and_fips(tmp_path):
    d=pd.read_csv(ROOT/'data/raw/USDA_NASS_CALIFORNIA.csv',dtype=str).iloc[:3].copy()
    d['Value']=['(D)','1,234.5','0'];p=tmp_path/'n.csv';d.to_csv(p,index=False)
    result,q=clean_nass(p)
    assert result.county_fips.eq('06019').all()
    assert pd.isna(result.loc[0,'value_numeric'])
    assert result.loc[0,'value_status']=='(D)'
    assert result.loc[1,'value_numeric']==1234.5
    assert result.loc[2,'value_numeric']==0
    assert result.unit.eq('BU / ACRE').all()
    assert not result.loc[0,'usable']


def test_nass_duplicate_variants(tmp_path):
    d=pd.read_csv(ROOT/'data/raw/USDA_NASS_CALIFORNIA.csv',dtype=str).iloc[:1]
    d=pd.concat([d,d],ignore_index=True);p=tmp_path/'n.csv';d.to_csv(p,index=False)
    result,_=clean_nass(p)
    assert result.duplicate_key.all() and not result.usable.any()


def test_month_coverage_counts_unique_not_files():
    c=month_coverage([dict(month='2021-01',status='validated')]*2+[
        dict(month='2021-02',status='quarantined')],end='2021-03')
    assert c['unique_months']==1
    assert c['duplicate_months']=={'2021-01':2}
    assert c['missing_months']==['2021-02','2021-03']


def test_gpm_extract_dimensions_fill_and_qa(tmp_path):
    p=tmp_path/'g.h5'
    with h5py.File(p,'w') as f:
        g=f.create_group('Grid');g['lat']=[-0.05,0.05];g['lon']=[-0.05,0.05]
        from src.audit import GPM_VARIABLES
        for name in GPM_VARIABLES:
            d=g.create_dataset(name,data=np.array([[[2.,3.],[4.,-9999.]]]))
            d.attrs['_FillValue']=-9999.
    r=dict(status='validated',path=str(p),sha256=digest(p),start='2021-01-01',end_exclusive='2021-02-01',duration_hours=744)
    points=[dict(location_id='x',latitude=-.04,longitude=.04)]
    row=extract_gpm(p,points,r)[0]
    assert row['precipitation']==4 and row['cell_lon_index']==1 and row['cell_lat_index']==0
    points[0]['latitude']=.04
    assert np.isnan(extract_gpm(p,points,r)[0]['precipitation'])
    points[0]['latitude']=100
    with pytest.raises(ValueError):extract_gpm(p,points,r)


def test_store_overlap_and_no_extrapolation(tmp_path):
    write_table(pd.DataFrame([dict(location_id='p',latitude=1.,longitude=2.)]),tmp_path/'data/integrated/locations.parquet',{})
    write_table(pd.DataFrame([dict(location_id='p',period_start='2021-01-01',period_end_exclusive='2022-01-01',source='nass',crop_id='nass:WHEAT')]),tmp_path/'data/integrated/observations.parquet',{})
    s=DataStore(tmp_path)
    assert len(s.observations(start='2021-06-01',end='2021-07-01',crop_id='nass:WHEAT'))==1
    assert s.observations(start='2022-01-01').empty
    assert s.at_point(1.001,2.).empty
    assert len(s.at_point(1.,2.))==1
    with pytest.raises(ValueError):s.observations(start='2022',end='2021')


def test_real_audit_integrity_and_coverage():
    p=ROOT/'data/metadata/audit/summary.json'
    if not p.exists():pytest.skip('Run offline audit first')
    summary=json.loads(p.read_text())
    assert summary['raw_unchanged']
    assert summary['gpm']['validated_files']==57
    assert summary['gpm']['unique_months']==57
    assert summary['gpm']['missing_months']==['2025-10','2025-11','2025-12']
    report=json.loads((p.parent/'gpm_monthly.json').read_text())
    for r in report['files']:
        assert not r['errors']
        assert r['variables']['precipitation']['cells']==6480000
        assert digest(ROOT/r['path'])==r['sha256']
    assert summary['sentinel']['rows']==426 and summary['nass']['rows']==392


def test_empty_originals_excluded_from_observations():
    p=ROOT/'data/metadata/audit/existing_sources.json'
    if not p.exists():pytest.skip('Run offline audit first')
    entries=json.loads(p.read_text())
    for source in ['smap','modis','gpm']:
        assert any(r['source']==source and r['status']=='empty_original' for r in entries)
    obs=DataStore().observations()
    assert not obs.source.isin(['smap','modis','gpm','gaez']).any()


@pytest.mark.parametrize('problem',['units','time','coordinate','negative','product'])
def test_gpm_rejects_readable_but_invalid_file(tmp_path,problem):
    import shutil
    from src.audit import audit_gpm
    source=next((ROOT/'data/raw/gpm_monthly').glob('*.HDF5'),None)
    if source is None:pytest.skip('Monthly original unavailable')
    p=tmp_path/'monthly.h5';shutil.copyfile(source,p)
    with h5py.File(p,'r+') as f:
        if problem=='units':f['Grid/precipitation'].attrs['units']='mm/day'
        elif problem=='time':f['Grid/time_bnds'][0,1]-=86400
        elif problem=='coordinate':f['Grid/lat'][5]=f['Grid/lat'][4]
        elif problem=='negative':f['Grid/precipitation'][0,1000,1000]=-2
        else:f.attrs['FileHeader']=f.attrs['FileHeader'].replace(b'TimeInterval=MONTH',b'TimeInterval=DAY')
    result=audit_gpm(p)
    assert result['status']=='quarantined' and result['errors']


def test_real_crop_query_and_point_access():
    if not (ROOT/'data/integrated/catalog.parquet').exists():pytest.skip('Run audit first')
    store=DataStore()
    rows=store.crop_reference('fao56','Broccoli')
    assert len(rows)==1 and pd.isna(rows.iloc[0].kc_initial)
    assert rows.attrs['fieldshift_lineage']
    assert not store.crop_reference('calendar','0056',area='PE').empty
    assert store.crop_reference('calendar','0056',area='US').empty
    rows=store.gpm_at_point(-5.24,-79.45,'2021-01-01','2021-02-01')
    assert len(rows)==1 and rows.iloc[0].duration_hours==744
    assert store.observations(source='usda_nass',start='2022-01-01').empty


def test_calendar_impossible_dates_preserved():
    from src.audit import calendar_flags
    df=pd.DataFrame({'session_early_sowing_month':['4','2',None],
                     'session_early_sowing_day':['31','29',None]},dtype='string')
    checked=calendar_flags(df)
    assert checked.seasonal_date_invalid.tolist()==[True,False,False]
    assert checked.loc[0,'session_early_sowing_day']=='31'
    assert pd.isna(checked.loc[2,'session_early_sowing_day'])


def test_readiness_exclusions_and_nass_temporal_only():
    issues=json.loads((ROOT/'data/metadata/audit/readiness_issues.json').read_text())
    assert len(issues['calendars'])==109
    assert all(r['usable'] is False for r in issues['calendars'])
    n=pd.read_parquet(ROOT/'data/processed/usda_nass.parquet')
    assert n.year.eq(2021).sum()==1
    obs=DataStore().observations()
    assert not obs.source.isin(['smap','modis','gpm','gaez']).any()
    s=pd.read_parquet(ROOT/'data/processed/sentinel2_monthly.parquet')
    assert not s.ndvi_usable.any()
