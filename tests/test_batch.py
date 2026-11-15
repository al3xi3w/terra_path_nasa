import json,shutil
import pandas as pd
from src.pipeline import ROOT,Pipeline,digest,dump
from src.batch import power_variables,existing_power,Batch

def test_solar_availability():
    assert power_variables(1981,['T2M','ALLSKY_SFC_SW_DWN'])==['T2M']
    assert len(power_variables(1984,['T2M','ALLSKY_SFC_SW_DWN']))==2

def test_no_mandatory_coordinates(tmp_path):
    shutil.copytree(ROOT/'config',tmp_path/'config');b=Batch(Pipeline(tmp_path));b.power();b.appeears()
    assert all(e['status']=='on_demand_no_coordinates_configured' for e in b.events)

def test_existing_power_requires_full_year_and_standard(tmp_path):
    shutil.copytree(ROOT/'config',tmp_path/'config');p=Pipeline(tmp_path)
    raw=tmp_path/'data/raw/power/year.json';data={d:1 for d in pd.date_range('2024-01-01','2024-12-31').strftime('%Y%m%d')}
    dump(raw,{'properties':{'parameter':{'T2M':data}}})
    m=tmp_path/'data/metadata/power-test.json';dump(m,{'path':str(raw.relative_to(tmp_path)),'sha256':digest(raw),'params':{'latitude':1.,'longitude':2.,'time-standard':'LST'}})
    assert existing_power(p,1.,2.,2024,['T2M'],'LST')
    assert not existing_power(p,1.,2.,2024,['T2M'],'UTC')
    assert not existing_power(p,1.,2.,2023,['T2M'],'LST')

def test_budget_baseline_persisted(tmp_path):
    shutil.copytree(ROOT/'config',tmp_path/'config');b=Batch(Pipeline(tmp_path));baseline=b.baseline
    dump(tmp_path/'data/raw/extra.json',{'synthetic':True})
    assert Batch(Pipeline(tmp_path)).baseline==baseline
