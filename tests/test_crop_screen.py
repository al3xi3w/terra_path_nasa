import pandas as pd
import pytest
from src.crop_screen import monthly_climate,evaluate_crop,rotation_context

def test_real_months_and_units():
 d=monthly_climate()
 assert len(d)==57 and d.month.nunique()==57
 assert d.power_calendar_complete.all()
 assert d.iloc[0].gpm_duration_hours==744
 p=pd.read_parquet('data/processed/power_california_2021_2025.parquet')
 assert d.iloc[0].power_precipitation_mm==pytest.approx(p[p.fecha.dt.strftime('%Y-%m').eq('2021-01')].PRECTOTCORR.sum())
 assert d.latitude.eq(36.59).all()

def test_partial_year_no_annual_rainfall_inference():
 d=pd.read_parquet('data/processed/california_monthly_climate.parquet')
 r=evaluate_crop(d,'Zea mays',start='2025-01',end='2025-09')
 assert r['status']=='insufficiently_documented' and not r['factors']

def test_unknown_crop_and_no_rotation():
 d=pd.read_parquet('data/processed/california_monthly_climate.parquet')
 assert evaluate_crop(d,'invented species')['status']=='insufficiently_documented'
 r=rotation_context(None,['Zea mays'],36.59,-119.52,'2021-01','2024-12')
 assert r['recommendation'] is None

def test_reference_boundaries_and_missing(monkeypatch):
 from src.store import DataStore
 row={'ecoportcode':1}
 for prefix,values in [('t',[10,20,30,40]),('r',[100,200,300,400])]:
  names=['tmin','topmn','topmx','tmax'] if prefix=='t' else ['rmin','ropmn','ropmx','rmax']
  for n,v in zip(names,values):row[n+'_usable']=v;row[n+'_valid']=True
 monkeypatch.setattr(DataStore,'crop_reference',lambda *a,**k:pd.DataFrame([row]))
 d=pd.DataFrame({'month':pd.period_range('2021-01','2021-12',freq='M').astype(str),'power_calendar_complete':True,'expected_days':30,'power_precipitation_mm':20.,'power_temperature_mean_c':20.})
 assert evaluate_crop(d,'test')['status']=='favorable'
 d['power_precipitation_mm']=1
 assert evaluate_crop(d,'test')['status']=='unfavorable'
 d['power_precipitation_mm']=float('nan');d['power_temperature_mean_c']=float('nan')
 assert evaluate_crop(d,'test')['status']=='insufficiently_documented'
