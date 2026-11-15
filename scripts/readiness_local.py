"""Focused readiness diagnostics; no network or rewriting of original/large tables."""
import sys,json
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import pandas as pd
from src.audit import calendar_flags
from src.pipeline import ROOT,dump

def run():
 s=pd.read_parquet(ROOT/'data/processed/sentinel2_monthly.parquet');issues=[]
 for _,r in s.iterrows():
  for index in ['ndvi','ndmi']:
   for stat in ['mean','median','min','max','p10','p90']:
    c=index+'_'+stat;v=r[c]
    if pd.notna(v) and not -1<=v<=1:issues.append(dict(source='sentinel2',source_row=int(r.source_row),pilot=r.pilot,month=r.month,field=c,value=float(v),reason='outside_index_range'))
   if r[index+'_inconsistent_summary']:issues.append(dict(source='sentinel2',source_row=int(r.source_row),pilot=r.pilot,month=r.month,field=index,value=None,reason='summary_order_or_mean_outside_extrema'))
 calendars=[]
 for p in sorted((ROOT/'data/processed').glob('agronomy-calendar-*.parquet')):
  d=calendar_flags(pd.read_parquet(p))
  for pos,r in d[d.seasonal_date_invalid].iterrows():
   calendars.append(dict(path=str(p.relative_to(ROOT)),row_position=int(pos),source_record=int(r.source_record),session_index=int(r.session_index),crop_id=r.crop_id,usable=False,reason='invalid_seasonal_endpoint',original_endpoints={c:None if pd.isna(r[c]) else str(r[c]) for c in d if c.endswith(('_day','_month'))}))
 dump(ROOT/'data/metadata/audit/readiness_issues.json',dict(sentinel=issues,calendars=calendars,policy='No objectively inferable numeric correction; preserve original values; invalid dates excluded from scheduling'))
 return len(calendars)
if __name__=='__main__':print(run())
