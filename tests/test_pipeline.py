"""Synthetic fixtures only; no geographic network calls."""
import json, shutil
import pytest
from src.pipeline import Pipeline, ROOT, dump, digest
@pytest.fixture
def run(tmp_path):
    shutil.copytree(ROOT/'config',tmp_path/'config'); return Pipeline(tmp_path)
def test_dates(run):
    with pytest.raises(ValueError): run.power(0,0,'2025-01-02','2025-01-01',[])
def test_coordinates(run):
    with pytest.raises(ValueError): run.power(91,0,'2021-01-01','2025-01-01',[])
def test_budget(run):
    with pytest.raises(ValueError): run.fetch('agronomy','x','https://unused.invalid',expected=5000000001)
def test_cache_and_integrity(run):
    p=run.root/'data/raw/agronomy/x.json'; dump(p,[])
    dump(run.root/'data/metadata/agronomy-x.json.json',{'sha256':digest(p)})
    assert run.fetch('agronomy','x.json','https://unused.invalid')==p
    p.write_text('[1]')
    with pytest.raises(ValueError): run.fetch('agronomy','x.json','https://unused.invalid')
def test_processing(run):
    p=run.root/'data/raw/agronomy/test.json'; dump(p,[{'Crop Name':'test','value':None},{'Crop Name':'test','value':None}])
    m=run.root/'data/metadata/test.json'; dump(m,{'path':str(p.relative_to(run.root)),'bytes':p.stat().st_size,'sha256':digest(p),'status':'downloaded'})
    run.process(); j=json.loads(m.read_text()); assert j['quality']['duplicates']==1; assert j['quality']['missing_percent']['value']==100
    assert (run.root/j['processed']).exists(); run.reports(); assert (run.root/'reports/data_inventory.md').exists()

def test_fill_before_scale():
    import numpy as np
    from src.pipeline import decode_array
    a=decode_array([-3000,5000,10000],{'_FillValue':-3000,'scale_factor':0.0001})
    assert np.isnan(a[0]); assert a[1:].tolist()==[0.5,1.0]

def test_srtm_invalid_period(run):
    with pytest.raises(ValueError,match='SRTM coverage'): run.earth('srtm',[-180,-56,180,60],'2021-01-01','2025-12-31',1)

def test_synthetic_imerg(run,tmp_path):
    import h5py,numpy as np,pandas as pd
    p=tmp_path/'synthetic.HDF5'
    with h5py.File(p,'w') as f:
        g=f.create_group('Grid'); d=g.create_dataset('precipitation',data=np.array([[[1,-9999],[3,4]]],dtype=float)); d.attrs['_FillValue']=-9999; d.attrs['units']='mm/hr'
        g['lat']=[0,1];g['lon']=[0,1];g['time']=[0];g['time'].attrs['units']='seconds since 2021-01-01 00:00:00'
    out=run.satellite('gpm',p); df=pd.read_parquet(out)
    assert len(df)==4; assert df.precipitation_rate.isna().sum()==1
    assert run.satellite('gpm',p)==out
    with pytest.raises(ValueError,match='cap'): run.satellite('gpm',p,max_cells=1)

def test_synthetic_smap(run,tmp_path):
    import h5py,numpy as np,pandas as pd
    p=tmp_path/'SMAP_20210101_synthetic.h5'
    with h5py.File(p,'w') as f:
        for part,suffix in [('AM',''),('PM','_pm')]:
            g=f.create_group('Soil_Moisture_Retrieval_Data_'+part)
            for name,data in [('soil_moisture',[[0.2,-9999]]),('latitude',[[0,1]]),('longitude',[[0,1]]),('retrieval_qual_flag',[[0,1]])]:
                d=g.create_dataset(name+suffix,data=data); d.attrs['_FillValue']=-9999
    df=pd.read_parquet(run.satellite('smap',p));assert len(df)==4;assert df.soil_moisture.isna().sum()==2;assert set(df['pass'])=={'AM','PM'}

def test_blank_normalization(run):
    p=run.root/'data/raw/agronomy/blank.json';dump(p,[{'id':'a','optional':' '}])
    m=run.root/'data/metadata/blank.json';dump(m,{'path':str(p.relative_to(run.root)),'status':'downloaded','bytes':p.stat().st_size})
    run.process();assert json.loads(m.read_text())['quality']['missing_percent']['optional']==100

def test_synthetic_elevation(run,tmp_path):
    import rasterio,numpy as np,pandas as pd
    from rasterio.transform import from_origin
    p=tmp_path/'synthetic_elevation.tif'
    with rasterio.open(p,'w',driver='GTiff',width=2,height=1,count=1,dtype='int16',crs='EPSG:4326',transform=from_origin(0,1,1,1),nodata=-32768) as d: d.write(np.array([[10,-32768]],dtype='int16'),1)
    df=pd.read_parquet(run.satellite('srtm',p));assert df.value.isna().sum()==1;assert df.value.iloc[0]==10

def test_earth_search_cache(run,monkeypatch):
    import earthaccess
    calls=[]
    monkeypatch.setattr(earthaccess,'search_data',lambda **kw: calls.append(kw) or [{'synthetic':True}])
    assert run.earth('gpm',[-180,-90,180,90],'2021-01-01','2021-01-02',1)==[{'synthetic':True}]
    run.earth('gpm',[-180,-90,180,90],'2021-01-01','2021-01-02',1)
    assert len(calls)==1

def test_missing_auth(run,monkeypatch):
    import earthaccess
    monkeypatch.delenv('EARTHDATA_USERNAME',raising=False);monkeypatch.delenv('EARTHDATA_PASSWORD',raising=False)
    monkeypatch.setattr(earthaccess,'search_data',lambda **kw: [])
    with pytest.raises(RuntimeError,match='credentials absent'):run.earth('gpm',[-180,-90,180,90],'2021-01-01','2021-01-02',1,True)

def test_calendar_mixed_values(run):
    p=run.root/'data/raw/agronomy/calendar-TEST.json'
    dump(p,[{'id_country':'TEST','sessions':[{'growing_period':{'value':70}},{'growing_period':{'value':'70-85'}}]}])
    m=run.root/'data/metadata/calendar-test.json';dump(m,{'path':str(p.relative_to(run.root)),'status':'downloaded','bytes':p.stat().st_size})
    run.process(); j=json.loads(m.read_text());assert 'processing_error' not in j;assert j['quality']['rows']==2
