"""Offline regression against user-provided real granules; skip when not present."""
import json
import numpy as np
import pytest
from src.pipeline import ROOT,Pipeline,digest,decode_array

@pytest.mark.parametrize('source',['smap','gpm','srtm','modis'])
def test_real_native(source):
    import h5py
    manifests=list((ROOT/'data/metadata').glob(source+'-native-*.json'))
    if not manifests: pytest.skip('User granule/output not present')
    meta=json.loads(manifests[0].read_text());raw=ROOT/meta['path'];out=ROOT/meta['processed']
    if not raw.exists() or raw.stat().st_size==0:
        pytest.skip('Local original missing/empty; integrity failure is reported by offline audit, derivative cannot be verified')
    assert digest(raw)==meta['input_sha256']
    stamp=out.stat().st_mtime_ns
    assert Pipeline().native_satellite(source,raw)==out
    assert out.stat().st_mtime_ns==stamp
    with h5py.File(out) as result:
        if source in ['smap','gpm']:
            with h5py.File(raw) as original:
                if source=='gpm':
                    np.testing.assert_allclose(result['precipitation'][0,::50,::50],decode_array(original['Grid/precipitation'][0,::50,::50],dict(original['Grid/precipitation'].attrs)),equal_nan=True)
                    np.testing.assert_allclose(result['duration_seconds'][:],np.diff(original['Grid/time_bnds'][:],axis=1).ravel())
                else:
                    for part,suffix in [('AM',''),('PM','_pm')]:
                        d=original['Soil_Moisture_Retrieval_Data_'+part+'/soil_moisture'+suffix]
                        np.testing.assert_allclose(result[part+'/soil_moisture'][:],decode_array(d[:],dict(d.attrs)),equal_nan=True)
                        q=original['Soil_Moisture_Retrieval_Data_'+part+'/retrieval_qual_flag'+suffix][:]
                        expected=(q!=65534)&((q&3)==0)&np.isfinite(result[part+'/soil_moisture'][:])
                        np.testing.assert_array_equal(result[part+'/recommended_quality'][:],expected)
        elif source=='modis':
            from pyhdf.SD import SD
            f=SD(str(raw))
            try:
                for name in ['NDVI','EVI']:
                    d=f.select('250m 16 days '+name);a=d.get()[::100,::100].astype(float);a[(a< -2000)|(a>10000)]=np.nan
                    np.testing.assert_allclose(result[name][::100,::100],a/10000,rtol=1e-6,equal_nan=True)
                assert result['x'].shape==(4800,);assert result['y'][0]>result['y'][-1]
            finally:f.end()
        else:
            import rasterio,zipfile
            with zipfile.ZipFile(raw) as z: member=next(n for n in z.namelist() if n.endswith('.hgt'))
            with rasterio.open(f'/vsizip/{raw}/{member}') as src:
                np.testing.assert_allclose(result['elevation'][::100,::100],src.read(1,masked=True).astype(float).filled(np.nan)[::100,::100],equal_nan=True)
                assert result['elevation'].shape==(src.height,src.width)
    assert digest(raw)==meta['input_sha256']
