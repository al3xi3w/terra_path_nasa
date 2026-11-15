import copy,json
import pytest
from src.parcel_scenarios import validate_input,seasonal_climate,scenarios,gaez_context

@pytest.fixture
def parcel():
 return dict(latitude=36.59,longitude=-119.52,current_crop=None,previous_crops=[],sowing_date='2023-04-01',horizon_end='2023-10-31',irrigation={'available':None},soil={},candidates=[{'crop':'Zea mays','harvest_date':'2023-09-30'}])

@pytest.mark.parametrize('field,value',[('latitude',float('nan')),('longitude',181),('sowing_date','2023-02-30'),('horizon_end','2022-01-01'),('irrigation',{'available':False,'seasonal_mm':100}),('soil',{'ph':15})])
def test_invalid_parcel(parcel,field,value):
 parcel[field]=value
 with pytest.raises(ValueError):validate_input(parcel)

def test_invalid_history_and_duplicate(parcel):
 parcel['previous_crops']=[{'crop':'Zea mays','start':'2023-01-01','end':'2024-01-01'}]
 with pytest.raises(ValueError):validate_input(parcel)
 parcel['previous_crops']=[];parcel['candidates']*=2
 with pytest.raises(ValueError):validate_input(parcel)

def test_season_exact_dates_and_unknown_location():
 import pandas as pd
 p=pd.read_parquet('data/processed/power_california_2021_2025.parquet')
 r=seasonal_climate(36.59,-119.52,'2023-04-01','2023-09-30')
 assert r['complete'] and r['expected_days']==183
 assert r['rainfall_mm']==pytest.approx(p[p.fecha.between('2023-04-01','2023-09-30')].PRECTOTCORR.sum())
 assert seasonal_climate(0,0,'2023-04-01','2023-09-30')['rainfall_mm'] is None
 assert seasonal_climate(36.59,-119.52,'2025-12-01','2026-02-01')['rainfall_mm'] is None

def test_no_unjustified_recommendation(parcel):
 r=scenarios(parcel)
 assert r['rotation_sequence'] is None and r['comparison']['ranking'] is None
 s=r['scenarios'][0]
 assert s['water']['status']=='unknown' and s['calendar']['status']=='unverified_plan'
 assert not s['factors'] # No implicit temperature assumption or invented soil
 assert s['gaez']['climate_lineage']=='AgERA5'
 assert len(s['gaez']['layers'])==2
 assert all(x['units'].startswith('SIX') for x in s['gaez']['layers'])

def test_soil_declaration_and_assumption_separate(parcel):
 parcel['soil']={'ph':6.5};parcel['assumptions']={'screen_season_mean_temperature':True}
 r=scenarios(parcel)['scenarios'][0]
 assert {f['observation_source'] for f in r['factors']}=={'farmer declaration','NASA POWER'}
 assert r['status']=='insufficiently_documented'
