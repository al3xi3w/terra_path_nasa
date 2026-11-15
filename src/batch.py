"""Bounded batch orchestration around existing Pipeline; no implicit coordinates."""
import hashlib,json,os,time
from pathlib import Path
import requests,yaml,pandas as pd
from src.pipeline import Pipeline,dump,digest


def retry_get(url,**kwargs):
    for attempt in range(3):
        try:
            r=requests.get(url,timeout=(15,60),**kwargs)
            if r.status_code in [429,500,502,503,504] and attempt<2:
                time.sleep(2**attempt);continue
            r.raise_for_status();return r
        except requests.ConnectionError:
            if attempt==2:raise
            time.sleep(2**attempt)


def power_variables(year,variables):
    return [v for v in variables if v!='ALLSKY_SFC_SW_DWN' or year>=1984]


def existing_power(p,lat,lon,year,variables,standard):
    needed=set(pd.date_range(f'{year}-01-01',f'{year}-12-31').strftime('%Y%m%d'))
    for m in (p.root/'data/metadata').glob('power*.json'):
        j=json.loads(m.read_text())
        if not isinstance(j,dict) or 'path' not in j:continue
        raw=p.root/j['path']
        if not raw.exists() or digest(raw)!=j.get('sha256',j.get('input_sha256')):continue
        q=j.get('params') or {};quality=j.get('quality',{})
        if q and q.get('latitude')==lat and q.get('longitude')==lon and q.get('time-standard')==standard:
            data=json.loads(raw.read_text()).get('properties',{}).get('parameter',{})
            if all(needed<=set(data.get(v,{})) for v in variables):return str(raw)
        coords=quality.get('coordinates',{})
        if coords.get('latitude')==lat and coords.get('longitude')==lon and quality.get('time_standard')==standard and set(variables)<=set(quality.get('variables',[])):
            from src.pipeline import read_power_csv
            frame,_=read_power_csv(raw)
            if needed<=set(frame.fecha.dt.strftime('%Y%m%d')):return str(raw)
    return None


class Batch:
    def __init__(self,p=None):
        self.p=p or Pipeline();self.cfg=yaml.safe_load((self.p.root/'config/batch.yaml').read_text())
        self.dir=self.p.root/'data/metadata/batch';self.dir.mkdir(exist_ok=True)
        baseline=self.dir/'baseline.json'
        if not baseline.exists():dump(baseline,{'bytes':self.p.usage()})
        self.baseline=json.loads(baseline.read_text())['bytes']
        # Keep previous total-storage ceiling as an additional conservative guard.
        self.p.settings['max_bytes']=min(self.p.settings['max_bytes'],self.baseline+self.cfg['new_data_max_bytes'])
        self.events=[]
    def event(self,source,status,**info):
        self.events.append(dict(source=source,status=status,**info));dump(self.dir/'last_run.json',self.events)
    def power(self):
        for point in self.cfg['power_points']:
            lat=float(point['latitude']);lon=float(point['longitude'])
            if not(-90<=lat<=90 and -180<=lon<=180):raise ValueError('Invalid coordinates')
            for year in range(self.cfg['power_start_year'],self.cfg['power_end_year']+1):
                variables=power_variables(year,self.p.settings['power_variables']);standard=self.cfg['power_time_standard']
                if existing_power(self.p,lat,lon,year,variables,standard):
                    self.event('power','reused',year=year,coordinates=point);continue
                q=dict(latitude=lat,longitude=lon,start=f'{year}0101',end=f'{year}1231',parameters=','.join(variables),community='AG',format='JSON',**{'time-standard':standard})
                key=hashlib.sha256(json.dumps(q,sort_keys=True).encode()).hexdigest()[:20]
                try:
                    for attempt in range(3):
                        try:raw=self.p.fetch('power',key+'.json','https://power.larc.nasa.gov/api/temporal/daily/point',q);break
                        except requests.RequestException:
                            if attempt==2:raise
                            time.sleep(2**attempt)
                    data=json.loads(raw.read_text())['properties']['parameter'];days=pd.date_range(f'{year}-01-01',f'{year}-12-31').strftime('%Y%m%d')
                    coverage={v:sum(d in data.get(v,{}) and data[v][d]!=-999 for d in days)/len(days)*100 for v in variables}
                    self.event('power','downloaded',year=year,coordinates=point,coverage_percent=coverage,path=str(raw))
                except Exception as e:self.event('power','error',year=year,error=type(e).__name__)
        if not self.cfg['power_points']:self.event('power','on_demand_no_coordinates_configured')
    def global_gaez(self):
        # Existing verified global suitability catalog; complementary irrigation management.
        path=self.p.root/'data/raw/gaez/catalog-RES05-SIX.json'
        if not path.exists():self.event('gaez','missing_local_catalog');return
        for o in json.loads(path.read_text()).get('items',[]):
            if not any('.'+c+'.HILM.' in o['name'] for c in ['MZE','SOY','WHE']):continue
            name=Path(o['name']).name;exists=(self.p.root/'data/raw/gaez'/name).exists()
            try:
                raw=self.p.fetch('gaez',name,o['mediaLink'],expected=int(o['size']))
                m=self.p.root/'data/metadata'/f'gaez-{name}.json';j=json.loads(m.read_text())
                j['source']=dict(self.p.sources['gaez'],product='RES05-SIX',units='index 0–10000',resolution='5 arcminutes',period='2001–2020',management='irrigated; high input',coverage='global');dump(m,j)
                self.event('gaez','reused' if exists else 'downloaded',path=str(raw),bytes=raw.stat().st_size)
            except Exception as e:self.event('gaez','error',file=name,error=type(e).__name__)
    def monthly(self,download=False):
        for product in self.cfg['monthly_global']:
            source=product['source'];self.p.sources[source]=dict(product,url='https://cmr.earthdata.nasa.gov/',coverage='global',resolution='monthly',units='native product attributes; not yet processed')
            try:
                cache=self.dir/(source+'-catalog.json')
                if cache.exists():j=json.loads(cache.read_text())
                else:
                    r=retry_get('https://cmr.earthdata.nasa.gov/search/granules.json',params={'short_name':product['product'],'version':product['version'],'temporal':'2021-01-01T00:00:00Z,2025-12-31T23:59:59Z','page_size':2000,'sort_key':'start_date'})
                    j={'hits':int(r.headers.get('CMR-Hits',0)),'entries':r.json()['feed']['entry']};dump(cache,j)
                entries=j['entries']
                if len(entries)!=j['hits']:raise ValueError('Catalog incomplete; pagination required')
                if not entries:raise ValueError('No granules')
                estimated=sum(float(x['granule_size'])*1024**2 for x in entries)
                months=sorted(set(x['time_start'][:7] for x in entries)); downloaded=[]
                can_auth=all(os.getenv(k) for k in ['EARTHDATA_USERNAME','EARTHDATA_PASSWORD'])
                if estimated>self.p.settings['max_bytes']-self.p.usage():status='exceeds_remaining_budget'
                elif not download:status='catalog_only'
                elif not can_auth:status='requires_earthdata_credentials'
                else:
                    import earthaccess
                    if not earthaccess.login(strategy='environment').authenticated:raise RuntimeError('Authentication failed')
                    session=earthaccess.get_requests_https_session()
                    for entry in entries:
                        links=[x['href'] for x in entry.get('links',[]) if x.get('rel','').endswith('/data#') and x['href'].startswith('https://') and not x.get('inherited',False)]
                        if not links:raise ValueError('No verified HTTPS data link')
                        raw=self.p.fetch(source,entry['id']+Path(links[0]).suffix,links[0],session=session)
                        downloaded.append(str(raw))
                    status='downloaded_pending_product_processing'
                self.event(source,status,granules=len(entries),estimated_bytes=int(estimated),missing_months=sorted(set(pd.period_range('2021-01','2025-12',freq='M').astype(str))-set(months)),available_months=len(months),catalog_temporal_percent=100*len(months)/60,local_months=len(downloaded),local_percent=100*len(downloaded)/60,files=downloaded)
            except Exception as e:self.event(source,'error',error=type(e).__name__,detail=str(e) if isinstance(e,ValueError) else 'See provider access/credentials')
    def appeears(self):
        base='https://appeears.earthdatacloud.nasa.gov/api';points=self.cfg['satellite_points']
        if not points:self.event('appeears','on_demand_no_coordinates_configured');return
        layers=self.cfg['appeears_layers']
        for product in set(x['product'] for x in layers):
            catalog=retry_get(base+'/product/'+product).json()
            if any(x['layer'] not in catalog for x in layers if x['product']==product):raise ValueError('Unknown layer; review provider catalog')
        if not all(os.getenv(k) for k in ['EARTHDATA_USERNAME','EARTHDATA_PASSWORD']):self.event('appeears','requires_earthdata_credentials');return
        response=requests.post(base+'/login',auth=(os.environ['EARTHDATA_USERNAME'],os.environ['EARTHDATA_PASSWORD']),timeout=60);response.raise_for_status()
        session=requests.Session();session.headers['Authorization']='Bearer '+response.json()['token']
        for year in range(2021,2026):
            body={'task_type':'point','task_name':f'FieldShift-{year}','params':{'dates':[{'startDate':f'01-01-{year}','endDate':f'12-31-{year}'}],'layers':layers,'coordinates':points}}
            key=hashlib.sha256(json.dumps(body,sort_keys=True).encode()).hexdigest()[:20];state=self.dir/('appeears-'+key+'.json')
            if state.exists():task=json.loads(state.read_text())
            else:
                # Persist intent first: uncertain POST outcomes require review, never blind resubmission.
                dump(state,{'request':body,'status':'submission_intent'})
                r=session.post(base+'/task',json=body,timeout=60);r.raise_for_status();task={'request':body,'task_id':r.json()['task_id']};dump(state,task)
            if 'task_id' not in task:raise RuntimeError('Submission outcome uncertain; inspect AppEEARS task list before retry')
            tid=task['task_id'];r=session.get(base+'/task/'+tid,timeout=60);r.raise_for_status();status=r.json()['status']
            if status!='done':self.event('appeears',status,year=year,task_id=tid);continue
            r=session.get(base+'/bundle/'+tid,timeout=60);r.raise_for_status();bundle=r.json();dump(self.dir/f'appeears-{key}-bundle.json',bundle)
            self.p.sources['appeears']={'product':'AppEEARS point extraction','version':'see task layers','url':base,'period':str(year),'coordinates':points}
            for f in bundle['files']:
                name=key+'-'+Path(f['file_name']).name
                raw=self.p.fetch('appeears',name,base+'/bundle/'+tid+'/'+f['file_id'],expected=f['file_size'],session=session)
                if digest(raw)!=f['sha256']:raise ValueError('Provider checksum mismatch')
            self.event('appeears','downloaded_native_exports_pending_schema_validation',year=year,task_id=tid)
    def probe_complementary(self):
        catalog=retry_get('https://appeears.earthdatacloud.nasa.gov/api/product').json()
        products=['MOD13Q1.061','SPL3SMP.009','SRTMGL1_NC.003','HLSL30.020','HLSS30.020','ECO_L2T_LSTE.002']
        found={x['ProductAndVersion']:x for x in catalog if x.get('ProductAndVersion') in products}
        dump(self.dir/'appeears-products.json',found)
        for name in products:
            if name not in found:self.event(name,'not_in_provider_catalog');continue
            layers=retry_get('https://appeears.earthdatacloud.nasa.gov/api/product/'+name).json()
            dump(self.dir/(name+'-layers.json'),layers)
            self.event(name,'provider_catalog_verified_on_demand',available=found[name].get('Available'),layer_count=len(layers))
        self.event('ERA5','pending_client_and_CDS_credentials',endpoint='https://cds.climate.copernicus.eu/datasets/reanalysis-era5-single-levels-monthly-means',credential_available=bool(os.getenv('CDSAPI_KEY')))
        self.event('USDA_NASS','pending_client_and_API_key',endpoint='https://quickstats.nass.usda.gov/api',credential_available=bool(os.getenv('NASS_API_KEY')),coverage='United States only')

    def report(self):
        text=['# Cobertura de lotes','',f'Datos utilizados: {self.p.usage()} bytes. Incremento desde inicio: {self.p.usage()-self.baseline} bytes.','No hay coordenadas obligatorias. La disponibilidad de catálogo NO equivale a descarga local.','', '```json',json.dumps(self.events,indent=2),'```']
        (self.p.root/'reports/batch_coverage.md').write_text('\n'.join(text))


def run_batch(mode):
    b=Batch()
    if mode=='batch':b.global_gaez();b.monthly(download=True);b.power();b.appeears();b.probe_complementary()
    elif mode=='batch-power':b.power()
    elif mode=='batch-appeears':b.appeears()
    elif mode=='batch-monthly':b.monthly(download=True)
    b.p.process();b.p.reports();b.report()
