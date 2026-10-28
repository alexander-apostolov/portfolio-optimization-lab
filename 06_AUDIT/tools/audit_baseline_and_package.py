#!/usr/bin/env python3
from __future__ import annotations
import csv,json,statistics
from pathlib import Path
from collections import defaultdict
ROOT=Path(__file__).resolve().parents[2]; BASE=ROOT/'03_CURRENT_BASELINE_RESULTS'/'baseline_v18_extracted'; AUD=ROOT/'06_AUDIT'/'results'; AUD.mkdir(parents=True,exist_ok=True)
METHODS=['MSA','Octane','aOctane','sCPA_lite']; EXPECTED={'MSA':9,'Octane':7,'aOctane':10,'sCPA_lite':10,'usable_ranking_comparison_worlds':10,'strict_4way_worlds':6,'scpa_beats_best3_abs_worlds':10,'scpa_best4_worlds':10}
EXPMED={'MSA':{'p85_profit':-97.3574572669764,'roi_pct_used_budget':-0.6181166837896088,'avg_budget_util_pct':77.47264217647205},'Octane':{'p85_profit':937.6970837947556,'roi_pct_used_budget':5.790455406467864,'avg_budget_util_pct':77.81814350068173},'aOctane':{'p85_profit':1128.1885054308898,'roi_pct_used_budget':8.416901488679903,'avg_budget_util_pct':77.35961651832471},'sCPA_lite':{'p85_profit':4162.970683125401,'roi_pct_used_budget':28.234744861417923,'avg_budget_util_pct':80.24616026573548}}
issues=[]; checks=[]
def add(c,ok,d=''):
    checks.append({'check':c,'status':'PASS' if ok else 'FAIL','detail':d})
    if not ok: issues.append(f'{c}: {d}')
def rows(p):
    with open(p,newline='',encoding='utf-8') as f: return list(csv.DictReader(f))
def tr(x): return str(x).lower()=='true'
def fl(x):
    try: return float(x)
    except: return None
for rel in ['00_START_HERE/README_START_HERE.md','01_METHOD_GUIDE/Four_Methods_Explained.md','01_METHOD_GUIDE/Portfolio_Waste_Metrics.md','03_CURRENT_BASELINE_RESULTS/baseline_v18_extracted/summary.json','LICENSE_AND_ATTRIBUTION.md']:
    add('required:'+rel,(ROOT/rel).exists(),'missing')
summary=json.loads((BASE/'summary.json').read_text(encoding='utf-8'))['summary']
for m in METHODS: add('admissible_count_'+m,summary['method_admissible_counts'].get(m)==EXPECTED[m],str(summary['method_admissible_counts'].get(m)))
for k in ['usable_ranking_comparison_worlds','strict_4way_worlds','scpa_beats_best3_abs_worlds','scpa_best4_worlds']: add(k,summary.get(k)==EXPECTED[k],str(summary.get(k)))
wm=rows(BASE/'world_method_summary_schedule_budget_wip_roi_utilization.csv'); period=rows(BASE/'period_budget_constraint_wip_by_world_method_det.csv'); sel=rows(BASE/'selected_projects_by_world_method.csv'); seq=rows(BASE/'sequence_by_world_method.csv'); per=rows(BASE/'per_seed_summary.csv')
for m in METHODS:
    rs=[r for r in wm if r['method']==m and tr(r['admissible'])]
    add('raw_count_'+m,len(rs)==EXPECTED[m],str(len(rs)))
    for fld,exp in EXPMED[m].items():
        vals=[fl(r[fld]) for r in rs if fl(r.get(fld)) is not None]
        med=statistics.median(vals) if vals else None
        add('median_'+m+'_'+fld, med is not None and abs(med-exp)<=1e-6, f'{med} vs {exp}')
add('period_budget_violations', all(tr(r['budget_ok']) for r in period),'')
add('period_constraint_violations', all(tr(r['constraint_ok']) for r in period),'')
smap=defaultdict(list); qmap=defaultdict(list)
for r in sel: smap[(r['seed'],r['method'])].append(r['project_id'])
for r in seq: qmap[(r['seed'],r['method'])].append(r['project_id'])
add('duplicate_selected_ids', all(len(v)==len(set(v)) for v in smap.values()),'')
add('selected_sequence_same_set', all(set(v)==set(qmap.get(k,[])) for k,v in smap.items()),'')
by={(r['seed'],r['method']):r for r in wm}; bad=[]
for seed in sorted(set(r['seed'] for r in wm)):
    o=by.get((seed,'Octane')); a=by.get((seed,'aOctane'))
    if o and a and tr(o['admissible']) and tr(a['admissible']) and fl(a['p85_profit'])+1e-9<fl(o['p85_profit']): bad.append(seed)
add('aOctane_not_below_Octane',len(bad)==0,str(bad))
waste=[]
for r in per:
    vals={m:fl(r.get(m+'_p85')) for m in METHODS if tr(r.get(m+'_admissible')) and fl(r.get(m+'_p85')) is not None}
    if vals:
        best_m=max(vals,key=vals.get); best=vals[best_m]
        for m in METHODS:
            p=fl(r.get(m+'_p85')); adm=tr(r.get(m+'_admissible'))
            waste.append({'seed':r['seed'],'method':m,'admissible':adm,'best_method':best_m,'best_profit':best,'absolute_waste':'' if (not adm or p is None) else best-p,'percent_waste':'' if (not adm or p is None or best<=0) else (best-p)/best*100})
add('best_overall_is_sCPA_lite_all_worlds', all(w['best_method']=='sCPA_lite' for w in waste if w['method']=='sCPA_lite'), '')
with open(AUD/'waste_recomputed_from_raw.csv','w',newline='',encoding='utf-8') as f:
    w=csv.DictWriter(f,fieldnames=waste[0].keys()); w.writeheader(); w.writerows(waste)
red=[]
for r in wm:
    if tr(r.get('near_all_selected')): red.append({'type':'near_all_selected',**r})
    if (fl(r.get('selected_count')) or 0)>=24 and (fl(r.get('portfolio_duration_periods')) or 999)<=8: red.append({'type':'many_projects_short_duration',**r})
    if (fl(r.get('roi_pct_used_budget')) or 0)>100: red.append({'type':'roi_above_100pct',**r})
add('suspicious_red_flags',len(red)==0,str(len(red)))
with open(AUD/'suspicious_signal_recomputed.csv','w',newline='',encoding='utf-8') as f:
    fields=['type']+list(wm[0].keys()); w=csv.DictWriter(f,fieldnames=fields); w.writeheader(); w.writerows(red)
smoke=ROOT/'04_CONTINUATION'/'continuation_runs'/'smoke_test_budget_reserve_sensitivity'/'smoke_test_summary.json'
add('continuation_smoke_test_output_present',smoke.exists(),'missing')
status='READY FOR HANDOFF' if not issues else 'NOT READY'
report={'status':status,'critical_issues':issues,'checks':checks}
(AUD/'audit_status.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
with open(AUD/'audit_checklist.csv','w',newline='',encoding='utf-8') as f:
    w=csv.DictWriter(f,fieldnames=['check','status','detail']); w.writeheader(); w.writerows(checks)
print(json.dumps({'status':status,'critical_issues':len(issues)},indent=2))
if issues: raise SystemExit(1)
