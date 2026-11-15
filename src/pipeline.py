"""Global acquisition; no default geographic query. Raw bytes are immutable."""
import hashlib, json, re, os
from pathlib import Path
from datetime import datetime, timezone
import requests
import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[1]

def digest(p):
    h = hashlib.sha256()
    with open(p, 'rb') as f:
        for b in iter(lambda: f.read(1024*1024), b''): h.update(b)
    return h.hexdigest()

def dump(p, value):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(value, indent=2, default=str))

class Pipeline:
    def __init__(self, root=ROOT):
        self.root=Path(root)
        self.settings=yaml.safe_load((self.root/'config/settings.yaml').read_text())
        self.sources=yaml.safe_load((self.root/'config/sources.yaml').read_text())
        for d in ['raw','processed','metadata','integrated']: (self.root/'data'/d).mkdir(parents=True,exist_ok=True)
    def usage(self):
        return sum(p.stat().st_size for d in ['raw','processed','metadata','integrated'] for p in (self.root/'data'/d).rglob('*') if p.is_file())
    def fetch(self, source, name, url, params=None, expected=None, session=None):
        p=self.root/'data/raw'/source/name
        m=self.root/'data/metadata'/f'{source}-{name}.json'
        if p.exists() and m.exists() and digest(p)==json.loads(m.read_text())['sha256']: return p
        if p.exists(): raise ValueError(f'Existing raw file fails integrity or lacks metadata: {p}')
        p.parent.mkdir(parents=True,exist_ok=True)
        part=p.with_suffix(p.suffix+'.part'); offset=part.stat().st_size if part.exists() else 0
        if expected and expected-offset>self.settings['max_bytes']-self.usage(): raise ValueError('Storage budget exceeded before download')
        headers={'Range':f'bytes={offset}-'} if offset else {}
        with (session or requests).get(url,params=params,headers=headers,stream=True,timeout=(20,120)) as r:
            r.raise_for_status()
            resume=offset and r.status_code==206
            if resume and not r.headers.get('Content-Range','').startswith(f'bytes {offset}-'): raise ValueError('Invalid resume response')
            size=int(r.headers.get('Content-Length',0))
            if size>self.settings['max_bytes']-self.usage(): raise ValueError('Storage budget exceeded')
            with part.open('ab' if resume else 'wb') as f:
                for chunk in r.iter_content(1024*1024):
                    if self.usage()+len(chunk)>self.settings['max_bytes']: raise ValueError('Storage budget exceeded')
                    f.write(chunk)
        if expected and part.stat().st_size!=expected: raise ValueError('Size mismatch')
        part.replace(p)
        dump(m,dict(source=self.sources[source],url=url,params=params,downloaded=datetime.now(timezone.utc).isoformat(),bytes=p.stat().st_size,sha256=digest(p),path=str(p.relative_to(self.root)),status='downloaded',license='Consult official source terms; retain attribution'))
        return p
    def globals(self):
        errors={}
        for name in ['crops','countries']:
            try: self.fetch('agronomy',name+'.json','https://api-cropcalendar.apps.fao.org/api/v1/'+name,{'language':'en'})
            except Exception as e: errors[name]=str(e)
        try:
            listing=self.fetch('gaez','listing.json','https://storage.googleapis.com/storage/v1/b/fao-gismgr-gaez-v5-data/o',{'prefix':self.settings['gaez_prefix'],'maxResults':1000})
            j=json.loads(listing.read_text())
            # Historical global layers only; no arbitrary regional extracts or projections.
            for o in j.get('items',[]):
                if o['name'].endswith(('.tif','.json')) and '.HP' in o['name']:
                    self.fetch('gaez',Path(o['name']).name,o['mediaLink'],expected=int(o['size']))
            if j.get('nextPageToken'): errors['gaez_pagination']='Catalog truncated; narrow configured prefix before adding layers'
        except Exception as e: errors['gaez']=str(e)
        dump(self.root/'data/metadata/errors.json',errors)
    def power(self,lat,lon,start,end,variables):
        if not (-90<=lat<=90 and -180<=lon<=180): raise ValueError('Invalid coordinates')
        if datetime.fromisoformat(start)>datetime.fromisoformat(end): raise ValueError('Invalid dates')
        q=dict(latitude=lat,longitude=lon,start=start.replace('-',''),end=end.replace('-',''),parameters=','.join(variables),community='AG',format='JSON',**{'time-standard':'UTC'})
        key=hashlib.sha256(json.dumps(q,sort_keys=True).encode()).hexdigest()[:20]
        return self.fetch('power',key+'.json','https://power.larc.nasa.gov/api/temporal/daily/point',q)
    def earth(self,source,bbox,start,end,limit,download=False):
        import earthaccess
        w,s,e,n=bbox
        if not (-180<=w<e<=180 and -90<=s<n<=90): raise ValueError('Invalid bbox; split antimeridian queries')
        if datetime.fromisoformat(start)>datetime.fromisoformat(end) or limit<1: raise ValueError('Invalid dates/count')
        if source=='srtm' and (n>60 or s< -56 or start>'2000-02-22' or end<'2000-02-11'):
            raise ValueError('SRTM coverage: 56 S–60 N, February 2000')
        cfg=self.sources[source]
        query_key=hashlib.sha256(json.dumps([source,bbox,start,end,limit]).encode()).hexdigest()[:20]
        cache=self.root/'data/metadata'/f'{source}-search-{query_key}.json'
        if cache.exists() and not download: return json.loads(cache.read_text())
        results=earthaccess.search_data(short_name=cfg['product'],version=cfg['version'],bounding_box=tuple(bbox),temporal=(start,end),count=limit)
        dump(cache,[dict(x) for x in results])
        if download:
            if not all(os.getenv(k) for k in ['EARTHDATA_USERNAME','EARTHDATA_PASSWORD']):
                raise RuntimeError('Earthdata credentials absent; run from your authenticated local terminal')
            if not earthaccess.login(strategy='environment').authenticated:
                raise RuntimeError('Earthdata authentication failed')
            session=earthaccess.get_requests_https_session()
            for x in results:
                for url in x.data_links(): self.fetch(source,url.split('/')[-1].split('?')[0],url,session=session)
        return results
    def process(self):
        jobs=[('ecocrop', self.root/'data/raw/ecocrop/ecocrop.parquet')]
        jobs += [('power',p) for p in (self.root/'data/raw/power').glob('*.csv')]
        for source,path in jobs:
            if not path.exists():continue
            try:self.local_environment(source,path)
            except Exception as error:
                dump(self.root/'data/metadata'/f'{source}-environment-error.json',{'file':path.name,'error':str(error)})
                print(f'{source}: processing failed: {error}')

        for source in ['faostat','fao56']:
            try: self.local_agronomy(source)
            except Exception as error:
                dump(self.root/'data/metadata'/f'{source}-processing-error.json',{'error':str(error)})
                print(f'{source}: processing failed: {error}')
            else:
                error_file=self.root/'data/metadata'/f'{source}-processing-error.json'
                if error_file.exists(): error_file.unlink()

        for source in ['smap','gpm','srtm','modis']:
            for path in (self.root/'data/raw'/source).glob('*'):
                if path.suffix.lower() not in ['.h5','.hdf5','.hdf','.zip','.hgt']: continue
                try: self.native_satellite(source,path)
                except Exception as error:
                    dump(self.root/'data/metadata'/f'{source}-processing-error.json',{'file':path.name,'error':str(error)})
                    print(f'{source}: processing failed: {error}')
                    continue
                error_file=self.root/'data/metadata'/f'{source}-processing-error.json'
                if error_file.exists(): error_file.unlink()

        for m in (self.root/'data/metadata').glob('*.json'):
            meta=json.loads(m.read_text())
            if not isinstance(meta,dict) or 'path' not in meta: continue
            p=self.root/meta['path']
            try:
                if p.suffix=='.tif' or p.suffix.lower()=='.hgt':
                    import rasterio
                    with rasterio.open(p) as ds:
                        count=missing=0; low=high=None
                        for _,window in ds.block_windows(1):
                            a=ds.read(1,window=window,masked=True); count+=a.size; missing+=int(a.mask.sum()) if hasattr(a.mask,'sum') else 0
                            if a.count(): low=min(low if low is not None else float('inf'),float(a.min())); high=max(high if high is not None else -float('inf'),float(a.max()))
                        meta['quality']=dict(dimensions=[ds.count,ds.height,ds.width],crs=str(ds.crs),resolution=ds.res,missing_percent=100*missing/count,min=low,max=high,nodata=ds.nodata,transformations='None: native georeferenced raster retained; no duplicate raster')
                    meta['status']='validated native raster'
                elif p.suffix=='.json' and p.parent.name in ['agronomy','power']:
                    j=json.loads(p.read_text())
                    if p.parent.name=='power':
                        df=pd.DataFrame(j['properties']['parameter']); df.index=pd.to_datetime(df.index,format='%Y%m%d'); df.index.name='date'; df=df.reset_index().replace(j.get('header',{}).get('fill_value',-999),float('nan')); meta['units']=j.get('parameters'); meta['coordinates']=j.get('geometry')
                    else:
                        if isinstance(j,dict):
                            arrays=[v for v in j.values() if isinstance(v,list)]
                            if len(arrays)!=1: raise ValueError('Unrecognized table schema')
                            j=arrays[0]
                        if p.stem.startswith('calendar-'):
                            records=[]
                            for item_index,item in enumerate(j):
                                base={k:v for k,v in item.items() if k!='sessions'}
                                for session_index,session in enumerate(item.get('sessions') or [{}]):
                                    records.append(dict(base,session=session,source_record=item_index,session_index=session_index))
                            df=pd.json_normalize(records)
                        else: df=pd.json_normalize(j)
                    df=df.replace(r'^\s*$',pd.NA,regex=True)
                    df.columns=[re.sub(r'[^a-z0-9]+','_',str(c).lower()).strip('_') for c in df.columns]
                    # Nested source structures retained as JSON, not silently dropped.
                    for c in df:
                        df[c]=df[c].map(lambda v:json.dumps(v,sort_keys=True) if isinstance(v,(dict,list)) else v)
                    if p.stem.startswith('calendar-'):
                        for c in df:
                            if c not in ['source_record','session_index']: df[c]=df[c].astype('string')
                    out=self.root/'data/processed'/f'{p.parent.name}-{p.stem}.parquet'
                    tmp=out.with_suffix('.part'); df.to_parquet(tmp,index=False)
                    if self.usage()>self.settings['max_bytes']: tmp.unlink(); raise ValueError('Processed storage budget exceeded')
                    tmp.replace(out)
                    meta['quality']=dict(identifier_duplicates=int(df['id'].duplicated().sum()) if 'id' in df else None, rows=len(df),missing_percent=(df.isna().mean()*100).to_dict(),duplicates=int(df.duplicated().sum()),types=df.dtypes.astype(str).to_dict(),statistics=df.describe(include='all').astype(str).to_dict() if len(df.columns) else {},transformations='snake_case names; nested JSON serialized; POWER dates and fill values normalized; no imputation/deduplication')
                    meta['processed']=str(out.relative_to(self.root)); meta['status']='downloaded and processed'
                meta.pop('processing_error',None)
                dump(m,meta)
            except Exception as e: meta['processing_error']=str(e); dump(m,meta)
    def reports(self):
        rows=['# Inventario real','', '| Dataset | Estado | Bytes | Ruta | Producto / periodo / unidades |','|---|---|---:|---|---|']; quality=['# Calidad','']
        for m in sorted((self.root/'data/metadata').glob('*.json')):
            j=json.loads(m.read_text())
            if isinstance(j,dict) and 'path' in j:
                rows.append(f"| {m.stem} | {j['status']} | {j['bytes']} | {j['path']} → {j.get('processed','—')} | {j.get('source',{}).get('product','')} / {j.get('source',{}).get('period','ver fuente')} / {j.get('source',{}).get('units','ver campos originales')} |")
                quality.extend([f'## {m.stem}','```json',json.dumps(j.get('quality',j.get('processing_error','Not tabular / metadata only')),indent=2),'```'])
        for m in sorted((self.root/'data/metadata').glob('*processed-*.json')):
            j=json.loads(m.read_text()); rows.append(f"| {m.stem} | processed local granule | — | {j['processed']} |")
        for s in ['power','gpm','smap','modis','srtm']: rows.append(f'| {s} | Configurado bajo demanda'+ ('; requiere Earthdata' if s!='power' else '')+' | 0 | — |')
        verification=self.root/'data/metadata/earth-verification.json'
        if verification.exists(): rows.append('\nCMR: verificación pública realizada; detalles en data/metadata/earth-verification.json; metadatos consultados previamente; los gránulos locales fueron aportados desde la terminal del usuario.')
        failures=self.root/'data/metadata/extension_errors.json'
        if failures.exists(): rows.append('\nErrores de ampliación: '+failures.read_text())
        rows+=['',f'Almacenamiento de datos: {self.usage()} bytes.','', 'Errores: ver data/metadata/errors.json. GAEZ no representa observaciones de parcelas. Las tablas FAO contienen únicamente países publicados.']
        for failure in sorted((self.root/'data/metadata').glob('*-processing-error.json')):
            quality.append('ERROR: '+failure.read_text())
        audit=self.root/'reports/quality_review.md'
        if audit.exists(): quality.append(audit.read_text())
        quality+=['No se integran resoluciones incompatibles. Procesamiento de gránulos locales: ver entradas *-native-* con estadísticas reales. HDF4 se lee con pyhdf. No se han ejecutado consultas regionales.']
        (self.root/'reports').mkdir(exist_ok=True)
        batch_report=self.root/'reports/batch_coverage.md'
        if batch_report.exists(): rows.extend(['', '## Cobertura histórica y fuentes pendientes', batch_report.read_text()])
        (self.root/'reports/data_inventory.md').write_text('\n'.join(rows)); (self.root/'reports/data_quality.md').write_text('\n'.join(quality))

    def extend(self):
        """Compact global selection, verified against GCS objects; all FAO countries."""
        errors={}
        for variable in self.settings['gaez_variables']:
            try:
                prefix=f'DATA/GAEZ-V5/MAPSET/{variable}/GAEZ-V5.{variable}.HP0120'
                listing=self.fetch('gaez',f'catalog-{variable}.json','https://storage.googleapis.com/storage/v1/b/fao-gismgr-gaez-v5-data/o',{'prefix':prefix,'maxResults':1000})
                catalog=json.loads(listing.read_text())
                if catalog.get('nextPageToken'): raise ValueError('Catalog paginated; selection incomplete')
                crops=[{'MZE':'MAIZ','WHE':'WHEA','SOY':'SOYB'}.get(c,c) for c in self.settings['gaez_crops']] if variable.startswith('RES02') else self.settings['gaez_crops']
                selected=[o for o in catalog.get('items',[]) if any('.'+c+'.HRLM.' in o['name'] for c in crops)]
                if not selected: raise ValueError('No matching verified objects')
                for o in selected:
                    p=self.fetch('gaez',Path(o['name']).name,o['mediaLink'],expected=int(o['size']))
                    m=self.root/'data/metadata'/f'gaez-{p.name}.json'
                    meta=json.loads(m.read_text()); meta['source']=dict(self.sources['gaez'],product=variable,units='index 0–10000' if variable=='RES05-SIX' else 'unverified; do not quantitatively integrate',resolution='See raster geotransform',period='2001–2020',management='rainfed, high inputs'); dump(m,meta)
            except Exception as e: errors[variable]=str(e)
        countries=json.loads((self.root/'data/raw/agronomy/countries.json').read_text())
        for country in countries:
            try:
                self.fetch('agronomy',f"calendar-{country['id']}.json",f"https://api-cropcalendar.apps.fao.org/api/v1/countries/{country['id']}/cropCalendar",{'language':'en'})
            except Exception as e: errors['calendar-'+country['id']]=str(e)
        dump(self.root/'data/metadata/extension_errors.json',errors)

    def verify_earth(self):
        """Public global metadata only. Does not authenticate or download granules."""
        results={}
        for source in ['gpm','smap','modis','srtm']:
            cfg=self.sources[source]
            try:
                r=requests.get('https://cmr.earthdata.nasa.gov/search/collections.json',params={'short_name':cfg['product'],'version':cfg['version'],'page_size':10},timeout=60); r.raise_for_status()
                entries=r.json()['feed']['entry']
                if not entries: raise ValueError('Collection not found')
                cid=entries[0]['id']
                r=requests.get('https://cmr.earthdata.nasa.gov/search/granules.umm_json',params={'collection_concept_id':cid,'page_size':1},timeout=60); r.raise_for_status()
                results[source]={'collections':entries,'granule_metadata':r.json(),'download_executed':False}
            except Exception as e: results[source]={'error':str(e)}
        results['credentials_available']=all(os.getenv(k) for k in ['EARTHDATA_USERNAME','EARTHDATA_PASSWORD'])
        dump(self.root/'data/metadata/earth-verification.json',results)

    def satellite(self, source, path, max_cells=2000000):
        """Decode a local native file. Explicit cap prevents accidental global expansion."""
        import numpy as np
        path=Path(path).resolve()
        frames=[]; metadata={'source':self.sources[source],'input_sha256':digest(path),'input':str(path),'validation':'processor; scientific validation against real granule still required'}
        if source in ['gpm','smap']:
            import h5py
            with h5py.File(path,'r') as f:
                if source=='gpm':
                    g=f['Grid']; shape=g['precipitation'].shape
                    if np.prod(shape)>max_cells: raise ValueError('Cell cap exceeded; request a subset before decoding')
                    lon,lat=np.meshgrid(g['lon'][:],g['lat'][:],indexing='ij')
                    if shape[-2:]!=lon.shape: raise ValueError('Unexpected IMERG dimension order')
                    a=decode_array(g['precipitation'][:],dict(g['precipitation'].attrs))
                    if a.shape[0]!=1: raise ValueError('Expected single half-hour IMERG granule')
                    frame=pd.DataFrame({'longitude':lon.ravel(),'latitude':lat.ravel(),'precipitation_rate':a.ravel()})
                    for name in ['precipitationQualityIndex','randomError']:
                        if name in g: frame[name]=decode_array(g[name][:],dict(g[name].attrs)).ravel()
                    metadata['time']=g['time'][:].tolist(); metadata['time_attributes']=dict(g['time'].attrs)
                    metadata['variable_attributes']=dict(g['precipitation'].attrs); metadata['period']='30 minutes; rate retained, no accumulation'; frames=[frame]
                else:
                    for pass_name,suffix in [('AM',''),('PM','_pm')]:
                        g=f['Soil_Moisture_Retrieval_Data_'+pass_name]; d=g['soil_moisture'+suffix]
                        if d.size>max_cells: raise ValueError('Cell cap exceeded')
                        frame=pd.DataFrame({'soil_moisture':decode_array(d[:],dict(d.attrs)).ravel(),'latitude':decode_array(g['latitude'+suffix][:],dict(g['latitude'+suffix].attrs)).ravel(),'longitude':decode_array(g['longitude'+suffix][:],dict(g['longitude'+suffix].attrs)).ravel(),'pass':pass_name})
                        for name in ['retrieval_qual_flag','surface_flag','tb_time_seconds']:
                            if name+suffix in g:
                                frame[name]=decode_array(g[name+suffix][:],dict(g[name+suffix].attrs)).ravel()
                                metadata[pass_name+'_'+name+'_attrs']=dict(g[name+suffix].attrs)
                        metadata[pass_name+'_attrs']=dict(d.attrs); frames.append(frame)
                    metadata['observation_date_from_filename']=re.search(r'\d{8}',path.name).group() if re.search(r'\d{8}',path.name) else None
        elif source in ['modis','srtm']:
            import rasterio
            with rasterio.open(path) as root:
                datasets=root.subdatasets if source=='modis' else [str(path)]
                if source=='modis' and not datasets: raise ValueError('MODIS HDF4 subdatasets unavailable: install GDAL with HDF4 support')
                for uri in datasets:
                    name=uri.split(':')[-1]
                    if source=='modis' and not any(v in name for v in ['NDVI','EVI','VI Quality','pixel reliability','composite day']): continue
                    with rasterio.open(uri) as ds:
                        if ds.width*ds.height>max_cells: raise ValueError('Cell cap exceeded; use subset')
                        a=ds.read(1); attrs={'_FillValue':ds.nodata} if ds.nodata is not None else {}
                        if source=='modis' and ('NDVI' in name or 'EVI' in name): attrs={'_FillValue':-3000,'scale_factor':0.0001}
                        a=decode_array(a,attrs)
                        rr,cc=np.indices(a.shape); x,y=rasterio.transform.xy(ds.transform,rr.ravel(),cc.ravel())
                        frames.append(pd.DataFrame({'row':rr.ravel(),'column':cc.ravel(),'x':x,'y':y,'variable':name,'value':a.ravel()}))
                        metadata[name]={'crs':str(ds.crs),'transform':list(ds.transform),'tags':ds.tags(),'units':'dimensionless' if source=='modis' else 'm'}
                metadata['period']='16-day composite' if source=='modis' else 'February 2000'
        else: raise ValueError('Unsupported source')
        if not frames: raise ValueError('No supported variables found')
        frame=pd.concat(frames,ignore_index=True)
        key=metadata['input_sha256'][:16]; out=self.root/'data/processed'/f'{source}-{key}.parquet'
        if out.exists(): return out
        tmp=out.with_suffix('.part'); frame.to_parquet(tmp,index=False)
        if self.usage()>self.settings['max_bytes']: tmp.unlink(); raise ValueError('Storage budget exceeded')
        tmp.replace(out); metadata.update(rows=len(frame),processed=str(out.relative_to(self.root)),missing_percent=(frame.isna().mean()*100).to_dict(),qa_policy='QA preserved, not silently filtered; no imputation')
        dump(self.root/'data/metadata'/f'{source}-processed-{key}.json',metadata)
        return out


    def native_satellite(self, source, path):
        """Compact scientific grids; never a global pixel table."""
        import numpy as np
        import h5py
        import rasterio
        from datetime import timedelta
        path=Path(path); sha=digest(path)
        out=self.root/'data/processed'/f'{source}-{sha[:16]}-grid.h5'
        manifest=self.root/'data/metadata'/f'{source}-native-{sha[:16]}.json'
        if out.exists() and manifest.exists():
            old=json.loads(manifest.read_text())
            if old.get('processor_version')==1 and old.get('output_sha256')==digest(out): return out
        tmp=out.with_suffix('.part')
        meta=dict(source=self.sources[source],path=str(path.relative_to(self.root)),bytes=path.stat().st_size,input_sha256=sha,processor_version=1,processed=str(out.relative_to(self.root)),status='processed and verified against local real file',quality={})
        def clean(v):
            if isinstance(v,bytes): return v.decode(errors='replace')
            if isinstance(v,np.ndarray): return [clean(x) for x in v.tolist()]
            if isinstance(v,np.generic): return clean(v.item())
            return v
        try:
            with h5py.File(tmp,'w') as dst:
                dst.attrs['source_file']=path.name; dst.attrs['input_sha256']=sha
                def put(name,a,attrs=None):
                    a=np.asarray(a)
                    if a.nbytes+self.usage()>self.settings['max_bytes']: raise ValueError('Storage budget exceeded before writing array')
                    ds=dst.create_dataset(name,data=a,compression='gzip',compression_opts=4,shuffle=True)
                    for k,v in (attrs or {}).items():
                        if k in ['DIMENSION_LIST','REFERENCE_LIST','CLASS','NAME']: continue
                        try: ds.attrs[k]=clean(v)
                        except (TypeError,ValueError): ds.attrs[k]=str(v)
                    if a.dtype.kind in 'fiu':
                        good=np.isfinite(a); vals=a[good]
                        meta['quality'][name]=dict(shape=list(a.shape),missing_percent=float(100*(1-good.mean())),min=float(vals.min()) if vals.size else None,max=float(vals.max()) if vals.size else None,mean=float(vals.mean()) if vals.size else None)
                    return ds
                if source in ['smap','gpm']:
                    with h5py.File(path) as f:
                        if source=='smap':
                            dst.attrs['grid']='EASE-Grid 2.0 36 km; per-cell geographic coordinates retained'
                            dst.attrs['date']=datetime.strptime(re.search(r'_(\d{8})_',path.name)[1],'%Y%m%d').date().isoformat()
                            for part,suffix in [('AM',''),('PM','_pm')]:
                                g=f['Soil_Moisture_Retrieval_Data_'+part]
                                for n in ['soil_moisture','soil_moisture_error','latitude','longitude','tb_time_seconds','retrieval_qual_flag','surface_flag']:
                                    d=g[n+suffix]; attrs=dict(d.attrs); a=decode_array(d[:],attrs)
                                    # Float64 preserves exact time values and all uint16 flags; NaN denotes fill.
                                    attrs.pop('_FillValue',None); attrs['missing_representation']='NaN'
                                    put(part+'/'+n,a,attrs)
                                sm=dst[part+'/soil_moisture'][:]; q=dst[part+'/retrieval_qual_flag'][:]
                                ok=np.isfinite(sm)&np.isfinite(q)&((np.nan_to_num(q,nan=65535).astype('uint16')&3)==0)
                                put(part+'/recommended_quality',ok.astype('uint8'),{'meaning':'finite soil moisture and retrieval flag bits 0 and 1 both zero'})
                                meta['quality'][part+'/soil_moisture']['outside_provider_range']=int(((sm<0.02)|(sm>0.5)).sum())
                        else:
                            g=f['Grid']; dst.attrs['crs']='EPSG:4326';dst.attrs['dimension_order']='time,longitude,latitude'
                            for n in ['precipitation','precipitationQualityIndex','randomError','lat','lon','lat_bnds','lon_bnds','time','time_bnds']:
                                if n not in g: continue
                                d=g[n]; attrs=dict(d.attrs);a=decode_array(d[:],attrs);attrs.pop('_FillValue',None)
                                put(n,a,attrs)
                            bounds=g['time_bnds'][:]; epoch=datetime(1980,1,6,tzinfo=timezone.utc)
                            meta['period']=[(epoch+timedelta(seconds=float(x))).isoformat() for x in bounds.ravel()]
                            put('duration_seconds',np.diff(bounds,axis=1).ravel(),{'units':'s'})
                            dst.attrs['period_utc']=json.dumps(meta['period']);dst.attrs['qa_policy']='Quality index preserved; no arbitrary threshold; rates in mm/hr, not accumulated'
                elif source=='srtm':
                    import zipfile
                    if path.suffix=='.zip':
                        with zipfile.ZipFile(path) as z:
                            names=[n for n in z.namelist() if n.lower().endswith('.hgt')]
                            if len(names)!=1: raise ValueError('Expected exactly one HGT in ZIP')
                        uri=f'/vsizip/{path.resolve()}/{names[0]}'
                    else: uri=str(path)
                    with rasterio.open(uri) as r:
                        a=r.read(1,masked=True).astype('float32').filled(np.nan)
                        put('elevation',a,{'units':'m','vertical_datum':'EGM96 geoid'})
                        dst.attrs['crs']=r.crs.to_wkt();dst.attrs['transform']=list(r.transform);dst.attrs['period']='2000-02-11/2000-02-22'
                        put('x',r.transform.c+(np.arange(r.width)+0.5)*r.transform.a,{'units':'degrees_east'})
                        put('y',r.transform.f+(np.arange(r.height)+0.5)*r.transform.e,{'units':'degrees_north'})
                elif source=='modis':
                    from pyhdf.SD import SD,SDC
                    f=SD(str(path),SDC.READ)
                    try:
                        struct=f.attributes()['StructMetadata.0'].rstrip('\x00')
                        if 'Projection=GCTP_SNSOID' not in struct: raise ValueError('Unsupported MODIS projection')
                        def pair(k): return [float(v) for v in re.search(k+r'=\(([^)]+)\)',struct)[1].split(',')]
                        ul=pair('UpperLeftPointMtrs');lr=pair('LowerRightMtrs');radius=pair('ProjParams')[0]
                        dst.attrs['crs']=f'+proj=sinu +R={radius} +units=m +no_defs'
                        for label in ['NDVI','EVI','VI Quality','pixel reliability','composite day of the year']:
                            d=f.select('250m 16 days '+label);attrs=d.attributes();raw=d.get()
                            if label in ['NDVI','EVI']:
                                a=raw.astype('float32');a[raw==attrs['_FillValue']]=np.nan
                                lo,hi=attrs['valid_range'];a[(raw<lo)|(raw>hi)]=np.nan
                                a=(a-attrs.get('add_offset',0))/attrs['scale_factor']
                                attrs['applied_divisor']=attrs.pop('scale_factor');attrs['units']='1'
                            else: a=decode_array(raw,attrs)
                            attrs.pop('_FillValue',None);attrs['missing_representation']='NaN'
                            put(label.replace(' ','_'),a,attrs);d.endaccess()
                        h,w=dst['NDVI'].shape;dx=(lr[0]-ul[0])/w;dy=(lr[1]-ul[1])/h
                        put('x',ul[0]+(np.arange(w)+0.5)*dx,{'units':'m'});put('y',ul[1]+(np.arange(h)+0.5)*dy,{'units':'m'})
                        dst.attrs['transform']=[dx,0,ul[0],0,dy,ul[1]]
                        day=datetime.strptime(re.search(r'\.A(\d{7})',path.name)[1],'%Y%j');dst.attrs['period_start']=day.isoformat();dst.attrs['period_end_exclusive']=(day+timedelta(days=16)).isoformat()
                        q=dst['VI_Quality'][:];reliability=dst['pixel_reliability'][:];bits=np.nan_to_num(q,nan=65535).astype('uint16')
                        ok=(reliability==0)&((bits&3)==0)&np.isfinite(dst['NDVI'][:])&np.isfinite(dst['EVI'][:])
                        put('recommended_quality',ok.astype('uint8'),{'policy':'pixel reliability 0 AND MODLAND QA bits 0-1 == 0 AND both indices valid; full QA retained'})
                        dst.attrs['native_struct_metadata']=struct
                    finally: f.end()
                else: raise ValueError('Unsupported product')
                meta['geotemporal_metadata']={k:clean(v) for k,v in dst.attrs.items()}
            if self.usage()>self.settings['max_bytes']: raise ValueError('Storage budget exceeded')
            # Reopen every output dataset: compression/read integrity and dimensional verification.
            with h5py.File(tmp) as check:
                for name,stats in meta['quality'].items():
                    assert list(check[name].shape)==stats['shape']
                    assert np.isclose(float(np.isfinite(check[name][:]).mean()*100),100-stats['missing_percent'])
            if digest(path)!=sha: raise ValueError('Original changed during processing')
            tmp.replace(out);meta['output_sha256']=digest(out);meta['output_bytes']=out.stat().st_size
            dump(manifest,meta);return out
        except Exception:
            if tmp.exists(): tmp.unlink()
            raise


    def local_agronomy(self, source):
        """Offline, hash-bound processing of FAOSTAT and reviewed FAO-56 transcription."""
        import zipfile
        import pyarrow as pa
        import pyarrow.parquet as pq
        path=self.root/'data/raw'/source/('crops_livestock_global.zip' if source=='faostat' else 'FAO56.pdf')
        if not path.exists(): return
        manifest=self.root/'data/metadata'/f'{source}-local.json'
        out=self.root/'data/processed'/('faostat_yield_global.parquet' if source=='faostat' else 'fao56_kc_verified.parquet')
        sha=digest(path); config=self.root/'config/fao56_verified.json'
        signature=sha+(digest(config) if source=='fao56' else 'yield5412-v1')
        if manifest.exists() and out.exists():
            old=json.loads(manifest.read_text())
            if old.get('signature')==signature and old.get('output_sha256')==digest(out): return
        tmp=out.with_suffix('.part'); meta=dict(path=str(path.relative_to(self.root)),bytes=path.stat().st_size,input_sha256=sha,signature=signature,processed=str(out.relative_to(self.root)),status='downloaded and processed',source={'product':source,'institution':'FAO','units':'kg/ha' if source=='faostat' else 'dimensionless','url':'https://www.fao.org/faostat/en/#data/QCL' if source=='faostat' else 'https://www.fao.org/4/x0490e/x0490e00.htm'},license='Retain FAO attribution; consult source redistribution terms')
        try:
            if source=='faostat':
                count=0;years=set();areas=set();items=set();flags={};missing=0;negative=0;members={};writer=None
                with zipfile.ZipFile(path) as z:
                    names=[n for n in z.namelist() if n.endswith('(Normalized).csv')]
                    if len(names)!=1: raise ValueError('Expected one normalized CSV')
                    for name in z.namelist():
                        if name!=names[0]: members[name]=z.read(name).decode('utf-8-sig')
                    with z.open(names[0]) as stream:
                        for block in pd.read_csv(stream,dtype=str,chunksize=100000,encoding='utf-8-sig',keep_default_na=False):
                            df=select_crop_yield(block)
                            if df.empty: continue
                            years.update(df['Year']);areas.update(df['Area Code']);items.update(df['Item Code']);count+=len(df)
                            df['value_numeric']=pd.to_numeric(df['Value'],errors='raise').astype('float64');missing+=int(df.value_numeric.isna().sum());negative+=int((df.value_numeric<0).sum())
                            df['source_member']=names[0];df['source_sha256']=sha
                            for k,v in df.Flag.value_counts().items():flags[k]=flags.get(k,0)+int(v)
                            table=pa.Table.from_pandas(df,preserve_index=False)
                            if writer is None: writer=pq.ParquetWriter(tmp,table.schema,compression='zstd')
                            writer.write_table(table)
                            if self.usage()>self.settings['max_bytes']: raise ValueError('Storage budget exceeded')
                if writer: writer.close()
                if not count: raise ValueError('No verified crop yield rows')
                meta['quality']=dict(rows=count,years=[min(years),max(years)],areas=len(areas),items=len(items),flag_counts=flags,missing_values=missing,negative_values=negative,filter='Element Code 5412 AND Element Yield AND Unit kg/ha; all years and areas retained, including aggregates/historical entities',transformations='Original columns unchanged; numeric value added; no deduplication, imputation or crop crosswalk')
                meta['archive_dictionaries']=members
            else:
                j=json.loads(config.read_text())
                if j['pdf_sha256']!=sha: raise ValueError('PDF changed: visual review required before reusing transcription')
                df=pd.DataFrame(j['records']);df['general_conditions']=j['conditions'];df['source_sha256']=sha
                df['page_notes_text']=df.pdf_page.map(lambda n:j['page_text'][str(n)])
                df.to_parquet(tmp,index=False)
                meta['quality']=dict(rows=len(df),unique_labels=df.crop_label.nunique(),complete_triplets=int(df[['kc_initial','kc_mid','kc_end']].notna().all(axis=1).sum()),missing_initial=int(df.kc_initial.isna().sum()),pdf_pages=j['pdf_pages'],verified_pdf_pages=[136,137,138],review_pending=j['review_pending'],method='Curated transcription visually checked against rendered source; pinned to PDF SHA-256; original page text with footnotes embedded in Parquet')
                review=self.root/'data/metadata/fao56_manual_review.json'
                dump(review,{'source_sha256':sha,'status':'manual_review_required','scope':j['review_pending'],'page_text':j['page_text']})
            if self.usage()>self.settings['max_bytes']: raise ValueError('Storage budget exceeded')
            if digest(path)!=sha: raise ValueError('Original changed during processing')
            if pq.ParquetFile(tmp).metadata.num_rows!=meta['quality']['rows']: raise ValueError('Row count mismatch')
            tmp.replace(out);meta['output_sha256']=digest(out);meta['output_bytes']=out.stat().st_size;dump(manifest,meta)
        except Exception:
            if source=='faostat' and writer: writer.close()
            if tmp.exists(): tmp.unlink()
            raise


    def local_environment(self, source, path):
        path=Path(path);sha=digest(path)
        key=f'{source}-local-{sha[:16]}'
        manifest=self.root/'data/metadata'/f'{key}.json'
        # Retain the user's established output filename for this one original only.
        known='POWER_Point_Daily_20210101_20251231_036d59N_0119d52W_LST.csv'
        filename='ecocrop_validated.parquet' if source=='ecocrop' else ('power_california_2021_2025.parquet' if path.name==known else f'power-{path.stem}.parquet')
        out=self.root/'data/processed'/filename
        if manifest.exists() and out.exists():
            old=json.loads(manifest.read_text())
            if old.get('input_sha256')==sha and old.get('processor_version')==2 and old.get('output_sha256')==digest(out):return out
        if source=='ecocrop':
            df,quality=validate_ecocrop(pd.read_parquet(path));source_meta={'product':'EcoCrop local species reference','units':'See per-variable units in quality','url':'https://www.fao.org/geospatial/data-and-tools/data-portals/ecocrop/en','coverage':'Species reference; not all species are agricultural crops'}
        else:
            df,quality=read_power_csv(path);source_meta={'product':'POWER daily point CSV','units':quality['units'],'url':'https://power.larc.nasa.gov/','coverage':quality['coordinates'],'period':quality['period']}
        import pyarrow as pa
        import pyarrow.parquet as pq
        meta=dict(path=str(path.relative_to(self.root)),bytes=path.stat().st_size,input_sha256=sha,processor_version=2,processed=str(out.relative_to(self.root)),source=source_meta,quality=quality,status='downloaded and processed')
        table=pa.Table.from_pandas(df,preserve_index=False)
        table=table.replace_schema_metadata(dict(table.schema.metadata or {},field_shift=json.dumps(meta,default=str).encode()))
        tmp=out.with_suffix('.part')
        try:
            pq.write_table(table,tmp,compression='zstd')
            if self.usage()>self.settings['max_bytes']:raise ValueError('Storage budget exceeded')
            if digest(path)!=sha:raise ValueError('Original changed during processing')
            if pq.ParquetFile(tmp).metadata.num_rows!=len(df):raise ValueError('Row count mismatch')
            tmp.replace(out);meta.update(output_sha256=digest(out),output_bytes=out.stat().st_size);dump(manifest,meta)
        finally:
            if tmp.exists():tmp.unlink()
        return out


def select_crop_yield(block):
    """Crop yield code verified in the local FAOSTAT element dictionary; reject other units."""
    mask=(block['Element Code']=='5412') & (block['Element']=='Yield')
    if not block.loc[mask,'Unit'].eq('kg/ha').all(): raise ValueError('Unexpected crop yield unit; review required')
    return block.loc[mask].copy()


def decode_array(values, attrs):
    """Mask packed fill before scaling. Retain extremes for explicit QA review."""
    import numpy as np
    a=np.asarray(values,dtype=float).copy()
    fill=attrs.get('_FillValue',attrs.get('missing_value'))
    if fill is not None:
        for v in np.asarray(fill).ravel(): a[a==float(v)]=np.nan
    return a*float(attrs.get('scale_factor',1))+float(attrs.get('add_offset',0))

def validate_ecocrop(original):
    """Preserve all original columns; only *_usable is cleared by conservative checks."""
    import numpy as np
    df=original.copy();issues=[];invalid={};units={}
    groups=[(['tmin','topmn','topmx','tmax'],-100,100,'degC'),(['rmin','ropmn','ropmx','rmax'],0,None,'mm annual precipitation'),(['phmin','phopmn','phopmx','phmax'],0,14,'pH'),(['latmn','latopmn','latopmx','latmx'],0,90,'degrees absolute latitude'),(['gmin','gmax'],0,None,'days'),(['altmx'],None,None,'m'),(['ktmp','ktmpr'],-100,100,'degC')]
    def flag(mask,cols,reason):
        mask=mask.fillna(False)
        for c in cols: invalid[c]|=mask
        for pos in np.flatnonzero(mask.to_numpy(dtype=bool)):
            issues.append({'row_position_0_based':int(pos),'scientificname':str(original.iloc[pos].get('scientificname','')),'columns':cols,'reason':reason})
    for cols,lo,hi,unit in groups:
        cols=[c for c in cols if c in df]
        for c in cols:
            units[c]=unit;v=pd.to_numeric(df[c],errors='coerce').astype('Float64');df[c+'_usable']=v;invalid[c]=pd.Series(False,index=df.index)
            flag(df[c].notna()&v.isna(),[c],'not_numeric')
            if lo is not None:flag(v<lo,[c],'below_sanity_bound')
            if hi is not None:flag(v>hi,[c],'above_sanity_bound')
            if c in ['gmin','gmax']:flag(v==0,[c],'zero_cycle_unsuitable_for_duration_calculation')
        # Compare bounds only if each value passed its own sanity checks.
        for a,b in zip(cols,cols[1:]):
            if not cols or cols[0] not in ['tmin','rmin','phmin','gmin']:continue
            flag((df[a+'_usable']>df[b+'_usable'])&~invalid[a]&~invalid[b],[a,b],'inconsistent_order; neither endpoint auto-corrected')
    for c,bad in invalid.items():
        df[c+'_valid']=df[c+'_usable'].notna()&~bad
        df.loc[bad,c+'_usable']=pd.NA
    df['environment_has_invalid']=pd.DataFrame(invalid).any(axis=1)
    # Object/list columns cannot be hashed directly; canonical JSON is only for duplicate counting.
    canonical=original.map(lambda v:json.dumps(v.tolist() if isinstance(v,np.ndarray) else v,sort_keys=True,default=str) if isinstance(v,(list,dict,np.ndarray)) else v)
    quality=dict(rows=len(df),original_columns=len(original.columns),types=original.dtypes.astype(str).to_dict(),missing_percent=(original.isna().mean()*100).to_dict(),duplicates=int(canonical.duplicated().sum()),units=units,invalid_rows=int(df.environment_has_invalid.sum()),invalid_counts={c:int(v.sum()) for c,v in invalid.items()},issues=issues,statistics=df[[c+'_usable' for c in invalid]].describe().to_dict(),policy='Original attributes unchanged. Use *_usable or *_valid for calculations. Missing remains missing. Temperature sanity bounds [-100,100] C are screening bounds, not species requirements; no correction or cross-source matching. Categorical attributes retain source units/classes; unknown categories not numerically decoded.')
    return df,quality


def power_csv_for(latitude, longitude, root=ROOT):
    """The POWER export for exactly these coordinates, choosing the longest period on ties.

    Several downloads of the same point (different date ranges) may coexist. Picking the first
    filename alphabetically would be a silent choice, so the longest covered period wins and the
    chosen file is returned for the evidence trail. Identical periods are a real ambiguity: raise.
    """
    matches=[]
    for path in sorted((Path(root)/'data/raw/power').glob('*.csv')):
        df,quality=read_power_csv(path)
        if quality['coordinates']['latitude']!=latitude or quality['coordinates']['longitude']!=longitude:continue
        start,end=[pd.Timestamp(x) for x in quality['period']]
        matches.append(((end-start).days,str(path),path,df,quality))
    if not matches:return None,None,None
    matches.sort(key=lambda m:(-m[0],m[1]))
    if len(matches)>1 and matches[0][0]==matches[1][0]:
        raise ValueError('Several POWER exports cover the same period for this point: '+', '.join(m[2].name for m in matches[:2]))
    return matches[0][2],matches[0][3],matches[0][4]


def read_power_csv(path):
    import io,calendar
    text=Path(path).read_text(encoding='utf-8-sig')
    if '-END HEADER-' not in text:raise ValueError('Missing POWER header terminator')
    header,body=text.split('-END HEADER-',1);df=pd.read_csv(io.StringIO(body.strip()))
    variables=['T2M','T2M_MAX','T2M_MIN','PRECTOTCORR','RH2M','ALLSKY_SFC_SW_DWN','WS2M']
    if not set(['YEAR','DOY']+variables)<=set(df):raise ValueError('Required POWER columns missing')
    for c in ['YEAR','DOY']:
        if not pd.to_numeric(df[c],errors='raise').mod(1).eq(0).all():raise ValueError('Noninteger YEAR/DOY')
        df[c]=df[c].astype('int64')
    if any(d<1 or d>(366 if calendar.isleap(y) else 365) for y,d in zip(df.YEAR,df.DOY)):raise ValueError('DOY outside calendar year')
    df['fecha']=pd.to_datetime(df.YEAR.astype(str),format='%Y')+pd.to_timedelta(df.DOY-1,unit='D')
    loc=re.search(r'latitude\s+([-\d.]+)\s+longitude\s+([-\d.]+)',header)
    if not loc:raise ValueError('Missing point coordinates')
    lat,lon=map(float,loc.groups())
    if not (-90<=lat<=90 and -180<=lon<=180):raise ValueError('Invalid point coordinates')
    standard=re.search(r'in\s+(LST|UTC)\b',header)
    if not standard:raise ValueError('Unknown time standard')
    dates=re.search(r'Dates.*?:\s*(\d+/\d+/\d+)\s+through\s+(\d+/\d+/\d+)',header)
    if not dates:raise ValueError('Missing declared period')
    start,end=[pd.to_datetime(x,format='%m/%d/%Y') for x in dates.groups()]
    if (df.fecha<start).any() or (df.fecha>end).any():raise ValueError('Dates outside header period')
    units={}
    for v in variables:
        line=next((line for line in header.splitlines() if re.match(r'^'+v+r'\s',line)),None)
        if not line:raise ValueError(f'Missing unit description: {v}')
        units[v]=re.search(r'\(([^()]*)\)\s*$',line)[1]
        df[v]=pd.to_numeric(df[v],errors='raise').replace(-999,float('nan'))
    df['latitude']=lat;df['longitude']=lon;df['time_standard']=standard[1]
    invalid=((df.T2M_MIN>df.T2M)|(df.T2M>df.T2M_MAX)|(df.T2M_MIN>df.T2M_MAX))
    quality=dict(rows=len(df),variables=variables,units=units,coordinates={'latitude':lat,'longitude':lon,'crs':'EPSG:4326'},time_standard=standard[1],period=[str(start.date()),str(end.date())],missing_percent=(df[variables].isna().mean()*100).to_dict(),duplicate_dates=int(df.fecha.duplicated().sum()),missing_days=len(pd.date_range(start,end).difference(df.fecha)),temperature_order_violations=int(invalid.sum()),physical_range_violations={v:int(((df[v]<0)|((df[v]>100) if v=='RH2M' else False)).sum()) for v in ['RH2M','PRECTOTCORR','WS2M','ALLSKY_SFC_SW_DWN']},statistics=df[variables].describe().to_dict(),header_original=header+'-END HEADER-',coverage='Single point series, not global coverage',transformations='YEAR+DOY calendar validation; -999 to NaN; original variable names and units retained, no unit conversion or resampling. LST dates are not UTC instants.')
    return df,quality
