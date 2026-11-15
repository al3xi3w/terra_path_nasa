import argparse,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.crop_screen import monthly_climate,evaluate_crop,rotation_context,LAT,LON
p=argparse.ArgumentParser(description='Offline annual climate screening; no rotation recommendation')
p.add_argument('--crops',nargs='+',required=True);p.add_argument('--start',default='2021-01');p.add_argument('--end',default='2024-12');p.add_argument('--current-crop')
a=p.parse_args();climate=monthly_climate()
print(json.dumps(dict(monthly_rows=len(climate),evaluations=[evaluate_crop(climate,c,start=a.start,end=a.end) for c in a.crops],rotation=rotation_context(a.current_crop,a.crops,LAT,LON,a.start,a.end)),indent=2,ensure_ascii=False))
