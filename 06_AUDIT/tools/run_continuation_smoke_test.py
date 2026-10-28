#!/usr/bin/env python3
from __future__ import annotations
import csv,json,statistics
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]; BASE=ROOT/'03_CURRENT_BASELINE_RESULTS'/'baseline_v18_extracted'; OUT=ROOT/'04_CONTINUATION'/'continuation_runs'/'smoke_test_budget_reserve_sensitivity'; OUT.mkdir(parents=True,exist_ok=True)
def rows(p):
    with open(p,newline='',encoding='utf-8') as f: return list(csv.DictReader(f))
def tr(x): return str(x).lower()=='true'
def fl(x):
    try: return float(x)
    except: return None
wm=rows(BASE/'world_method_summary_schedule_budget_wip_roi_utilization.csv'); out=[]; red=[]
for r in wm:
    if not tr(r['admissible']): continue
    full=fl(r['roi_pct_full_22p_budget_envelope']); conservative=None if full is None else full/1.10
    row={'seed':r['seed'],'method':r['method'],'baseline_p85':fl(r['p85_profit']),'roi_full_22p_budget_pct':full,'conservative_roi_if_full_budget_plus_10pct_reserve_pct':conservative,'avg_budget_util_pct':fl(r['avg_budget_util_pct'])}
    out.append(row)
    if r['method']=='sCPA_lite' and conservative is not None and conservative<15: red.append({'seed':r['seed'],'method':r['method'],'type':'scpa_conservative_roi_below_15pct','value':conservative})
with open(OUT/'conservative_reserve_roi_sensitivity.csv','w',newline='',encoding='utf-8') as f:
    w=csv.DictWriter(f,fieldnames=out[0].keys()); w.writeheader(); w.writerows(out)
with open(OUT/'smoke_test_red_flags.csv','w',newline='',encoding='utf-8') as f:
    w=csv.DictWriter(f,fieldnames=['seed','method','type','value']); w.writeheader(); w.writerows(red)
summary=[]
for m in sorted(set(r['method'] for r in out)):
    vals=[r['conservative_roi_if_full_budget_plus_10pct_reserve_pct'] for r in out if r['method']==m and r['conservative_roi_if_full_budget_plus_10pct_reserve_pct'] is not None]
    summary.append({'method':m,'median_conservative_roi_pct':statistics.median(vals) if vals else None,'rows':len(vals)})
report={'test_id':'smoke_test_budget_reserve_sensitivity','purpose':'New continuation smoke test: conservative reserve ROI sensitivity and red-flag generation without overwriting baseline. Analytical smoke test, not new method benchmark.','red_flags':len(red),'summary':summary}
with open(OUT/'smoke_test_method_summary.csv','w',newline='',encoding='utf-8') as f:
    w=csv.DictWriter(f,fieldnames=summary[0].keys()); w.writeheader(); w.writerows(summary)
(OUT/'smoke_test_summary.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps(report,indent=2))
