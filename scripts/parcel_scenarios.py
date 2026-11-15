import argparse,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.parcel_scenarios import scenarios
p=argparse.ArgumentParser(description='Offline parcel scenarios; no optimization')
p.add_argument('--input',type=Path);p.add_argument('--demo',action='store_true');a=p.parse_args()
if bool(a.input)==a.demo:p.error('Choose --input parcel.json OR --demo')
demo={'latitude':36.59,'longitude':-119.52,'current_crop':None,'previous_crops':[],
 'sowing_date':'2023-04-01','horizon_end':'2023-10-31','irrigation':{'available':None},'soil':{},
 'candidates':[{'crop':'Zea mays','harvest_date':'2023-09-30'},{'crop':'Glycine max','harvest_date':'2023-09-30'}],
 'assumptions':{'screen_season_mean_temperature':True}}
try:
 result=scenarios(demo if a.demo else json.loads(a.input.read_text()))
 if a.demo:result['demo_notice']='Hypothetical farmer plan, actual local NASA/FAO data; dates are not a recommended crop calendar'
 print(json.dumps(result,indent=2,ensure_ascii=False,allow_nan=False))
except (ValueError,KeyError,TypeError) as e:p.error(str(e))
