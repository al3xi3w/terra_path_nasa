"""Reproducible offline audit. Original data are read-only; no acquisition clients."""
from pathlib import Path
import json
import re
import numpy as np
import pandas as pd
import h5py
from .pipeline import ROOT, Pipeline, digest, dump, decode_array, read_power_csv

VERSION = 1
GPM_VARIABLES = ['precipitation', 'randomError', 'gaugeRelativeWeighting',
                 'probabilityLiquidPrecipitation', 'precipitationQualityIndex']


def text(value):
    if isinstance(value, bytes):
        return value.decode('utf8')
    return str(value)


def attributes(dataset):
    result = {}
    for k, v in dataset.attrs.items():
        if k in ['DIMENSION_LIST', 'REFERENCE_LIST', 'CLASS', 'NAME']:
            continue
        if isinstance(v, bytes): v = v.decode('utf8')
        elif isinstance(v, np.ndarray): v = v.tolist()
        elif isinstance(v, np.generic): v = v.item()
        result[k] = v
    return result


def profile(df):
    # Nested objects in existing tables are represented canonically for comparison only.
    canonical = df.map(lambda v: json.dumps(v.tolist() if isinstance(v, np.ndarray) else v,
                                           sort_keys=True, default=str)
                       if isinstance(v, (dict, list, np.ndarray)) else v)
    return dict(rows=len(df), columns=list(df.columns), types=df.dtypes.astype(str).to_dict(),
                missing=df.isna().sum().astype(int).to_dict(),
                exact_duplicates=int(canonical.duplicated().sum()))


def write_table(df, path, metadata):
    import pyarrow as pa
    import pyarrow.parquet as pq
    path.parent.mkdir(parents=True, exist_ok=True)
    table = pa.Table.from_pandas(df, preserve_index=False)
    table = table.replace_schema_metadata({**(table.schema.metadata or {}),
        b'fieldshift': json.dumps(metadata, default=str, sort_keys=True).encode()})
    temp = path.with_suffix('.part')
    pq.write_table(table, temp, compression='zstd')
    temp.replace(path)


def audit_gpm(path):
    """Read every science cell in bounded longitude strips; validate native semantics."""
    path = Path(path)
    report = dict(path=str(path), bytes=path.stat().st_size, sha256=digest(path), errors=[])
    errors = report['errors']
    with h5py.File(path, 'r') as f:
        header = dict(re.findall(r'([^;\n=]+)=([^;]*);', text(f.attrs['FileHeader'])))
        report['header'] = header
        start = pd.Timestamp(header['StartGranuleDateTime'])
        end = pd.Timestamp(header['StopGranuleDateTime'])
        next_month = start + pd.offsets.MonthBegin(1)
        if start != start.normalize() or start.day != 1 or end != next_month-pd.Timedelta(milliseconds=1):
            errors.append('header_not_full_calendar_month')
        if header.get('TimeInterval') != 'MONTH' or header.get('AlgorithmID') != '3IMERGM':
            errors.append('wrong_monthly_product')
        if header.get('ProductVersion') != 'V07B': errors.append('unexpected_product_version')
        report.update(month=start.strftime('%Y-%m'), start=start.isoformat(),
                      end_exclusive=next_month.isoformat())
        filename_date = re.search(r'3IMERG\.(\d{8})-', header.get('FileName',''))
        if not filename_date or filename_date[1] != start.strftime('%Y%m%d'):
            errors.append('filename_date_disagrees_with_header')
        g = f['Grid']; time_attrs = attributes(g['time'])
        if time_attrs.get('units') != 'seconds since 1980-01-06 00:00:00 UTC':
            raise ValueError('Unsupported time epoch/unit')
        if time_attrs.get('calendar') not in ['julian', 'standard', 'gregorian']:
            raise ValueError('Unsupported calendar')
        # Julian/Gregorian elapsed days agree for this 1980–2026 interval (no 2100).
        if not (1980 <= start.year < 2100): raise ValueError('Time calendar needs review')
        epoch = pd.Timestamp('1980-01-06', tz='UTC')
        bounds = g['time_bnds'][:]
        if attributes(g['time_bnds']).get('units') != time_attrs.get('units'):
            errors.append('time_bounds_units_disagree')
        if bounds.shape != (1, 2): raise ValueError('Unexpected time bounds shape')
        decoded = [epoch + pd.Timedelta(seconds=int(v)) for v in bounds[0]]
        if decoded != [start, next_month]: errors.append('time_bounds_disagree_with_header')
        if g['time'].shape != (1,) or not bounds[0, 0] <= g['time'][0] < bounds[0, 1]:
            errors.append('representative_time_outside_bounds')
        report.update(time_attributes=time_attrs, duration_hours=float(np.diff(bounds)[0, 0]/3600))
        coords = {}
        for name, size, low, high, unit in [('lon',3600,-180,180,'degrees_east'),
                                           ('lat',1800,-90,90,'degrees_north')]:
            a = g[name][:]; b = g[name+'_bnds'][:]
            good = (a.shape == (size,) and b.shape == (size,2) and np.isfinite(a).all()
                    and np.all(np.diff(a)>0) and np.allclose(np.diff(a),0.1,atol=3e-5)
                    and np.allclose(b.mean(axis=1),a,atol=3e-5)
                    and np.allclose(b[:,1]-b[:,0],0.1,atol=3e-5)
                    and np.allclose(b[1:,0],b[:-1,1],atol=3e-5)
                    and np.isclose(b[0,0],low) and np.isclose(b[-1,1],high)
                    and text(g[name].attrs['units']) == unit)
            if not good: errors.append(name+'_invalid_coordinates')
            coords[name] = dict(count=len(a), minimum=float(a.min()), maximum=float(a.max()),
                                bounds=[float(b.min()),float(b.max())], units=unit, valid=bool(good))
        report['coordinates'] = coords; report['variables'] = {}
        for name in GPM_VARIABLES:
            if name not in g:
                errors.append('missing_'+name); continue
            d = g[name]; attrs = attributes(d)
            if '_FillValue' not in attrs: errors.append(name+'_missing_fill_definition')
            if d.shape != (1,3600,1800) or attrs.get('DimensionNames') != 'time,lon,lat':
                raise ValueError('Unexpected dimensions: '+name)
            expected_units = {'precipitation':'mm/hr','randomError':'mm/hr',
                              'gaugeRelativeWeighting':'percent','probabilityLiquidPrecipitation':'percent'}
            if name in expected_units and attrs.get('units') != expected_units[name]:
                errors.append(name+'_unexpected_units')
            count = missing = negative = above100 = 0
            total = 0.; minimum = np.inf; maximum = -np.inf
            for offset in range(0,d.shape[1],120):
                a = decode_array(d[:,offset:offset+120,:],dict(d.attrs))
                valid = a[np.isfinite(a)]; count += a.size; missing += a.size-valid.size
                if valid.size:
                    minimum=min(minimum,float(valid.min()));maximum=max(maximum,float(valid.max()))
                    total += float(valid.sum());negative += int((valid<0).sum())
                    if name in ['gaugeRelativeWeighting','probabilityLiquidPrecipitation']:
                        above100 += int((valid>100).sum())
            report['variables'][name] = dict(attributes=attrs, cells=count, missing=missing,
                missing_percent=100*missing/count, negative=negative, above100=above100,
                minimum=minimum if count>missing else None, maximum=maximum if count>missing else None,
                mean=total/(count-missing) if count>missing else None)
            if negative or above100: errors.append(name+'_outside_physical_range')
        report['status'] = 'validated' if not errors else 'quarantined'
    return report


def clean_sentinel(path, as_of='2026-11-14'):
    df = pd.read_csv(path); quality = profile(df)
    required = ['pilot','lat','lon','month','n_scenes_used','n_scenes_total','pct_valid_pixels']
    required += [f'{index}_{stat}' for index in ['ndvi','ndmi'] for stat in ['mean','median','min','max','p10','p90']]
    if not set(required) <= set(df): raise ValueError('Missing Sentinel columns')
    df['source_row'] = np.arange(len(df))+2
    df['date'] = pd.to_datetime(df.month, errors='coerce')
    df['invalid_date'] = df.date.isna() | df.date.dt.day.ne(1)
    df['incomplete_or_future_month'] = df.date.ge(pd.Timestamp(as_of).to_period('M').start_time)
    df['invalid_coordinates'] = ~df.lat.between(-90,90) | ~df.lon.between(-180,180)
    df['duplicate_key'] = df.duplicated(['pilot','month'],keep=False)
    df['invalid_scene_counts'] = (~df.n_scenes_used.ge(0) | ~df.n_scenes_total.ge(df.n_scenes_used)
        | df.n_scenes_used.mod(1).ne(0) | df.n_scenes_total.mod(1).ne(0)
        | ~df.pct_valid_pixels.between(0,100))
    for index in ['ndvi','ndmi']:
        columns = [f'{index}_{s}' for s in ['min','p10','median','p90','max']]
        values = df[columns]
        df[index+'_inconsistent_summary'] = (values.diff(axis=1).iloc[:,1:] < -1e-7).any(axis=1)
        df[index+'_inconsistent_summary'] |= ((df[index+'_mean'] < df[index+'_min']-1e-7)
                                                 | (df[index+'_mean'] > df[index+'_max']+1e-7))
        all_values = df[[c for c in required if c.startswith(index+'_')]]
        df[index+'_outside_range'] = ((all_values < -1) | (all_values > 1)).any(axis=1)
        df[index+'_missing'] = all_values.isna().any(axis=1)
        flags = ['invalid_date','incomplete_or_future_month','invalid_coordinates','duplicate_key',
                 'invalid_scene_counts',index+'_inconsistent_summary',index+'_outside_range',index+'_missing']
        df[index+'_usable'] = ~df[flags].any(axis=1) & df.n_scenes_used.gt(0) & df.pct_valid_pixels.gt(0)
    quality.update(flags={c:int(df[c].sum()) for c in df if df[c].dtype==bool},
                   locations=df[['pilot','lat','lon']].drop_duplicates().to_dict('records'),
                   start=str(df.date.min().date()), end=str(df.date.max().date()),
                   missing_months_by_pilot={str(k):pd.date_range(g.date.min(),g.date.max(),freq='MS').difference(g.date).strftime('%Y-%m').tolist() for k,g in df.groupby('pilot')},
                   units='NDVI/NDMI dimensionless; percent valid pixels 0–100; scenes count',
                   spatial_resolution='Unknown aggregation footprint; coordinates are pilot labels, not polygons',
                   limitations='Export lacks extraction script, cloud mask, geometry, band resolution and scene IDs. Summary inconsistencies retained, not repaired. Current month is incomplete. No crop labels.')
    return df, quality


def clean_nass(path):
    df = pd.read_csv(path,dtype=str,keep_default_na=False)
    quality = profile(df.replace('',pd.NA));df['source_row']=np.arange(len(df))+2
    df['year'] = pd.to_numeric(df.Year,errors='coerce').astype('Int64')
    if df.year.isna().any() or not df.Period.eq('YEAR').all(): raise ValueError('Unsupported NASS period')
    df['period_start'] = pd.to_datetime(df.year.astype(str)+'-01-01')
    df['period_end_exclusive'] = df.period_start + pd.offsets.YearBegin(1)
    df['unit'] = df['Data Item'].str.extract(r'MEASURED IN (.+)$',expand=False)
    df['value_numeric'] = pd.to_numeric(df.Value.str.replace(',','',regex=False),errors='coerce')
    df['value_status'] = np.where(df.value_numeric.notna(),'numeric',df.Value.str.strip().replace('','missing'))
    df['cv_numeric'] = pd.to_numeric(df['CV (%)'],errors='coerce')
    df['county_fips'] = (df['State ANSI'].str.zfill(2)+df['County ANSI'].str.zfill(3)).where(
        df['Geo Level'].eq('COUNTY') & df['State ANSI'].str.fullmatch(r'\d{1,2}') & df['County ANSI'].str.fullmatch(r'\d{1,3}'))
    # Unit, management/type, domain, geography and program remain part of the key.
    keys = [c for c in pd.read_csv(path,nrows=0).columns if c not in ['Value','CV (%)']]
    df['duplicate_key'] = df.duplicated(keys,keep=False)
    df['usable'] = df.value_numeric.ge(0) & df.unit.notna() & ~df.duplicate_key & df.county_fips.notna()
    quality.update(years=[int(df.year.min()),int(df.year.max())], units=df.unit.unique().tolist(),
        locations=df[['Geo Level','State','County','county_fips']].drop_duplicates().to_dict('records'),
        value_status=df.value_status.value_counts().to_dict(), duplicate_keys=int(df.duplicate_key.sum()),
        invalid_values=int((df.value_numeric<0).sum()), items=df['Data Item'].value_counts().to_dict(),
        years_by_item={k:sorted(g.year.astype(int).unique().tolist()) for k,g in df.groupby('Data Item')},
        limitations='County annual survey yields; no parcel boundaries or crop rotation histories. Preserve BU / ACRE; no unverified commodity bushel-to-mass conversion. CV absent is unknown uncertainty, not zero.')
    return df, quality


def month_coverage(records, start='2021-01', end='2025-12'):
    months = pd.Series([r['month'] for r in records if r.get('status')=='validated'],dtype=str)
    counts=months.value_counts()
    return dict(files=len(records), validated_files=len(months), unique_months=int(months.nunique()),
                duplicate_months=counts[counts>1].to_dict(),
                missing_months=sorted(set(pd.period_range(start,end,freq='M').astype(str))-set(months)),
                unexpected_months=sorted(set(months)-set(pd.period_range(start,end,freq='M').astype(str))))


def calendar_flags(frame):
    """Check seasonal endpoints against a leap reference year, without assigning a year."""
    result=frame.copy()
    invalid=pd.Series(False,index=frame.index)
    for column in frame:
        if column.endswith(('_month','_day')):
            number=pd.to_numeric(frame[column],errors='coerce')
            maximum=12 if column.endswith('_month') else 31
            invalid |= frame[column].notna() & (~number.between(1,maximum) | number.mod(1).ne(0))
        if not column.endswith('_day'):continue
        month=column[:-4]+'_month'
        if month not in frame:continue
        supplied=frame[column].notna() & frame[month].notna()
        dates=pd.to_datetime(dict(year=pd.Series(2000,index=frame.index),
            month=pd.to_numeric(frame[month],errors='coerce').astype(float),
            day=pd.to_numeric(frame[column],errors='coerce').astype(float)),errors='coerce')
        flag=supplied & dates.isna()
        result[column+'_invalid_date']=flag
        invalid |= flag
    result['seasonal_date_invalid']=invalid
    # Missing endpoints remain unknown; this is not a complete crop-suitability mask.
    return result


def extract_gpm(path, points, report):
    if report['status'] != 'validated': return []
    rows=[]
    with h5py.File(path,'r') as f:
        g=f['Grid']; lats=g['lat'][:]; lons=g['lon'][:]
        for point in points:
            lat,lon=float(point['latitude']),float(point['longitude'])
            if not (-90<=lat<=90 and -180<=lon<180): raise ValueError('Invalid query coordinates')
            i=int(np.argmin(abs(lons-lon))); j=int(np.argmin(abs(lats-lat)))
            row=dict(location_id=point['location_id'],latitude=lat,longitude=lon,
                cell_latitude=float(lats[j]),cell_longitude=float(lons[i]),cell_lon_index=i,cell_lat_index=j,
                period_start=report['start'],period_end_exclusive=report['end_exclusive'],
                source_path=report['path'],source_sha256=report['sha256'],duration_hours=report['duration_hours'])
            for name in GPM_VARIABLES:
                row[name]=float(decode_array(g[name][0,i,j],dict(g[name].attrs)))
            row['quality_status']='present_qa_unthresholded' if np.isfinite(row['precipitation']) else 'missing'
            rows.append(row)
    return rows


def audit_existing(root, raw_inventory):
    """Verify lineage, actual tables and native rasters without downloading or rewriting raw."""
    import rasterio
    results=[]
    raw_by_path={r['path']:r for r in raw_inventory}
    for path in sorted((root/'data/metadata').glob('*.json')):
        meta=json.loads(path.read_text())
        if not isinstance(meta,dict) or 'path' not in meta: continue
        rel=meta['path']
        if rel.startswith('data/raw/gpm_monthly/'): continue
        raw=raw_by_path.get(rel)
        if raw is None: continue
        source=Path(rel).parts[2]
        if source not in ['power','smap','modis','srtm','gpm','gaez','agronomy','ecocrop','faostat','fao56']:continue
        record=dict(source=source, manifest=str(path.relative_to(root)),path=rel,
                    bytes=raw['bytes'],sha256=raw['sha256'],provenance=meta.get('source',{}))
        expected=meta.get('input_sha256',meta.get('sha256'))
        record['input_hash_match']=expected==raw['sha256'] if expected else None
        record['status']='verified' if record['input_hash_match'] else 'unverified_lineage'
        if raw['bytes']==0:record['status']='empty_original'
        output=meta.get('processed')
        if output:
            out=root/output;record['processed']=output
            if not out.exists():record['status']='missing_processed'
            else:
                record['output_sha256']=digest(out)
                expected_output=meta.get('output_sha256')
                record['output_hash_match']=record['output_sha256']==expected_output if expected_output else None
                if expected_output and not record['output_hash_match']:record['status']='processed_hash_mismatch'
                try:
                    if out.suffix=='.parquet':
                        df=pd.read_parquet(out);record['quality']=profile(df)
                        if source=='faostat':
                            record['quality'].update(years=[int(df.Year.min()),int(df.Year.max())],
                                areas=int(df['Area Code'].nunique()),items=int(df['Item Code'].nunique()),
                                flags=df.Flag.value_counts().to_dict(),units=df.Unit.unique().tolist(),
                                duplicate_keys=int(df.duplicated(['Area Code','Item Code','Element Code','Year'],keep=False).sum()))
                        elif source=='agronomy' and 'calendar-' in out.name:
                            checked=calendar_flags(df)
                            record['quality']['invalid_seasonal_rows']=int(checked.seasonal_date_invalid.sum())
                            record['quality']['invalid_seasonal_row_positions']=np.flatnonzero(checked.seasonal_date_invalid).tolist()
                            month_cols=[c for c in df if c.endswith('_month')]
                            record['quality']['invalid_months']={c:int((df[c].notna()&~pd.to_numeric(df[c],errors='coerce').between(1,12)).sum()) for c in month_cols}
                            day_cols=[c for c in df if c.endswith('_day')]
                            record['quality']['invalid_days']={c:int((df[c].notna()&~pd.to_numeric(df[c],errors='coerce').between(1,31)).sum()) for c in day_cols}
                            record['quality']['invalid_seasonal_dates']={}
                            for col in day_cols:
                                month_col=col[:-4]+'_month'
                                if month_col not in df:continue
                                supplied=df[col].notna() & df[month_col].notna()
                                dates=pd.to_datetime(dict(year=pd.Series(2000,index=df.index),
                                    month=pd.to_numeric(df[month_col],errors='coerce').astype(float),
                                    day=pd.to_numeric(df[col],errors='coerce').astype(float)),errors='coerce')
                                record['quality']['invalid_seasonal_dates'][col]=int((supplied & dates.isna()).sum())
                        elif source=='agronomy' and 'id' in df:
                            record['quality']['duplicate_identifiers']=int(df.id.duplicated(keep=False).sum())
                        elif source=='ecocrop':
                            record['quality']['invalid_rows']=int(df.environment_has_invalid.sum())
                    elif out.suffix=='.h5':
                        grids={}
                        with h5py.File(out,'r') as f:
                            def scan(name,d):
                                if not isinstance(d,h5py.Dataset):return
                                missing=0;count=0;low=np.inf;high=-np.inf
                                for sl in d.iter_chunks() if d.chunks else [tuple(slice(None) for _ in d.shape)]:
                                    a=d[sl]; v=a[np.isfinite(a)];count+=a.size;missing+=a.size-v.size
                                    if v.size:low=min(low,float(v.min()));high=max(high,float(v.max()))
                                grids[name]=dict(shape=list(d.shape),missing=missing,cells=count,
                                    minimum=low if count>missing else None,maximum=high if count>missing else None,
                                    attributes=attributes(d))
                            f.visititems(scan)
                        record['quality']=grids
                except Exception as error:
                    record.update(status='unreadable_processed',error=str(error))
        if source=='gaez' and Path(rel).suffix=='.tif':
            record['excluded_from_integration']='AgERA5-derived GAEZ; conservative exclusion under no-ERA5 restriction; units also unresolved for several variables'
            if raw['bytes']:
                try:
                    with rasterio.open(root/rel) as ds:
                        count=missing=0;lo=np.inf;hi=-np.inf
                        for _,window in ds.block_windows(1):
                            a=ds.read(1,window=window,masked=True);v=a.compressed();count+=a.size;missing+=a.size-v.size
                            if v.size:lo=min(lo,float(v.min()));hi=max(hi,float(v.max()))
                        record['quality']=dict(shape=[ds.count,ds.height,ds.width],crs=str(ds.crs),
                            resolution=list(ds.res),bounds=list(ds.bounds),nodata=ds.nodata,
                            missing=missing,cells=count,minimum=lo if count>missing else None,
                            maximum=hi if count>missing else None,tags=ds.tags(),units=list(ds.units))
                except Exception as error:record.update(status='unreadable_original',error=str(error))
        results.append(record)
    return results


def integrate(root, sentinel, nass, gpm, power_frames, locations):
    """Long observations with explicit support. No implicit spatial or crop joins."""
    rows=[]
    def add(source, location, start, end, variable, value, unit, quality, path, sha,
            spatial, temporal, crop=None, source_row=None, extra=None):
        rows.append(dict(source=source,location_id=location,period_start=str(start),
            period_end_exclusive=str(end),variable=variable,value=value,unit=unit,
            quality_status=quality,source_path=path,source_sha256=sha,spatial_support=spatial,
            temporal_support=temporal,crop_id=crop,source_row=source_row,
            details_json=json.dumps(extra or {},default=str)))
    s_path='data/raw/ndvi_s2_mensual_todos.csv';s_sha=digest(root/s_path)
    for _,r in sentinel.iterrows():
        for index in ['ndvi','ndmi']:
            add('sentinel2','sentinel2:'+r.pilot,r.date,r.date+pd.offsets.MonthBegin(1),index+'_mean',
                r[index+'_mean'],'1','screened_provenance_pending' if r[index+'_usable'] else 'review_required',
                s_path,s_sha,'pilot aggregation; footprint unknown','monthly export',source_row=int(r.source_row),
                extra={c:r[c] for c in ['n_scenes_used','n_scenes_total','pct_valid_pixels',index+'_inconsistent_summary','incomplete_or_future_month']})
    for r in gpm:
        add('gpm_monthly',r['location_id'],r['period_start'],r['period_end_exclusive'],
            'precipitation_rate',r['precipitation'],'mm/hr',r['quality_status'],r['source_path'],r['source_sha256'],
            '0.1 degree native cell','monthly mean rate',extra={k:v for k,v in r.items() if k not in ['source_path','source_sha256']})
    for path,df,q in power_frames:
        sha=digest(path); rel=str(path.relative_to(root));location=f"power:{q['coordinates']['latitude']}:{q['coordinates']['longitude']}"
        for _,r in df.iterrows():
            for variable in q['variables']:
                value=r[variable]
                invalid=(variable in ['RH2M','WS2M','PRECTOTCORR','ALLSKY_SFC_SW_DWN'] and (value<0 or (variable=='RH2M' and value>100)))
                if variable in ['T2M','T2M_MIN','T2M_MAX']:
                    invalid |= r.T2M_MIN>r.T2M or r.T2M>r.T2M_MAX
                add('power',location,r.fecha,r.fecha+pd.Timedelta(days=1),variable,value,q['units'][variable],
                    'missing' if pd.isna(value) else ('review_required' if invalid else 'screened'),rel,sha,
                    'point export; meteorology ~0.5x0.625 degree; solar ~1 degree','daily '+q['time_standard'])
    npath='data/raw/USDA_NASS_CALIFORNIA.csv';nsha=digest(root/npath)
    for _,r in nass.iterrows():
        add('usda_nass','us_county:'+str(r.county_fips),r.period_start,r.period_end_exclusive,
            r['Data Item'],r.value_numeric,r.unit,'screened_cv_unknown' if r.usable and pd.isna(r.cv_numeric) else ('screened' if r.usable else 'review_required'),
            npath,nsha,'county aggregate; no polygon available','annual',crop='nass:'+r.Commodity,
            source_row=int(r.source_row),extra={'data_item':r['Data Item'],'domain':r.Domain,
                'domain_category':r['Domain Category'],'cv_percent':None if pd.isna(r.cv_numeric) else r.cv_numeric,'value_status':r.value_status})
    observations=pd.DataFrame(rows)
    # Date-only support and time standards remain explicit; never call LST timestamps UTC.
    for c in ['period_start','period_end_exclusive']:
        observations[c]=observations[c].map(lambda v:pd.Timestamp(v).strftime('%Y-%m-%d'))
    observations['observation_id']=[f'{s}:{i}' for i,s in enumerate(observations.source)]
    write_table(observations,root/'data/integrated/observations.parquet',
        {'version':VERSION,'policy':'No imputation, no cross-source joins; filter quality explicitly; reference datasets remain in native tables'})
    write_table(pd.DataFrame(locations),root/'data/integrated/locations.parquet',{'crs':'EPSG:4326','county geometry':'not supplied'})
    return observations


def run_audit(root=ROOT, as_of='2026-11-14'):
    root=Path(root); pipeline=Pipeline(root)
    raw_files=sorted(p for p in (root/'data/raw').rglob('*') if p.is_file())
    inventory=[dict(path=str(p.relative_to(root)),bytes=p.stat().st_size,sha256=digest(p)) for p in raw_files]
    print(f'Hashed {len(inventory)} originals',flush=True)
    output=root/'data/processed';audit_dir=root/'data/metadata/audit';audit_dir.mkdir(parents=True,exist_ok=True)
    s,sq=clean_sentinel(root/'data/raw/ndvi_s2_mensual_todos.csv',as_of)
    n,nq=clean_nass(root/'data/raw/USDA_NASS_CALIFORNIA.csv')
    for name,df,quality,raw in [('sentinel2_monthly',s,sq,'ndvi_s2_mensual_todos.csv'),('usda_nass',n,nq,'USDA_NASS_CALIFORNIA.csv')]:
        metadata=dict(version=VERSION,as_of=as_of,source_path='data/raw/'+raw,source_sha256=digest(root/'data/raw'/raw),quality=quality)
        write_table(df,output/(name+'.parquet'),metadata)
        metadata['output_sha256']=digest(output/(name+'.parquet'));dump(audit_dir/(name+'.json'),metadata)
    points=[dict(location_id='sentinel2:'+r['pilot'],latitude=r['lat'],longitude=r['lon']) for r in sq['locations']]
    locations=[dict(p,spatial_support='pilot aggregation; footprint unknown') for p in points]
    power_frames=[]
    for path in sorted((root/'data/raw/power').glob('*.csv')):
        df,q=read_power_csv(path);pipeline.local_environment('power',path);power_frames.append((path,df,q))
        p=dict(location_id=f"power:{q['coordinates']['latitude']}:{q['coordinates']['longitude']}",
               latitude=q['coordinates']['latitude'],longitude=q['coordinates']['longitude'])
        points.append(p);locations.append(dict(p,spatial_support='POWER point export'))
    for r in nq['locations']:locations.append(dict(location_id='us_county:'+r['county_fips'],
        latitude=None,longitude=None,spatial_support='county aggregate',country='US',state=r['State'],county=r['County']))
    records=[];extracted=[];corrections=[]
    for i,path in enumerate(sorted((root/'data/raw/gpm_monthly').glob('*.HDF5'))):
        try:
            record=audit_gpm(path);record['path']=str(path.relative_to(root))
            sidecar=root/'data/metadata'/('gpm_monthly-'+path.name+'.json')
            old=json.loads(sidecar.read_text()) if sidecar.exists() else {}
            match=re.search(r'3IMERG\.(\d{8})-',old.get('url',''))
            if match and match[1][:6]!=record['month'].replace('-',''):
                record['errors'].append('url_month_mismatch');record['status']='quarantined'
            if old.get('bytes')!=record['bytes'] or old.get('sha256')!=record['sha256']:
                corrections.append(dict(path=str(sidecar.relative_to(root)),previous_bytes=old.get('bytes'),
                    previous_sha256=old.get('sha256'),observed_bytes=record['bytes'],observed_sha256=record['sha256']))
                if record['status']=='validated':
                    old.setdefault('recovery_audit_history',[]).append(corrections[-1])
                    old.update(bytes=record['bytes'],sha256=record['sha256'],path=record['path'],
                        status='locally validated recovered monthly file',integrity_scope='Local SHA-256 baseline; no independent provider checksum available')
            old['local_audit']=dict(status=record['status'],month=record['month'],errors=record['errors'],report='data/metadata/audit/gpm_monthly.json')
            dump(sidecar,old)
            extracted.extend(extract_gpm(path,points,record));records.append(record)
        except Exception as error:
            records.append(dict(path=str(path.relative_to(root)),status='quarantined',errors=[str(error)]))
        print(f'GPM {i+1}: {records[-1].get("month",path.name)} {records[-1]["status"]}',flush=True)
    coverage=month_coverage(records)
    # Ambiguous months cannot enter the feature store, even when individual grids pass.
    duplicate_months=set(coverage['duplicate_months'])
    extracted=[r for r in extracted if r['period_start'][:7] not in duplicate_months]
    dump(audit_dir/'gpm_monthly.json',dict(coverage=coverage,files=records,corrections=corrections,
        qa_policy='Full-grid missing/range audit; quality index preserved without undocumented cutoff. No accumulation.'))
    compact=[]
    for r in records:
        compact.append({k:r.get(k) for k in ['path','bytes','sha256','month','start','end_exclusive','duration_hours','status']} |
                       {'errors':json.dumps(r['errors']), 'statistics_json':json.dumps(r.get('variables',{}),default=str)})
    write_table(pd.DataFrame(compact),output/'gpm_monthly_index.parquet',{'full_report':'data/metadata/audit/gpm_monthly.json'})
    write_table(pd.DataFrame(extracted),output/'gpm_monthly_points.parquet',{'points':'existing Sentinel/POWER coordinates only','units':'mm/hr; percent weighting/probability; QA native','grid':'0.1 degree; nearest cell, not interpolation'})
    # Existing processors are reused only when the original exists and is not empty.
    for source in ['ecocrop']:
        pipeline.local_environment(source,root/'data/raw/ecocrop/ecocrop.parquet')
    for source in ['faostat','fao56']:pipeline.local_agronomy(source)
    existing=audit_existing(root,inventory)
    dump(audit_dir/'existing_sources.json',existing)
    observations=integrate(root,s,n,extracted,power_frames,locations)
    write_table(pd.DataFrame([dict(source=r['source'],path=r['path'],processed=r.get('processed'),
        status=r['status'],metadata_json=json.dumps(r,default=str)) for r in existing]),
        root/'data/integrated/catalog.parquet',{'policy':'Reference lookup; GAEZ excluded; empty originals untrusted'})
    after=[dict(path=str(p.relative_to(root)),bytes=p.stat().st_size,sha256=digest(p)) for p in raw_files]
    if after!=inventory:raise RuntimeError('Raw input changed during audit')
    dump(audit_dir/'raw_integrity.json',{'unchanged':True,'files':inventory,'empty_files':[r['path'] for r in inventory if not r['bytes']]})
    summary=dict(as_of=as_of,version=VERSION,raw_files=len(inventory),raw_unchanged=True,
        empty_originals=[r['path'] for r in inventory if not r['bytes']],gpm=coverage,
        gpm_points=len(extracted),sentinel=sq,nass=nq,
        observations=len(observations),observation_counts=observations.source.value_counts().to_dict(),
        existing_source_statuses=pd.Series([r['status'] for r in existing]).value_counts().to_dict())
    summary['outputs']=[dict(path=str(p.relative_to(root)),bytes=p.stat().st_size,sha256=digest(p))
        for p in [output/'sentinel2_monthly.parquet',output/'usda_nass.parquet',
                  output/'gpm_monthly_index.parquet',output/'gpm_monthly_points.parquet',
                  root/'data/integrated/observations.parquet',root/'data/integrated/locations.parquet',
                  root/'data/integrated/catalog.parquet']]
    summary['nass_gpm_overlap_2021_rows']=int(n.year.eq(2021).sum())
    dump(audit_dir/'summary.json',summary)
    write_report(root,summary,existing)
    return summary


def write_report(root, summary, existing):
    calendar_entries=[r for r in existing if 'calendar-' in r.get('processed','')]
    invalid_calendar_rows=sum(r.get('quality',{}).get('invalid_seasonal_rows',0) for r in calendar_entries)
    invalid_calendar_files=[Path(r['path']).stem for r in calendar_entries if r.get('quality',{}).get('invalid_seasonal_rows',0)]
    lines=['# Auditoría local vigente', '',f"Corte de evaluación: {summary['as_of']} (America/Lima). Ejecución offline; originales sin cambios.",
           '', 'Este informe reemplaza las afirmaciones históricas de cobertura en los otros informes.', '',
           f"GPM: {summary['gpm']['validated_files']} archivos validados; {summary['gpm']['unique_months']} meses únicos; faltan {', '.join(summary['gpm']['missing_months'])} del intervalo 2021–2025.",
           f"Extracción compacta: {summary['gpm_points']} filas en coordenadas existentes. Sin expansión de la grilla global ni acumulación de tasas.",
           'Se leen todas las celdas de las cinco variables mensuales por bloques, coordenadas/límites, fechas, duración, versión, unidades y rangos. SHA local no es checksum independiente del proveedor.',
           '', '## Sentinel-2', f"{summary['sentinel']['rows']} filas; {len(summary['sentinel']['locations'])} ubicaciones; {summary['sentinel']['start']} a {summary['sentinel']['end']}.",
           'Indicadores: '+json.dumps(summary['sentinel']['flags'],ensure_ascii=False),summary['sentinel']['limitations'],
           '', '## USDA NASS', f"{summary['nass']['rows']} filas, años {summary['nass']['years']}, unidades {summary['nass']['units']}.",
           'Cobertura: '+json.dumps(summary['nass']['locations'],ensure_ascii=False),summary['nass']['limitations'],
           '', '## Fuentes existentes']
    for source in ['power','smap','modis','gpm','srtm','gaez','faostat','ecocrop','fao56','agronomy']:
        entries=[r for r in existing if r['source']==source]
        counts=pd.Series([r['status'] for r in entries]).value_counts().to_dict()
        tables={r['processed']:r.get('quality',{}).get('rows') for r in entries if r.get('processed','').endswith('.parquet')}
        lines += [f"- {source}: {len(entries)} manifiestos inspeccionados, estados {counts}; filas de tablas: {sum(v or 0 for v in tables.values())}."]
    lines += ['', 'Los conteos de manifiestos no equivalen a datasets únicos. El catálogo conserva cada ruta, hashes, dimensiones, estadísticas y unidades.',
              'SMAP, MODIS y GPM de media hora tienen originales vacíos: sus derivados son legibles pero no se integran como datos verificados. SRTM es un mosaico local estático de febrero de 2000.',
              'GAEZ: 17 GeoTIFF inventariados; se comprueba cada raster legible. Todos llevan AGERA5: se excluyen de integración cuantitativa por la restricción de no usar ERA5. Una capa está vacía. Las unidades no corroboradas siguen pendientes.',
              'FAOSTAT conserva áreas agregadas/históricas y flags A/E/X; no constituye etiquetas de parcela. FAO-56 conserva extracción parcial y condiciones; EcoCrop solo permite cálculos con *_usable. Crop Calendar usa país/zona/sesión estacional sin inventar año ni correspondencias.',
              f'Crop Calendar: {invalid_calendar_rows} filas con extremos estacionales inválidos en {invalid_calendar_files}. Se retienen; crop_reference añade seasonal_date_invalid y flags por extremo. Faltantes siguen siendo desconocidos; febrero 29 se admite como fecha estacional.',
              '', '## Integración y bloqueos de Machine Learning',
              f"{summary['observations']} observaciones largas, con soporte espacial/temporal, unidades, ruta/hash, estado de calidad y detalles de origen. No es una tabla de entrenamiento.",
              '- Resolver exportación Sentinel: polígonos, fechas de extracción, máscaras, escenas y significado de mínimos/percentiles. Noviembre 2026 se marca incompleto.',
              '- Revisar integridad de originales vacíos sin modificarlos en esta etapa; no confiar solo en derivados antiguos.',
              '- Definir área, cultivo, objetivo y unidad de predicción; no emparejar Fresno con puntos sin límites administrativos. NASS solo solapa 2021 con la serie mensual GPM disponible.',
              '- Acordar correspondencias taxonómicas/variantes con identificadores de cada fuente. No se ha inventado un crosswalk.',
              '- Definir QA GPM y reglas de agregación; tasas mensuales no son acumulaciones ni mediciones parcelarias.',
              '- Definir temporadas y particiones espaciales/temporales para evitar fuga; datos anuales agregados no identifican rotaciones observadas.',
              '- Documentar restricciones de suelo, riego, plagas, precedencias y función objetivo antes de optimizar rotaciones.',
              '', '## Trazabilidad',
              'Detalle reproducible en data/metadata/audit/*.json. raw_integrity.json registra todos los tamaños/hashes antes y después; no hubo cambios de bytes en originales. Correcciones de sidecars GPM conservan el hash/tamaño previos.',
              'No se descargaron datasets, entrenaron modelos, desarrolló frontend ni ejecutaron commits/push.']
    (root/'reports/local_audit.md').write_text('\n'.join(lines)+'\n')
    (root/'reports/data_inventory.md').write_text('\n'.join([
        '# Inventario vigente', '', f"{summary['raw_files']} archivos originales inventariados por tamaño y SHA-256; bytes originales sin cambios.",
        'Cobertura y limitaciones por fuente: [auditoría local](local_audit.md).',
        'Inventario completo: data/metadata/audit/raw_integrity.json. Fuentes existentes: data/metadata/audit/existing_sources.json.',
        '', '## Derivados nuevos',
        *[f"- {r['path']}: {r['bytes']} bytes; SHA-256 {r['sha256']}." for r in summary['outputs']],
        '', '## Originales vacíos', *['- '+p for p in summary['empty_originals']],
        '', 'Las grillas originales permanecen nativas; no se materializa una tabla global de píxeles.'])+'\n')
    (root/'reports/data_quality.md').write_text('\n'.join([
        '# Calidad vigente', '', 'Ver [auditoría local](local_audit.md) para cobertura, registros y bloqueos.',
        'GPM: datos científicos completos leídos por bloques; reportes por variable en data/metadata/audit/gpm_monthly.json.',
        'Sentinel: flags conservadores; ninguna fila NDVI usable. No corregir inconsistencias sin revisar exportación.',
        'NASS: códigos geográficos y variantes preservados, sin conversión de bushels. CV ausente no equivale a cero.',
        'SMAP/MODIS/GPM media hora: originales vacíos; derivados no verificables contra ellos.',
        'GAEZ local derivado de AgERA5 excluido de integración. No se utiliza ERA5, ECOSTRESS ni Landsat.',
        'Los hashes/tamaños GPM coincidían con los sidecars. Se añadió local_audit sin reemplazar hashes correctos.',
        'Originales sin alteraciones: data/metadata/audit/raw_integrity.json. Pruebas: [resultados](test_results.md).',
        'La revisión anterior se conserva como historial en quality_review.md; no sustituye esta auditoría.'])+'\n')
    (root/'reports/batch_coverage.md').write_text('\n'.join([
        '# Cobertura local verificada (sin adquisición)', '',
        f"IMERG mensual: {summary['gpm']['unique_months']}/60 meses únicos, enero 2021–septiembre 2025; faltan octubre–diciembre 2025.",
        'Las 57 entradas son archivos locales con validación científica, no solo resultados de catálogo.',
        f"Extracción: {summary['gpm_points']} filas para siete puntos existentes. No hay grilla global Parquet.",
        'Sentinel: 71 meses por cada uno de seis pilotos; noviembre 2026 incompleto al corte.',
        'POWER: un punto, 1.826 días (2021–2025). NASS: Fresno, 1945–2021; solo un registro de 2021 solapa con GPM.',
        'No hay una serie mensual SMAP/MODIS validada localmente. Sus originales de ejemplo están vacíos.',
        'Los snapshots de catálogos históricos no demuestran cobertura local utilizable. No se realizaron descargas.',
        'Detalle y restricciones: [auditoría local](local_audit.md).'])+'\n')
