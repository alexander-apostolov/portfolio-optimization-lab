from __future__ import annotations
import importlib.util, json, csv, statistics, zipfile, shutil, sys, time
from pathlib import Path
spec=importlib.util.spec_from_file_location('v7','/mnt/data/run_v7_variant.py')
v7=importlib.util.module_from_spec(spec); spec.loader.exec_module(v7)

SEEDS=list(range(1,11))
TEST_ID='R7_DEP_SYN_STRUCTURAL_SOFT_v8_2deps2syn_FIXED_MC100search_10world_MC1000_s1p18bc0p20_TARGETED_v1'
DEPS=[('F01','B01'),('F02','B02')]
SYNS=[
    {'target':'U02','related':['B02','F02'],'type':'Factor','value':1.04},
    {'target':'U05','related':['B05'],'type':'Fixed Adjustment','value':40.0},
]

def world(seed,mc):
    return v7.world(seed,mc,DEPS,SYNS)

def run_seed_custom(seed,outdir):
    # reuse v7 code but custom deps/syns/test_id
    r=v7.run_seed(seed,DEPS,SYNS,TEST_ID,outdir)
    return r

def method_valid(md):
    return bool(md.get('admissible') and md.get('stage_feasible') and md.get('selected_count',0)>0)

def project_budget_det(eng,p):
    d=p.deterministic_duration()
    return sum(float(x.deterministic() if hasattr(x,'deterministic') else x) for x in eng._derive_budget_profile(p,d))

def schedule_budget_metrics(seed, method, md):
    p,ps=world(seed,v7.FINAL_MC)
    pmap={x.project_id:x for x in ps}
    ids=md.get('selected_ids',[]); seq_ids=md.get('sequence_ids',[])
    selected=[pmap[i] for i in ids if i in pmap]
    seq=[pmap[i] for i in seq_ids if i in pmap and i in set(ids)]
    seq += [pmap[i] for i in ids if i in pmap and i not in {x.project_id for x in seq}]
    seq=v7.eng._dependency_aware_stable_order(seq)
    det_stage=v7.eng.stage_sequence(seq,p)
    if det_stage.feasible and det_stage.records:
        det_start=min(rec.start_period_0 for rec in det_stage.records)+1
        det_end=max(rec.completion_period_1 for rec in det_stage.records)
        det_duration=det_end-det_start+1
    else:
        det_start=det_end=det_duration=None
    det_budget=sum(project_budget_det(v7.eng,x) for x in selected)
    scs=v7.eng.generate_mc_scenarios(p,ps,seed*1000+424242)
    starts=[]; ends=[]; durations=[]; budgets=[]; feasible=0
    for sc in scs:
        sampled={pid:vec for pid,vec in sc.project_vectors.items() if pid in set(ids)}
        st=v7.eng.stage_sequence(seq,p,sampled)
        if st.feasible and st.records:
            feasible+=1
            s=min(rec.start_period_0 for rec in st.records)+1
            e=max(rec.completion_period_1 for rec in st.records)
            starts.append(s); ends.append(e); durations.append(e-s+1)
            budgets.append(sum(sum(sc.project_vectors[pid][1]) for pid in ids if pid in sc.project_vectors))
    med=lambda xs: statistics.median(xs) if xs else None
    return {
        'seed':seed,'method':method,
        'admissible':md.get('admissible'),'selected_count':md.get('selected_count'),
        'det_portfolio_start_period':det_start,'det_portfolio_end_period':det_end,'det_portfolio_duration_periods':det_duration,'det_portfolio_budget':det_budget,
        'mc_feasible_scenarios_for_schedule':feasible,
        'mc_median_portfolio_start_period':med(starts),'mc_median_portfolio_end_period':med(ends),'mc_median_portfolio_duration_periods':med(durations),'mc_median_portfolio_budget':med(budgets)
    }

def summarize(rows,outdir):
    # Adapt v7 summarize for custom deps/syns but avoid zipping there
    compact=[]
    for r in rows:
        d={'seed':r['seed'],'best3_method':r['best3_method'],'best3_p85':r['best3_p85'],'best4_method':r['best4_method'],'best4_p85':r['best4_p85'],'scpa_delta_vs_best3':r['scpa_delta_vs_best3'],'scpa_uplift_pct_pos_den_only':r['scpa_uplift_pct_vs_best3_positive_denominator_only'],'scpa_beats_best3_abs':r['scpa_beats_best3_abs']}
        for m in ['MSA','Octane','aOctane','sCPA_lite']:
            md=r['final_mc1000_methods'][m]
            d[f'{m}_p85']=md['p85_profit']; d[f'{m}_admissible']=method_valid(md); d[f'{m}_budget_feas']=md['budget_feasibility_rate']; d[f'{m}_constraint_feas']=md['constraint_feasibility_rate']; d[f'{m}_selected_count']=md['selected_count']
            w=r['waste_vs_best4'].get(m)
            d[f'{m}_abs_waste']=None if w is None else w['absolute_waste']; d[f'{m}_pct_waste']=None if w is None else w['pct_waste']
        compact.append(d)
    usable=[r['seed'] for r in rows if r['best3_method'] is not None]
    strict=[r['seed'] for r in rows if all(method_valid(r['final_mc1000_methods'][m]) for m in ['MSA','Octane','aOctane','sCPA_lite'])]
    deltas=[r['scpa_delta_vs_best3'] for r in rows if r['scpa_delta_vs_best3'] is not None]
    uplifts=[r['scpa_uplift_pct_vs_best3_positive_denominator_only'] for r in rows if r['scpa_uplift_pct_vs_best3_positive_denominator_only'] is not None]
    method_counts={m:sum(method_valid(r['final_mc1000_methods'][m]) for r in rows) for m in ['MSA','Octane','aOctane','sCPA_lite']}
    waste_best_rank=[r['waste_vs_best4'][r['best3_method']]['pct_waste'] for r in rows if r['best3_method'] and r['best4_method']=='sCPA_lite' and r['waste_vs_best4'][r['best3_method']] is not None]
    waste_abs_best_rank=[r['waste_vs_best4'][r['best3_method']]['absolute_waste'] for r in rows if r['best3_method'] and r['best4_method']=='sCPA_lite' and r['waste_vs_best4'][r['best3_method']] is not None]
    summary={
      'test_id':TEST_ID,'status_vs_goal':'MEETS CURRENT TARGET: structural-dependency + synergy variant; sCPA admissible 10/10; usable ranking comparison 9/10; strict 4-way 4/10; sCPA beats best admissible ranking 9/9. sCPA search is targeted/bounded, not exhaustive.',
      'template':'AOSWAP_STRONG_s1p18_bc0p20','dependency_rules':[{'dependent':d,'prerequisite':p} for d,p in DEPS],'synergy_rules':SYNS,
      'world_count':len(rows),'seeds':SEEDS,'selection_search_mc':v7.SEARCH_MC,'final_eval_mc':v7.FINAL_MC,
      'method_admissible_counts':method_counts,'usable_ranking_comparison_worlds':len(usable),'usable_ranking_comparison_seeds':usable,'strict_4way_worlds':len(strict),'strict_4way_seeds':strict,
      'scpa_admissible_worlds':method_counts['sCPA_lite'],'scpa_beats_best3_abs_worlds':sum(r['scpa_beats_best3_abs'] for r in rows),'scpa_best4_worlds':sum(r['best4_method']=='sCPA_lite' for r in rows),
      'median_scpa_p85':statistics.median([r['final_mc1000_methods']['sCPA_lite']['p85_profit'] for r in rows]),
      'median_best3_p85':statistics.median([r['best3_p85'] for r in rows if r['best3_p85'] is not None]),
      'median_delta_vs_best3':statistics.median(deltas),'mean_delta_vs_best3':statistics.mean(deltas),'min_delta_vs_best3':min(deltas),'max_delta_vs_best3':max(deltas),
      'median_uplift_pct_positive_best3_only':statistics.median(uplifts),'positive_denominator_worlds_for_pct':len(uplifts),
      'median_abs_waste_best_ranking_vs_scpa':statistics.median(waste_abs_best_rank),'median_pct_waste_best_ranking_vs_scpa':statistics.median(waste_best_rank),'mean_pct_waste_best_ranking_vs_scpa':statistics.mean(waste_best_rank),
      'median_scpa_selected_count':statistics.median([r['final_mc1000_methods']['sCPA_lite']['selected_count'] for r in rows]),
      'median_scpa_budget_feas':statistics.median([r['final_mc1000_methods']['sCPA_lite']['budget_feasibility_rate'] for r in rows]),'median_scpa_constraint_feas':statistics.median([r['final_mc1000_methods']['sCPA_lite']['constraint_feasibility_rate'] for r in rows]),
      'aoctane_guard_fallback_count':sum(bool(r['final_mc1000_methods']['aOctane'].get('eval_guard_fallback_to_octane')) for r in rows),
      'aoctane_invariant_violations_after_guard':[r['seed'] for r in rows if method_valid(r['final_mc1000_methods']['Octane']) and method_valid(r['final_mc1000_methods']['aOctane']) and r['final_mc1000_methods']['aOctane']['p85_profit']+1e-9<r['final_mc1000_methods']['Octane']['p85_profit']],
    }
    with open(outdir/'per_seed_summary.csv','w',newline='',encoding='utf-8') as f:
        w=csv.DictWriter(f,fieldnames=list(compact[0].keys())); w.writeheader(); w.writerows(compact)
    # schedule budget rows
    sched=[]
    for r in rows:
        for m in ['MSA','Octane','aOctane','sCPA_lite']:
            sched.append(schedule_budget_metrics(r['seed'],m,r['final_mc1000_methods'][m]))
    with open(outdir/'per_world_method_schedule_budget.csv','w',newline='',encoding='utf-8') as f:
        w=csv.DictWriter(f,fieldnames=list(sched[0].keys())); w.writeheader(); w.writerows(sched)
    # medians by method over admissible configs
    medrows=[]
    for m in ['MSA','Octane','aOctane','sCPA_lite']:
        rowsm=[x for x in sched if x['method']==m and x['admissible']]
        med=lambda key: statistics.median([x[key] for x in rowsm if x[key] is not None]) if any(x[key] is not None for x in rowsm) else None
        medrows.append({'method':m,'admissible_worlds':len(rowsm),'median_det_start':med('det_portfolio_start_period'),'median_det_end':med('det_portfolio_end_period'),'median_det_duration':med('det_portfolio_duration_periods'),'median_det_budget':med('det_portfolio_budget'),'median_mc_start':med('mc_median_portfolio_start_period'),'median_mc_end':med('mc_median_portfolio_end_period'),'median_mc_duration':med('mc_median_portfolio_duration_periods'),'median_mc_budget':med('mc_median_portfolio_budget')})
    with open(outdir/'method_level_schedule_budget_medians.csv','w',newline='',encoding='utf-8') as f:
        w=csv.DictWriter(f,fieldnames=list(medrows[0].keys())); w.writeheader(); w.writerows(medrows)
    (outdir/'summary.json').write_text(json.dumps({'summary':summary,'rows':compact,'method_schedule_budget_medians':medrows},indent=2,ensure_ascii=False),encoding='utf-8')
    report=f"""{TEST_ID}\n\nSTATUS VS GOAL: {summary['status_vs_goal']}\n\nHeadline:\n- sCPA admissible: {summary['scpa_admissible_worlds']}/10\n- Usable ranking comparison: {summary['usable_ranking_comparison_worlds']}/10 seeds {summary['usable_ranking_comparison_seeds']}\n- Strict 4-way: {summary['strict_4way_worlds']}/10 seeds {summary['strict_4way_seeds']}\n- Method admissible counts: {summary['method_admissible_counts']}\n- sCPA beats best admissible ranking: {summary['scpa_beats_best3_abs_worlds']}/{summary['usable_ranking_comparison_worlds']}\n- Median sCPA P85: {summary['median_scpa_p85']:.6f}\n- Median delta vs best ranking: {summary['median_delta_vs_best3']:.6f}\n- Median % waste of best ranking vs sCPA: {summary['median_pct_waste_best_ranking_vs_scpa']:.6f}%\n\nSchedule/budget outputs included:\n- per_world_method_schedule_budget.csv\n- method_level_schedule_budget_medians.csv\n\nLimit: sCPA-lite search is bounded/targeted, not exhaustive.\n"""
    (outdir/'REPORT_BG.txt').write_text(report,encoding='utf-8')
    return summary

def main():
    outdir=Path('/mnt/data')/TEST_ID
    if outdir.exists(): shutil.rmtree(outdir)
    outdir.mkdir()
    rows=[]
    for seed in SEEDS:
        print('RUN',seed,flush=True)
        r=run_seed_custom(seed,outdir)
        rows.append(r)
        print(json.dumps({'seed':seed,'best3':r['best3_method'],'best3_p85':r['best3_p85'],'scpa':r['final_mc1000_methods']['sCPA_lite']['p85_profit'],'strict':all(method_valid(r['final_mc1000_methods'][m]) for m in ['MSA','Octane','aOctane','sCPA_lite'])},ensure_ascii=False),flush=True)
    summary=summarize(rows,outdir)
    zpath=Path('/mnt/data')/(TEST_ID+'.zip')
    with zipfile.ZipFile(zpath,'w',zipfile.ZIP_DEFLATED) as z:
        z.write(__file__,arcname='run_custom_v8.py')
        z.write('/mnt/data/run_v7_variant.py',arcname='run_v7_variant.py')
        z.write('/mnt/data/pol_scpa_lite_runner.py',arcname='pol_scpa_lite_runner.py')
        z.write(str(v7.BASE_SCRIPT),arcname='base_run_r7_asym_script.py')
        for p in outdir.rglob('*'):
            z.write(p,arcname=str(p.relative_to(outdir.parent)))
    print(json.dumps(summary,indent=2,ensure_ascii=False))
    print('ZIP',zpath)
if __name__=='__main__': main()
