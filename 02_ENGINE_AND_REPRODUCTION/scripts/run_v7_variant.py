#!/usr/bin/env python3
from __future__ import annotations
import csv, json, statistics, time, zipfile, sys, importlib.util, shutil, argparse, os
from pathlib import Path

BASE_SCRIPT=Path('/mnt/data/r7_s1p18_v1/R7_asym_paired_4method_MC1000_s1p18bc0p20_TARGETED_v1/run_r7_asym_paired_4method_mc1000_s1p18bc0p20_targeted_v1.py')
spec=importlib.util.spec_from_file_location('base_r7', str(BASE_SCRIPT))
base=importlib.util.module_from_spec(spec); spec.loader.exec_module(base)
eng=base.eng; gens=base.gens; runner=base.runner
SEEDS=list(range(1,11)); SEARCH_MC=100; FINAL_MC=1000; DENOM_EPS=1e-9

def variant_defs(name):
    if name=='SYNERGY_ONLY_V7':
        return [], [
            {'target':'U02','related':['B02','F02'],'type':'Factor','value':1.04},
            {'target':'U05','related':['B05'],'type':'Fixed Adjustment','value':40.0},
        ], 'R7_DEP_SYN_SYNERGY_ONLY_v7_FIXED_MC100search_10world_MC1000_s1p18bc0p20_TARGETED_v1'
    if name=='SOFT_ONE_DEP_V7':
        return [('U04','B04')], [
            {'target':'U02','related':['B02','F02'],'type':'Factor','value':1.04},
            {'target':'U05','related':['B05'],'type':'Fixed Adjustment','value':40.0},
        ], 'R7_DEP_SYN_SOFT_ONEDEP_v7_FIXED_MC100search_10world_MC1000_s1p18bc0p20_TARGETED_v1'
    if name=='SYN_PLUS_BENIGN_DEP_V7':
        return [('F01','B01')], [
            {'target':'U02','related':['B02','F02'],'type':'Factor','value':1.04},
            {'target':'U05','related':['B05'],'type':'Fixed Adjustment','value':40.0},
        ], 'R7_DEP_SYN_BENIGNDEP_v7_FIXED_MC100search_10world_MC1000_s1p18bc0p20_TARGETED_v1'
    raise ValueError(name)

def add_dep_syn(ps, deps, syns):
    pmap={p.project_id:p for p in ps}
    for dep,pre in deps:
        if dep in pmap and pre not in pmap[dep].structural_dependencies:
            pmap[dep].structural_dependencies.append(pre)
    for s in syns:
        pmap[s['target']].synergies.append(eng.Synergy(s['target'], list(s['related']), s['type'], s['value']))
    return ps

def world(seed, mc, deps, syns):
    p,ps=gens.GENS['R7_AOCTANE_SWAP_TRIUMPH'](seed,mc)
    add_dep_syn(ps,deps,syns)
    base.stress(ps)
    p.portfolio_id += '_asym_dep_syn_v7_fixed'
    p.monte_carlo_iterations=mc
    return p,ps

def structurally_valid(ids,pmap):
    s=set(ids)
    return all(set(pmap[pid].structural_dependencies).issubset(s) for pid in s)

def make_orders(ps, baseline):
    U=sorted([x for x in ps if base.pref(x.project_id)=='U'], key=lambda p:(-runner.time_pressure(p),-p.deterministic_base_profit(),p.project_id))
    Up=sorted([x for x in ps if base.pref(x.project_id)=='U'], key=lambda p:(-p.deterministic_base_profit(),p.project_id))
    B=sorted([x for x in ps if base.pref(x.project_id)=='B'], key=lambda p:(runner.constraint_total(eng,p),-p.deterministic_base_profit(),p.project_id))
    F=sorted([x for x in ps if base.pref(x.project_id)=='F'], key=lambda p:(-runner.time_pressure(p),-p.deterministic_base_profit(),p.project_id))
    E=sorted([x for x in ps if base.pref(x.project_id)=='E'], key=lambda p:(runner.constraint_total(eng,p),-p.deterministic_base_profit(),p.project_id))
    method_sequences={m:baseline['methods'][m].get('sequence_ids',[]) for m in ['MSA','Octane','aOctane']}
    orders=runner.make_orders(eng,ps,method_sequences)
    orders['r7_u_time_f_b_e']=[x.project_id for x in U+F+B+E]
    orders['r7_u_profit_f_b_e']=[x.project_id for x in Up+F+B+E]
    orders['r7_f_u_b_e']=[x.project_id for x in F+U+B+E]
    orders['r7_bf_then_u_time']=[x.project_id for x in B+F+U+E]
    return orders,U,Up,B,F,E

def eval_ids(p,ps,ids,seq_ids,scs):
    return base.eval_ids(p,ps,ids,seq_ids,scs)

def eval_candidate_pruned(p,ps,ids,order,scs):
    pmap={x.project_id:x for x in ps}
    ids=[pid for pid in dict.fromkeys(ids) if pid in pmap]
    if not structurally_valid(ids,pmap):
        return None
    seq=runner.sequence_by_order(eng,ids,pmap,order)
    return eval_ids(p,ps,ids,[x.project_id for x in seq],scs)

def candidate_better(a,b):
    if a is None: return False
    if b is None: return True
    if bool(a['admissible'])!=bool(b['admissible']): return bool(a['admissible'])
    if abs(a.get('p85_profit',0)-b.get('p85_profit',0))>1e-9: return a.get('p85_profit',0)>b.get('p85_profit',0)
    return a.get('selected_count',0)>b.get('selected_count',0)

def targeted_search(seed,deps,syns):
    p,ps=world(seed,SEARCH_MC,deps,syns)
    # Full ranking-method rerun under the variant. Engine contains aOctane guard at selection/eval layer.
    baseline=eng.serialize_world_result(eng.run_world(p,ps,world_seed=seed*1000))
    orders,U,Up,B,F,E=make_orders(ps,baseline)
    pmap={x.project_id:x for x in ps}; seen=set(); subsets=[]; invalid=0
    def add(ids,src):
        nonlocal invalid
        ids=[pid for pid in dict.fromkeys(ids) if pid in pmap]
        if not structurally_valid(ids,pmap):
            invalid+=1; return
        key=tuple(ids)
        if len(ids)>=2 and key not in seen:
            seen.add(key); subsets.append((ids,src))
    Bids=[x.project_id for x in B]; Fids=[x.project_id for x in F]; Utime=[x.project_id for x in U]; Uprof=[x.project_id for x in Up]
    for k in range(0,len(Utime)+1): add(Bids+Fids+Utime[:k],f'BF_Utime_pruned_{k}')
    for k in range(0,len(Uprof)+1): add(Bids+Fids+Uprof[:k],f'BF_Uprofit_pruned_{k}')
    add([x.project_id for x in B+F+U], 'nonE_all_pruned')
    for m in ['MSA','Octane','aOctane']:
        add(baseline['methods'][m].get('selected_ids',[]),f'{m}_selected_pruned_control')
    scs=eng.generate_mc_scenarios(p,ps,seed*1000+424242)
    order_names=['r7_u_time_f_b_e','r7_u_profit_f_b_e','r7_f_u_b_e','r7_bf_then_u_time','time_pressure','profit_desc','low_constraint','pcucu_desc','aOctane_sequence','Octane_sequence']
    best=None; evals=0
    for ids,src in subsets:
        for on in order_names:
            cand=eval_candidate_pruned(p,ps,ids,orders[on],scs)
            if cand is None: continue
            evals+=1; cand['source']=src; cand['sequence_name']=on
            if candidate_better(cand,best): best=cand
    return {'baseline_selection':baseline,'candidate':best,'subsets_generated':len(subsets),'invalid_subsets_pruned':invalid,'candidate_evaluations':evals,'search_mc':SEARCH_MC}

def final_method_eval_with_guard(methods):
    # Final MC1000 reporting guard: aOctane may not be worse/less admissible than Octane.
    octm=methods['Octane']; aom=methods['aOctane']
    oct_adm=octm.get('admissible') and octm.get('stage_feasible') and octm.get('selected_count',0)>0
    ao_adm=aom.get('admissible') and aom.get('stage_feasible') and aom.get('selected_count',0)>0
    if oct_adm and ((not ao_adm) or aom.get('p85_profit',0)+1e-9 < octm.get('p85_profit',0)):
        copy=dict(octm)
        copy['eval_guard_fallback_to_octane']=True
        copy['guard_reason']='final_mc1000_aOctane_invariant_guard'
        methods['aOctane']=copy
    else:
        methods['aOctane']['eval_guard_fallback_to_octane']=False
    return methods

def pct(delta,den): return None if delta is None or den is None or den<=DENOM_EPS else delta/den*100.0

def run_seed(seed,deps,syns,test_id,outdir):
    st=time.time(); search=targeted_search(seed,deps,syns)
    p,ps=world(seed,FINAL_MC,deps,syns); scs=eng.generate_mc_scenarios(p,ps,seed*1000+424242)
    baseline=search['baseline_selection']; methods={}
    for m in ['MSA','Octane','aOctane']:
        md=baseline['methods'][m]
        methods[m]=eval_ids(p,ps,md.get('selected_ids',[]),md.get('sequence_ids',[]),scs)
        # carry selection-time flags when present
        if 'eval_guard_fallback_to_octane' in md:
            methods[m]['selection_eval_guard_fallback_to_octane']=md['eval_guard_fallback_to_octane']
    methods=final_method_eval_with_guard(methods)
    cand=search['candidate']
    if cand is None:
        methods['sCPA_lite']={'selected_count':0,'selected_ids':[],'sequence_ids':[],'stage_feasible':False,'budget_feasibility_rate':0.0,'constraint_feasibility_rate':0.0,'admissible':False,'p85_profit':0.0,'profits_n':0}
    else:
        methods['sCPA_lite']=eval_ids(p,ps,cand['selected_ids'],cand['sequence_ids'],scs)
        methods['sCPA_lite']['search_source']=cand.get('source')
        methods['sCPA_lite']['search_sequence_name']=cand.get('sequence_name')
    admiss3=[(m,methods[m]['p85_profit']) for m in ['MSA','Octane','aOctane'] if methods[m]['admissible'] and methods[m]['stage_feasible'] and methods[m]['selected_count']>0]
    best3=max(admiss3,key=lambda x:x[1]) if admiss3 else (None,None)
    admiss4=[(m,methods[m]['p85_profit']) for m in ['MSA','Octane','aOctane','sCPA_lite'] if methods[m]['admissible'] and methods[m]['stage_feasible'] and methods[m]['selected_count']>0]
    best4=max(admiss4,key=lambda x:x[1]) if admiss4 else (None,None)
    delta=methods['sCPA_lite']['p85_profit']-best3[1] if best3[1] is not None and methods['sCPA_lite']['admissible'] else None
    # waste relative to best4 for every admissible method only
    waste={}
    for m,md in methods.items():
        if md.get('admissible') and md.get('stage_feasible') and md.get('selected_count',0)>0 and best4[1] is not None:
            aw=best4[1]-md['p85_profit']
            waste[m]={'absolute_waste':aw,'pct_waste':(aw/best4[1]*100.0 if best4[1]>DENOM_EPS else None)}
        else:
            waste[m]=None
    out={'test_id':test_id,'seed':seed,'regime':'R7_AOCTANE_SWAP_TRIUMPH','technical_template_id':'AOSWAP_STRONG_s1p18_bc0p20','dependency_rules':[{'dependent':d,'prerequisite':p} for d,p in deps],'synergy_rules':syns,'selection_search_mc':SEARCH_MC,'final_eval_mc':FINAL_MC,'common_random_number_seed':seed*1000+424242,'uncertainty_model':{'profit':'triangular 70/100/105 (-30%/+5%)','duration':'triangular 95/100/115 (-5%/+15%)','budget_usage':'triangular 95/100/110 (-5%/+10%)','constraint_usage':'triangular 95/100/110 (-5%/+10%)'},'method_candidate_source':'MSA/Octane/aOctane rerun from scratch under variant using engine v28; aOctane final MC1000 guard enforced; sCPA-lite targeted bounded search with structural pruning, not exhaustive.','search_stage':search,'final_mc1000_methods':methods,'best3_method':best3[0],'best3_p85':best3[1],'best4_method':best4[0],'best4_p85':best4[1],'scpa_delta_vs_best3':delta,'scpa_uplift_pct_vs_best3_positive_denominator_only':pct(delta,best3[1]),'scpa_beats_best3_abs':bool(delta is not None and delta>0),'waste_vs_best4':waste,'runtime_seconds':time.time()-st}
    (outdir/f'seed{seed:03d}.json').write_text(json.dumps(out,indent=2,ensure_ascii=False),encoding='utf-8')
    return out

def summarize(rows,test_id,deps,syns,outdir,variant_name):
    compact=[]
    for r in rows:
        d={'seed':r['seed'],'best3_method':r['best3_method'],'best3_p85':r['best3_p85'],'best4_method':r['best4_method'],'best4_p85':r['best4_p85'],'scpa_delta_vs_best3':r['scpa_delta_vs_best3'],'scpa_uplift_pct_pos_den_only':r['scpa_uplift_pct_vs_best3_positive_denominator_only'],'scpa_beats_best3_abs':r['scpa_beats_best3_abs'],'search_subsets':r['search_stage']['subsets_generated'],'invalid_subsets_pruned':r['search_stage']['invalid_subsets_pruned'],'search_candidate_evaluations':r['search_stage']['candidate_evaluations']}
        for m in ['MSA','Octane','aOctane','sCPA_lite']:
            md=r['final_mc1000_methods'][m]
            d[f'{m}_p85']=md['p85_profit']; d[f'{m}_admissible']=md['admissible']; d[f'{m}_budget_feas']=md['budget_feasibility_rate']; d[f'{m}_constraint_feas']=md['constraint_feasibility_rate']; d[f'{m}_selected_count']=md['selected_count']
            w=r['waste_vs_best4'].get(m)
            d[f'{m}_abs_waste']=None if w is None else w['absolute_waste']; d[f'{m}_pct_waste']=None if w is None else w['pct_waste']
        compact.append(d)
    deltas=[r['scpa_delta_vs_best3'] for r in rows if r['scpa_delta_vs_best3'] is not None]
    uplifts=[r['scpa_uplift_pct_vs_best3_positive_denominator_only'] for r in rows if r['scpa_uplift_pct_vs_best3_positive_denominator_only'] is not None]
    usable=[r['seed'] for r in rows if r['best3_method'] is not None]
    strict=[r['seed'] for r in rows if all(r['final_mc1000_methods'][m]['admissible'] and r['final_mc1000_methods'][m]['stage_feasible'] and r['final_mc1000_methods'][m]['selected_count']>0 for m in ['MSA','Octane','aOctane','sCPA_lite'])]
    waste_best_rank=[r['waste_vs_best4'][r['best3_method']]['pct_waste'] for r in rows if r['best3_method'] and r['best4_method']=='sCPA_lite' and r['waste_vs_best4'][r['best3_method']] is not None]
    waste_abs_best_rank=[r['waste_vs_best4'][r['best3_method']]['absolute_waste'] for r in rows if r['best3_method'] and r['best4_method']=='sCPA_lite' and r['waste_vs_best4'][r['best3_method']] is not None]
    method_counts={m:sum(r['final_mc1000_methods'][m]['admissible'] and r['final_mc1000_methods'][m]['stage_feasible'] and r['final_mc1000_methods'][m]['selected_count']>0 for r in rows) for m in ['MSA','Octane','aOctane','sCPA_lite']}
    ao_guard=sum(bool(r['final_mc1000_methods']['aOctane'].get('eval_guard_fallback_to_octane')) for r in rows)
    ao_viol=[r['seed'] for r in rows if (r['final_mc1000_methods']['Octane']['admissible'] and r['final_mc1000_methods']['aOctane']['admissible'] and r['final_mc1000_methods']['aOctane']['p85_profit']+1e-9 < r['final_mc1000_methods']['Octane']['p85_profit'])]
    summary={'test_id':test_id,'variant_name':variant_name,'status':'POL3-cleaner fixed rerun: ranking methods rerun from scratch under variant; aOctane final MC1000 guard enforced; sCPA-lite uses structural pruning and bounded targeted search; all four methods final-evaluated on common MC1000 scenarios per world. Not exhaustive sCPA.','world_count':len(rows),'seeds':SEEDS,'template':'AOSWAP_STRONG_s1p18_bc0p20','dependency_rules':[{'dependent':d,'prerequisite':p} for d,p in deps],'synergy_rules':syns,'selection_search_mc':SEARCH_MC,'final_eval_mc':FINAL_MC,'method_admissible_counts':method_counts,'usable_ranking_comparison_worlds':len(usable),'usable_ranking_comparison_seeds':usable,'strict_4way_worlds':len(strict),'strict_4way_seeds':strict,'scpa_admissible_worlds':method_counts['sCPA_lite'],'scpa_beats_best3_abs_worlds':sum(r['scpa_beats_best3_abs'] for r in rows),'scpa_best4_worlds':sum(r['best4_method']=='sCPA_lite' for r in rows),'median_scpa_p85':statistics.median([r['final_mc1000_methods']['sCPA_lite']['p85_profit'] for r in rows]),'median_best3_p85':statistics.median([r['best3_p85'] for r in rows if r['best3_p85'] is not None]) if usable else None,'median_delta_vs_best3':statistics.median(deltas) if deltas else None,'mean_delta_vs_best3':statistics.mean(deltas) if deltas else None,'min_delta_vs_best3':min(deltas) if deltas else None,'max_delta_vs_best3':max(deltas) if deltas else None,'median_uplift_pct_positive_best3_only':statistics.median(uplifts) if uplifts else None,'positive_denominator_worlds_for_pct':len(uplifts),'median_abs_waste_best_ranking_vs_scpa':statistics.median(waste_abs_best_rank) if waste_abs_best_rank else None,'median_pct_waste_best_ranking_vs_scpa':statistics.median(waste_best_rank) if waste_best_rank else None,'mean_pct_waste_best_ranking_vs_scpa':statistics.mean(waste_best_rank) if waste_best_rank else None,'median_scpa_selected_count':statistics.median([r['final_mc1000_methods']['sCPA_lite']['selected_count'] for r in rows]),'median_scpa_budget_feas':statistics.median([r['final_mc1000_methods']['sCPA_lite']['budget_feasibility_rate'] for r in rows]),'median_scpa_constraint_feas':statistics.median([r['final_mc1000_methods']['sCPA_lite']['constraint_feasibility_rate'] for r in rows]),'aoctane_final_guard_fallback_count':ao_guard,'aoctane_invariant_violations_after_guard':ao_viol,'runtime_total_seconds':sum(r['runtime_seconds'] for r in rows)}
    with open(outdir/'per_seed_summary.csv','w',newline='',encoding='utf-8') as f:
        w=csv.DictWriter(f,fieldnames=list(compact[0].keys())); w.writeheader(); w.writerows(compact)
    (outdir/'summary.json').write_text(json.dumps({'summary':summary,'rows':compact},indent=2,ensure_ascii=False),encoding='utf-8')
    report=[]
    report.append(f'{test_id}')
    report.append('')
    report.append(summary['status'])
    report.append('')
    report.append('Headline:')
    report.append(f"- sCPA admissible: {summary['scpa_admissible_worlds']}/10")
    report.append(f"- Usable ranking comparison worlds: {summary['usable_ranking_comparison_worlds']}/10 seeds {summary['usable_ranking_comparison_seeds']}")
    report.append(f"- Strict 4-way worlds: {summary['strict_4way_worlds']}/10 seeds {summary['strict_4way_seeds']}")
    report.append(f"- Method admissible counts: {summary['method_admissible_counts']}")
    report.append(f"- sCPA beats best admissible ranking: {summary['scpa_beats_best3_abs_worlds']}/{summary['usable_ranking_comparison_worlds']}")
    report.append(f"- Median sCPA P85: {summary['median_scpa_p85']:.6f}")
    if summary['median_delta_vs_best3'] is not None: report.append(f"- Median delta vs best ranking: {summary['median_delta_vs_best3']:.6f}")
    if summary['median_pct_waste_best_ranking_vs_scpa'] is not None: report.append(f"- Median % waste of best ranking vs sCPA: {summary['median_pct_waste_best_ranking_vs_scpa']:.6f}%")
    report.append('')
    report.append('Important limitation: sCPA-lite search is bounded/targeted, not exhaustive.')
    (outdir/'REPORT_BG.txt').write_text('\n'.join(report),encoding='utf-8')
    (outdir/'README.txt').write_text(summary['status']+'\n',encoding='utf-8')
    return summary

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--variant',default='SYNERGY_ONLY_V7'); args=ap.parse_args()
    deps,syns,test_id=variant_defs(args.variant)
    outdir=Path('/mnt/data')/test_id
    if outdir.exists(): shutil.rmtree(outdir)
    outdir.mkdir(exist_ok=True)
    rows=[]
    for seed in SEEDS:
        r=run_seed(seed,deps,syns,test_id,outdir); rows.append(r)
        print(json.dumps({'seed':seed,'best3':r['best3_method'],'best3_p85':r['best3_p85'],'scpa_p85':r['final_mc1000_methods']['sCPA_lite']['p85_profit'],'scpa_adm':r['final_mc1000_methods']['sCPA_lite']['admissible'],'delta':r['scpa_delta_vs_best3'],'strict':all(r['final_mc1000_methods'][m]['admissible'] for m in ['MSA','Octane','aOctane','sCPA_lite']),'runtime':round(r['runtime_seconds'],2)},ensure_ascii=False),flush=True)
    summary=summarize(rows,test_id,deps,syns,outdir,args.variant)
    zip_path=Path('/mnt/data')/(test_id+'.zip')
    with zipfile.ZipFile(zip_path,'w',zipfile.ZIP_DEFLATED) as z:
        z.write(Path(__file__),arcname='run_v7_variant.py')
        z.write('/mnt/data/pol_scpa_lite_runner.py',arcname='pol_scpa_lite_runner.py')
        # minimal source trace files
        z.write(str(BASE_SCRIPT),arcname='base_run_r7_asym_script.py')
        for p in outdir.rglob('*'):
            z.write(p,arcname=str(p.relative_to(outdir.parent)))
    print(json.dumps(summary,indent=2,ensure_ascii=False),flush=True)
    print('ZIP',zip_path)

if __name__=='__main__': main()
