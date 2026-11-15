"""Parcel scenarios: declared facts, local evidence and unknowns remain distinct."""
import json, math
from datetime import date
from pathlib import Path
import pandas as pd
from .pipeline import ROOT, digest, power_csv_for
from .store import DataStore


def day(value):
    if not isinstance(value,str):raise ValueError('Dates must be ISO YYYY-MM-DD')
    result=date.fromisoformat(value)
    if result.isoformat()!=value:raise ValueError('Dates must be ISO YYYY-MM-DD')
    return result


def number(value,low,high):
    if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value) or not low<=value<=high:
        raise ValueError(f'Expected finite number in [{low}, {high}]')


def validate_input(value):
    if not isinstance(value,dict):raise ValueError('Parcel must be an object')
    allowed={'latitude','longitude','current_crop','previous_crops','sowing_date','horizon_end','irrigation','soil','candidates','assumptions'}
    if set(value)-allowed:raise ValueError('Unknown parcel fields: '+str(set(value)-allowed))
    number(value['latitude'],-90,90);number(value['longitude'],-180,180)
    start,end=day(value['sowing_date']),day(value['horizon_end'])
    if start>=end:raise ValueError('Horizon must follow sowing')
    if value.get('current_crop') is not None and (not isinstance(value['current_crop'],str) or not value['current_crop'].strip()):raise ValueError('Invalid current crop')
    history=value.get('previous_crops',[])
    if not isinstance(history,list):raise ValueError('previous_crops must be a list')
    for h in history:
        if set(h)!={'crop','start','end'} or not isinstance(h['crop'],str) or not h['crop'].strip() or not day(h['start'])<day(h['end'])<=start:raise ValueError('Invalid crop history')
    ordered=sorted(history,key=lambda h:h['start'])
    if any(day(a['end'])>day(b['start']) for a,b in zip(ordered,ordered[1:])):raise ValueError('Overlapping crop history; intercropping not supported')
    irrigation=value.get('irrigation',{'available':None})
    if not isinstance(irrigation,dict):raise ValueError('Irrigation must be an object')
    if set(irrigation)-{'available','seasonal_mm'} or irrigation.get('available') not in [True,False,None]:raise ValueError('Invalid irrigation')
    if irrigation.get('available') is not None and type(irrigation['available']) is not bool:raise ValueError('Irrigation availability must be boolean/null')
    if irrigation.get('seasonal_mm') is not None:
        number(irrigation['seasonal_mm'],0,100000)
        if irrigation.get('available') is not True:raise ValueError('Irrigation amount requires declared availability')
    soil=value.get('soil',{})
    if not isinstance(soil,dict):raise ValueError('Soil must be an object')
    for k,v in soil.items():
        if k not in ['ph','texture','nitrogen_kg_ha']:raise ValueError('Unsupported soil variable/unit')
        if v is None:continue
        if k=='ph':number(v,0,14)
        elif k=='nitrogen_kg_ha':number(v,0,100000)
        elif not isinstance(v,str):raise ValueError('Soil texture must be text')
    candidates=value['candidates']
    if not isinstance(candidates,list) or not candidates:raise ValueError('Candidates required')
    names=[]
    for c in candidates:
        if set(c)-{'crop','harvest_date','fao_calendar'}:raise ValueError('Unknown candidate field')
        if not isinstance(c['crop'],str) or not c['crop'].strip():raise ValueError('Exact crop name required')
        names.append(c['crop'])
        if c.get('harvest_date') and not start<day(c['harvest_date'])<=end:raise ValueError('Harvest outside horizon')
        cal=c.get('fao_calendar')
        if cal is not None and set(cal)!={'country','crop_id','aez_id','source_record','session_index'}:raise ValueError('Complete FAO calendar selector required')
    if len(set(names))!=len(names):raise ValueError('Duplicate candidates')
    assumptions=value.get('assumptions',{})
    if set(assumptions)-{'screen_season_mean_temperature'} or any(type(v) is not bool for v in assumptions.values()):raise ValueError('Unknown assumption')
    return value


def seasonal_climate(latitude,longitude,start,end,root=ROOT):
    """Inclusive sowing/harvest dates, no prorating monthly rainfall or filling days."""
    start,end=day(start),day(end)
    if start>end:raise ValueError('Invalid season interval')
    path,df,q=power_csv_for(latitude,longitude,root)
    if path is not None:
        if q['units']['PRECTOTCORR']!='mm/day':raise ValueError('Unsupported rainfall units')
        d=df[df.fecha.between(pd.Timestamp(start),pd.Timestamp(end))]
        expected=pd.date_range(start,end)
        complete=len(d)==len(expected) and not d.fecha.duplicated().any() and set(d.fecha)==set(expected)
        valid=complete and d.PRECTOTCORR.notna().all() and d.PRECTOTCORR.ge(0).all()
        return dict(source='NASA POWER estimated point export',source_path=str(path.relative_to(root)),sha256=digest(path),
            latitude=latitude,longitude=longitude,start=str(start),end_inclusive=str(end),time_standard=q['time_standard'],
            expected_days=len(expected),available_days=len(d),complete=complete,
            rainfall_mm=float(d.PRECTOTCORR.sum()) if valid else None,
            temperature_mean_c=float(d.T2M.mean()) if complete and d.T2M.notna().all() else None,
            support='coarse model grid served as point; not parcel/station measurement')
    return dict(source='NASA POWER',complete=False,rainfall_mm=None,temperature_mean_c=None,reason='No local series at exact coordinates; no spatial extrapolation')


def gaez_context(latitude,longitude,crop,root=ROOT):
    """Contextual historical SIX stored codes; never additional independent climate votes."""
    import rasterio
    mapping={'Zea mays':'MZE','Triticum aestivum':'WHE','Glycine max':'SOY'}
    code=mapping.get(crop)
    result=dict(source='FAO GAEZ V5',climate_lineage='AgERA5',period='2001–2020',
        use='context only; not additive evidence or parcel prediction',layers=[],
        excluded='YCX/WDE/CYL: unresolved units; LT5: not a crop suitability index; empty files unusable')
    if code is None:result['missing']='No explicit reviewed RES05 crop mapping';return result
    inventory=json.loads((Path(root)/'data/metadata/audit/raw_integrity.json').read_text())['files']
    hashes={r['path']:r['sha256'] for r in inventory}
    for management in ['HRLM','HILM']:
        p=Path(root)/f'data/raw/gaez/GAEZ-V5.RES05-SIX.HP0120.AGERA5.HIST.{code}.{management}.tif'
        if not p.exists() or not p.stat().st_size:continue
        rel=str(p.relative_to(root))
        if digest(p)!=hashes.get(rel):raise ValueError('GAEZ changed since audit')
        with rasterio.open(p) as ds:
            if str(ds.crs)!='EPSG:4326':raise ValueError('Unexpected GAEZ CRS')
            if not ds.bounds.left<=longitude<ds.bounds.right or not ds.bounds.bottom<latitude<=ds.bounds.top:continue
            sample=next(ds.sample([(longitude,latitude)],masked=True))[0]
            v=None if sample is pd.NA or bool(getattr(sample,'mask',False)) else float(sample)
            if v is not None and (not math.isfinite(v) or not 1<=v<=9):v=None
            result['layers'].append(dict(path=rel,sha256=hashes[rel],value=v,units='SIX stored code 1–9; legend unverified; zero is NoData',
                interpretation='Local uint8 rasters contradict previous 0–10000 index description; do not rank or convert to percentage',
                resolution_degrees=list(ds.res),management='rainfed high inputs' if management=='HRLM' else 'irrigated high inputs',
                applicability='Management scenario not confirmed for parcel; no automatic score'))
    return result


def calendar_check(parcel,candidate,root=ROOT):
    selector=candidate.get('fao_calendar')
    if selector is None:return dict(status='unverified_plan',source='farmer',reason='Valid proposed dates do not verify local agronomic calendar')
    frame=DataStore(root).crop_reference('calendar',selector['crop_id'],area=selector['country'])
    if frame.empty:return dict(status='unknown',reason='No local calendar for selector')
    frame=frame[(frame.aez_id==selector['aez_id']) & (frame.source_record==selector['source_record']) & (frame.session_index==selector['session_index'])]
    if len(frame)!=1 or frame.iloc[0].seasonal_date_invalid:return dict(status='unusable',reason='Ambiguous selector or invalid source endpoints')
    comparisons={}
    for event,early,late,target in [('sowing','early_sowing','later_sowing',parcel['sowing_date']),('harvest','early_harvest','late_harvest',candidate.get('harvest_date'))]:
        try:
            row=frame.iloc[0]
            low=(int(row['session_'+early+'_month']),int(row['session_'+early+'_day']))
            high=(int(row['session_'+late+'_month']),int(row['session_'+late+'_day']))
            actual=day(target);point=(actual.month,actual.day)
            comparisons[event]=(low<=point<=high) if low<=high else (point>=low or point<=high)
        except (TypeError,ValueError,KeyError):comparisons[event]=None
    # Taxonomic and spatial mappings cannot be certified by a supplied selector alone.
    return dict(status='reference_found_mapping_unverified',source='FAO Crop Calendar',
        reference=selector,date_window_checks=comparisons,reason='Need verified mapping of exact candidate taxon and parcel to FAO crop and agroecological zone',
        endpoints={c:str(frame.iloc[0][c]) for c in frame if c.endswith(('_month','_day'))})


def scenarios(parcel,root=ROOT):
    validate_input(parcel);results=[]
    for c in parcel['candidates']:
        climate=seasonal_climate(parcel['latitude'],parcel['longitude'],parcel['sowing_date'],c['harvest_date'],root) if c.get('harvest_date') else {'rainfall_mm':None,'reason':'Harvest date unknown'}
        calendar=calendar_check(parcel,c,root)
        ref=DataStore(root).crop_reference('ecocrop',c['crop'])
        factors=[]
        if len(ref)==1:
            r=ref.iloc[0]
            for name,value,lo,hi in [('soil_ph',parcel.get('soil',{}).get('ph'),'phmin','phmax'),
                ('season_mean_temperature_c',climate.get('temperature_mean_c'),'tmin','tmax')]:
                if name.startswith('season') and not parcel.get('assumptions',{}).get('screen_season_mean_temperature',False):continue
                if value is not None and bool(r[lo+'_valid']) and bool(r[hi+'_valid']):
                    factors.append(dict(variable=name,value=value,bounds=[float(r[lo+'_usable']),float(r[hi+'_usable'])],
                        status='within_reference_bounds' if r[lo+'_usable']<=value<=r[hi+'_usable'] else 'outside_reference_bounds',
                        observation_source='farmer declaration' if name=='soil_ph' else 'NASA POWER',range_source='FAO EcoCrop',
                        assumption='season mean is only a screening statistic' if name.startswith('season') else None))
        results.append(dict(crop=c['crop'],status='insufficiently_documented',climate=climate,calendar=calendar,
            factors=factors,gaez=gaez_context(parcel['latitude'],parcel['longitude'],c['crop'],root),
            water=dict(status='unknown',rainfall_mm=climate.get('rainfall_mm'),irrigation_declared=parcel.get('irrigation'),
                reason='No verified seasonal crop demand, effective rainfall, irrigation efficiency or soil water storage; annual EcoCrop rainfall bounds are not seasonal requirements'),
            required=['verified local crop calendar and taxon/zone mapping','seasonal water balance','verified family/previous-crop transition constraints','soil nutrient balance','objective and costs']))
    return dict(input=parcel,provenance={'farmer':'All supplied parcel fields except assumptions; declarations not independently verified',
        'NASA_FAO':'Per-factor source and GAEZ lineage','assumptions':parcel.get('assumptions',{}),
        'unknown':'Null/absent fields and required lists; never replaced with zero'},
        scenarios=results,comparison={'mode':'side-by-side factors only','ranking':None,'reason':'No common verified water/calendar constraints'},rotation_sequence=None)
