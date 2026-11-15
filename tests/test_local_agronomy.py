"""Small synthetic fixtures; curated coefficient assertions refer to local PDF review."""
import json,zipfile,shutil
import pandas as pd
import pytest
from src.pipeline import Pipeline,ROOT,select_crop_yield,digest

def test_crop_yield_excludes_livestock_and_production():
    df=pd.DataFrame({'Element Code':['5412','5510','5413','5417'],'Element':['Yield','Production','Yield','Yield/Carcass Weight'],'Unit':['kg/ha','t','No/An','kg/An']})
    assert len(select_crop_yield(df))==1
    df.loc[0,'Unit']='kg/An'
    with pytest.raises(ValueError,match='unit'):select_crop_yield(df)

def test_zip_pipeline_cache(tmp_path):
    shutil.copytree(ROOT/'config',tmp_path/'config');r=Pipeline(tmp_path)
    folder=tmp_path/'data/raw/faostat';folder.mkdir(parents=True)
    csv='Area Code,Area,Item Code,Item,Element Code,Element,Year,Unit,Value,Flag\n2,Test,1,Test crop,5412,Yield,1961,kg/ha,100,A\n2,Test,1,Test crop,5510,Production,1961,t,200,A\n'
    with zipfile.ZipFile(folder/'crops_livestock_global.zip','w') as z:z.writestr('Test(Normalized).csv',csv)
    r.local_agronomy('faostat');out=tmp_path/'data/processed/faostat_yield_global.parquet';assert len(pd.read_parquet(out))==1
    timestamp=out.stat().st_mtime_ns;r.local_agronomy('faostat');assert out.stat().st_mtime_ns==timestamp
    assert list(folder.iterdir())==[folder/'crops_livestock_global.zip']

def test_reviewed_kc_nulls_and_source_binding():
    j=json.loads((ROOT/'config/fao56_verified.json').read_text());df=pd.DataFrame(j['records'])
    assert df.loc[df.crop_label=='Broccoli','kc_initial'].isna().all()
    assert df.loc[df.crop_label=='Cantaloupe',['kc_initial','kc_mid','kc_end']].iloc[0].tolist()==[0.5,0.85,0.6]
    assert set(df.pdf_page)=={136,137,138}
    p=ROOT/'data/raw/fao56/FAO56.pdf'
    if p.exists(): assert digest(p)==j['pdf_sha256']

def test_changed_pdf_fails_closed(tmp_path):
    shutil.copytree(ROOT/'config',tmp_path/'config');r=Pipeline(tmp_path)
    p=tmp_path/'data/raw/fao56/FAO56.pdf';p.parent.mkdir(parents=True);p.write_bytes(b'Synthetic different PDF')
    with pytest.raises(ValueError,match='PDF changed'):r.local_agronomy('fao56')
