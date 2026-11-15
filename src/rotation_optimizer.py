"""Small deterministic experimental optimizer; no inferred agricultural parameters."""
from itertools import product
import math
from .parcel_scenarios import validate_input,day

# 'declared': farmer statement; 'derived': computed from verified local NASA/FAO data (src/constraints.py).
STATUSES=['hypothetical','documented','declared','derived']


def parameter(value,unit):
    if not isinstance(value,dict) or value.get('unit')!=unit or not value.get('provenance') or value.get('status') not in STATUSES:
        raise ValueError('Parameter requires unit, provenance and an accepted status')
    v=value.get('value')
    if isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v) or v<0:raise ValueError('Invalid parameter value')
    return v


def optimize(data):
    """All mandatory evidence explicitly supplied; objectives are optional, lexicographic."""
    result=dict(status='abstained',evaluation='experimental_not_agronomically_validated',feasible=[],discarded=[],missing=[],criteria=[],best=None)
    try:
        validate_input(data['parcel'])
        seasons=data['seasons'];crops=data['crops'];rules=data['transitions']
        if len(seasons) not in [2,3] or not 1<=len(crops)<=8:raise ValueError('Use 2–3 seasons and 1–8 crops')
        if set(crops)!={c['crop'] for c in data['parcel']['candidates']}:raise ValueError('Candidate mismatch')
        previous=data['parcel'].get('current_crop')
        if not previous:raise ValueError('Current/preceding crop required')
        objectives=data.get('objectives',[])
        if len(set(objectives))!=len(objectives) or any(o not in ['min_cost','min_irrigation'] for o in objectives):raise ValueError('Unsupported/duplicate objective')
        for i,s in enumerate(seasons):
            if not day(s['start'])<=day(s['end']):raise ValueError('Invalid season')
            if not day(data['parcel']['sowing_date'])<=day(s['start'])<=day(s['end'])<=day(data['parcel']['horizon_end']):raise ValueError('Season outside parcel horizon')
            if i and day(seasons[i-1]['end'])>=day(s['start']):raise ValueError('Overlapping seasons')
            parameter(s['irrigation_budget'],'mm')
        for name,c in crops.items():
            days=None if c.get('cycle') is None else parameter(c['cycle'],'day')
            if days is not None and (days<=0 or days!=int(days)):raise ValueError('Cycle must be positive integer days')
            if len(c['seasons'])!=len(seasons):raise ValueError('Missing crop-season evidence')
            for e,s in zip(c['seasons'],seasons):
                for k in ['calendar','climate','soil_nutrients']:
                    gate=e[k]
                    if type(gate.get('allowed')) is not bool or not gate.get('provenance') or gate.get('status') not in STATUSES:raise ValueError('Missing validated gate '+name+'/'+k)
                gates_ok=all(e[k]['allowed'] for k in ['calendar','climate','soil_nutrients'])
                fits=days is not None and days<=(day(s['end'])-day(s['start'])).days+1
                if days is None and gates_ok:raise ValueError('Cycle required where all gates allow '+name)
                # Requirement/cost may be absent only where the crop-season is already excluded.
                if (gates_ok and fits) or e.get('irrigation_required') is not None:
                    parameter(e['irrigation_required'],'mm')
                    if 'min_cost' in objectives:parameter(e['cost'],'USD/ha')
        for a in set(crops)|{previous}:
            for b in crops:
                r=rules[a][b]
                if type(r.get('allowed')) is not bool or not r.get('provenance') or r.get('status') not in STATUSES:raise ValueError('Missing explicit transition '+a+' -> '+b)
        # Explicit pair rules can encode verified history/family restrictions; never infer them.
        history=data['history_review']
        if type(history.get('allowed')) is not bool or not history.get('provenance') or history.get('status') not in STATUSES:raise ValueError('History constraints not reviewed')
    except (KeyError,ValueError,TypeError) as error:
        result['missing']=[str(error)];return result
    result['criteria']=objectives
    result['mandatory']=['cycle fits season','calendar','climate','soil_nutrients','irrigation budget','explicit pair transitions','history review']
    for sequence in product(sorted(crops),repeat=len(seasons)):
        reasons=[];cost=water=0.;prior=previous
        if not history['allowed']:reasons.append('history_review: forbidden')
        for i,(name,s) in enumerate(zip(sequence,seasons)):
            c=crops[name];e=c['seasons'][i]
            if not rules[prior][name]['allowed']:reasons.append(f'{i+1}: transition {prior} -> {name} forbidden')
            if c.get('cycle') is None:reasons.append(f'{i+1}: no documented cycle')
            elif c['cycle']['value']>(day(s['end'])-day(s['start'])).days+1:reasons.append(f'{i+1}: cycle exceeds season')
            for k in ['calendar','climate','soil_nutrients']:
                if not e[k]['allowed']:reasons.append(f'{i+1}: {name} {k} forbidden')
            if e.get('irrigation_required') is not None:  # absent only behind a forbidden gate; no metric invented
                w=e['irrigation_required']['value'];water+=w
                if w>s['irrigation_budget']['value']:reasons.append(f'{i+1}: irrigation budget exceeded')
                if 'min_cost' in objectives:cost+=e['cost']['value']
            prior=name
        if reasons:result['discarded'].append(dict(sequence=list(sequence),reasons=reasons))
        else:result['feasible'].append(dict(sequence=list(sequence),metrics={'min_irrigation':water,**({'min_cost':cost} if 'min_cost' in objectives else {})}))
    result['feasible'].sort(key=lambda r:tuple(r['metrics'][o] for o in objectives)+tuple(r['sequence']))
    result['status']='feasible' if result['feasible'] else 'infeasible'
    if objectives and result['feasible']:result['best']=result['feasible'][0]
    result['tie_break']='lexicographic crop names after ordered objectives; no agronomic superiority implied'
    result['assumptions']='Seasonal gates and water demand supplied externally; no inferred families, yields, nutrient effects or GAEZ interpretation'
    return result
