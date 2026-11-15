import json
import pandas as pd
import pytest
from src.pipeline import ROOT,Pipeline,validate_ecocrop,read_power_csv,digest

def test_ecocrop_invalid_and_original_preserved():
    raw=pd.DataFrame({'scientificname':['test'],'tmin':[12],'topmn':[160],'topmx':[28],'tmax':[38]})
    out,q=validate_ecocrop(raw)
    pd.testing.assert_frame_equal(out[raw.columns],raw)
    assert pd.isna(out.topmn_usable.iloc[0]);assert not out.topmn_valid.iloc[0]
    assert out.topmx_usable.iloc[0]==28

def test_ecocrop_order_nulls_ph():
    df=pd.DataFrame({'tmin':[12,None],'topmn':[30,None],'topmx':[20,None],'tmax':[38,None],'phmin':[0,None],'phopmn':[6,None],'phopmx':[7,None],'phmax':[15,None]})
    out,q=validate_ecocrop(df)
    assert out.topmn_usable.isna().all();assert out.topmx_usable.isna().all();assert out.phmax_usable.isna().all()
    assert not out.environment_has_invalid.iloc[1]

def power_fixture(tmp_path,rows):
    text='-BEGIN HEADER-\nDates (month/day/year): 01/01/2024 through 12/31/2024 in LST\nLocation: latitude 0 longitude 0\n'
    for v,u in [('T2M','C'),('T2M_MAX','C'),('T2M_MIN','C'),('PRECTOTCORR','mm/day'),('RH2M','%'),('ALLSKY_SFC_SW_DWN','MJ/m^2/day'),('WS2M','m/s')]:text+=f'{v} description ({u})\n'
    text+='-END HEADER-\nYEAR,DOY,T2M,T2M_MAX,T2M_MIN,PRECTOTCORR,RH2M,ALLSKY_SFC_SW_DWN,WS2M\n'+rows
    p=tmp_path/'test.csv';p.write_text(text);return p

def test_power_leap_fill_units(tmp_path):
    p=power_fixture(tmp_path,'2024,60,-999,20,10,0,50,10,2\n2024,366,15,20,10,0,50,10,2\n')
    df,q=read_power_csv(p);assert str(df.fecha.iloc[0].date())=='2024-02-29';assert pd.isna(df.T2M.iloc[0]);assert q['time_standard']=='LST';assert q['units']['ALLSKY_SFC_SW_DWN']=='MJ/m^2/day'
    p=power_fixture(tmp_path,'2024,367,15,20,10,0,50,10,2\n')
    with pytest.raises(ValueError,match='DOY'):read_power_csv(p)

def test_real_environment_and_cache():
    r=Pipeline()
    jobs=[('ecocrop',ROOT/'data/raw/ecocrop/ecocrop.parquet'),('power',ROOT/'data/raw/power/POWER_Point_Daily_20210101_20251231_036d59N_0119d52W_LST.csv')]
    if not all(p.exists() for _,p in jobs):pytest.skip('Local user inputs absent')
    for s,p in jobs:
        sha=digest(p);out=r.local_environment(s,p);mtime=out.stat().st_mtime_ns
        r.local_environment(s,p);assert out.stat().st_mtime_ns==mtime;assert digest(p)==sha
        df=pd.read_parquet(out);assert len(df)==(2568 if s=='ecocrop' else 1826)
        if s=='ecocrop':pd.testing.assert_frame_equal(df[pd.read_parquet(p).columns],pd.read_parquet(p))
        else:assert out.name=='power_california_2021_2025.parquet';assert df.fecha.nunique()==1826

def test_independent_killing_temperatures_not_ordered():
    df=pd.DataFrame({'ktmp':[-1],'ktmpr':[-5],'latmn':[20],'latopmn':[10],'latopmx':[30],'latmx':[40]})
    out,q=validate_ecocrop(df)
    assert not out.environment_has_invalid.any()
