from __future__ import annotations
import json,csv,statistics,shutil,zipfile,importlib.util
from pathlib import Path
spec=importlib.util.spec_from_file_location('v8','/mnt/data/run_custom_v8.py')
v8=importlib.util.module_from_spec(spec); spec.loader.exec_module(v8)
eng=v8.v7.eng
SRC=Path('/mnt/data/R7_STRUCTURAL_SOFT_V16C_FOCUSED_DETLOCAL_AOCTANE_SEQUENCE_ONLY_MC1000_v1')
TEST_ID='R7_STRUCTURAL_SOFT_V17C_FULL_U_LOCAL_AOCTANE_SEQUENCE_ONLY_MC1000_v1'
OUT=Path('/mnt/data')/TEST_ID; ZIP=Path(str(OUT)+'.zip')
SEEDS=range(1,11); METHODS=['MSA','Octane','aOctane','sCPA_lite']; RANKING=['MSA','Octane','aOctane']
MC=1000; BUD_MULT=20.0; CAP_MULT=1.9; EPS=1e-9; NEAR_ALL=34
MAX_ITERS=8; MAX_MOVE=999
if OUT.exists(): shutil.rmtree(OUT)
OUT.mkdir()

def write_csv(path,rows):
    if not rows: Path(path).write_text('',encoding='utf-8'); return
    fields=[]
    for r in rows:
        for k in r:
            if k not in fields: fields.append(k)
    with open(path,'w',newline='',encoding='utf-8') as f:
        w=csv.DictWriter(f,fieldnames=fields); w.writeheader(); w.writerows(rows)

def det(x): return float(x.deterministic() if hasattr(x,'deterministic') else x)
def scale(x,m):
    if hasattr(x,'optimistic') and hasattr(x,'most_likely') and hasattr(x,'pessimistic'):
        return eng.ThreePoint(x.optimistic*m,x.most_likely*m,x.pessimistic*m)
    return x*m

def world(seed):
    p,ps=v8.world(seed,MC); p.monte_carlo_iterations=MC; p.budget_restriction_profile=[float(x)*CAP_MULT for x in p.budget_restriction_profile]
    for pr in ps:
        pr.budget_usage_profile=[scale(x,BUD_MULT) for x in pr.budget_usage_profile]
        if getattr(pr,'total_project_budget',None) is not None: pr.total_project_budget=scale(pr.total_project_budget,BUD_MULT)
    return p,ps,{x.project_id:x for x in ps}

def profiles(p):
    d=p.deterministic_duration(); return d,[det(x) for x in eng._derive_budget_profile(p,d)],[det(x) for x in eng._normalize_profile(p.constraint_usage_profile,d)]
def pb(p): return sum(profiles(p)[1])
def pc(p): return sum(profiles(p)[2])

def structural_prune(ids,pmap):
    ids=[i for i in ids if i in pmap]; s=set(ids); changed=True
    while changed:
        changed=False
        for pid in list(s):
            if not set(pmap[pid].structural_dependencies).issubset(s): s.remove(pid); changed=True
    return [i for i in ids if i in s]

def make_seq(pmap,ids,order):
    ids=structural_prune(list(dict.fromkeys(ids)),pmap); s=set(ids)
    seq=[pmap[i] for i in order if i in pmap and i in s]
    seen={p.project_id for p in seq}; seq += [pmap[i] for i in ids if i not in seen]
    return eng._dependency_aware_stable_order(seq)

def subset_scenarios(scs,ids):
    ids=set(ids)
    return [eng.MonteCarloScenario(project_vectors={pid:sc.project_vectors[pid] for pid in ids if pid in sc.project_vectors},linear_cot_deltas={pid:sc.linear_cot_deltas[pid] for pid in ids if pid in sc.linear_cot_deltas},piecewise_cot_values={pid:sc.piecewise_cot_values[pid] for pid in ids if pid in sc.piecewise_cot_values},synergy_values={(pid,i):v for (pid,i),v in sc.synergy_values.items() if pid in ids}) for sc in scs]

def eval_md(p,ps,scs,ids,seq_ids):
    pmap={x.project_id:x for x in ps}; ids=structural_prune(ids,pmap); seq=make_seq(pmap,ids,seq_ids); st=eng.stage_sequence(seq,p)
    if not st.feasible: return {'selected_ids':ids,'sequence_ids':[x.project_id for x in seq],'selected_count':len(ids),'stage_feasible':False,'budget_feasibility_rate':0,'constraint_feasibility_rate':0,'admissible':False,'p85_profit':None}
    br,cr,adm,p85,_=eng.evaluate_stochastic_from_scenarios(p,[pmap[i] for i in ids],seq,subset_scenarios(scs,ids),optimistic_prefilter=False)
    return {'selected_ids':ids,'sequence_ids':[x.project_id for x in seq],'selected_count':len(ids),'stage_feasible':True,'budget_feasibility_rate':br,'constraint_feasibility_rate':cr,'admissible':bool(adm),'p85_profit':p85}

def valid(md): return bool(md.get('stage_feasible') and md.get('admissible') and md.get('p85_profit') is not None)
def seq_key(seq): return tuple(p.project_id for p in seq)
def det_profit(p,selected,seq):
    st=eng.stage_sequence(seq,p)
    if not st.feasible: return None
    return eng._profit_with_cost_and_synergy(selected,st)

def focused_det_candidates(current):
    """V17C: stronger but still local/fixed-set sequence-only aOctane.
    It extends V16C from bounded U moves to full U-earlier moves plus one U-priority block proposal.
    No add/drop/replace; selected set fixed.
    """
    n=len(current); seen=set()
    def emit(label,i,j,trial):
        k=tuple(x.project_id for x in trial)
        if k in seen or k==tuple(x.project_id for x in current): return None
        seen.add(k); return (label,i,j,trial)
    def pr(p):
        pid=p.project_id
        if pid.startswith('U'): return (0,pid)
        if pid.startswith('B'): return (1,pid)
        if pid.startswith('F'): return (2,pid)
        if pid.startswith('E'): return (3,pid)
        return (4,pid)
    got=emit('u_priority_block_order',None,None,sorted(list(current),key=pr))
    if got: yield got
    for i,p in enumerate(current):
        if p.project_id.startswith('U'):
            for j in range(0,i):
                rest=current[:i]+current[i+1:]
                got=emit('move_U_anywhere_earlier',i,j,rest[:j]+[p]+rest[j:])
                if got: yield got
            for j in (i-1,i+1):
                if 0<=j<n:
                    trial=list(current); trial[i],trial[j]=trial[j],trial[i]
                    got=emit('adjacent_U_swap',i,j,trial)
                    if got: yield got

def optimize_ao(seed, src_methods):
    p,ps,pmap=world(seed); scs=eng.generate_mc_scenarios(p,ps,seed*1000+424242)
    oct_md=src_methods['Octane']; std_ao=src_methods['aOctane']
    ids=structural_prune(oct_md.get('selected_ids',[]),pmap); selected=[pmap[i] for i in ids]
    oct_eval=eval_md(p,ps,scs,ids,oct_md.get('sequence_ids',[]))
    # Start from V15D standard aOctane if available and same set; this preserves standard local-swap gains.
    start_seq_ids=std_ao.get('sequence_ids',[]) if set(std_ao.get('selected_ids',[]))==set(ids) else oct_md.get('sequence_ids',[])
    base_ao=eval_md(p,ps,scs,ids,start_seq_ids)
    if valid(oct_eval) and ((not valid(base_ao)) or base_ao['p85_profit']<oct_eval['p85_profit']-EPS):
        base_ao=dict(oct_eval); start_seq_ids=oct_md.get('sequence_ids',[])
    current_seq=make_seq(pmap,ids,start_seq_ids); cur_det=det_profit(p,selected,current_seq)
    if cur_det is None: cur_det=-1e99
    checked=0; det_feas=0; det_improve=0; moves=[]
    for it in range(1,MAX_ITERS+1):
        best=None
        for typ,i,j,trial0 in focused_det_candidates(current_seq):
            checked+=1
            trial=eng._dependency_aware_stable_order(trial0)
            if seq_key(trial)==seq_key(current_seq): continue
            val=det_profit(p,selected,trial)
            if val is None: continue
            det_feas+=1
            if val<=cur_det+EPS: continue
            det_improve+=1
            if best is None or val>best['det_profit']:
                best={'move_type':typ,'from_index':i,'to_index':j,'seq':trial,'det_profit':val,'det_delta':val-cur_det}
        if best is None: break
        current_seq=best['seq']; cur_det=best['det_profit']
        moves.append({'seed':seed,'iteration':it,'move_type':best['move_type'],'from_index':best['from_index'],'to_index':best['to_index'],'det_delta':best['det_delta'],'det_profit_after':cur_det,'sequence_after':';'.join([p.project_id for p in current_seq])})
    trial=eval_md(p,ps,scs,ids,[x.project_id for x in current_seq])
    # Guard to the better of expanded Octane and standard aOctane baseline. This is an activation audit, not a new broad search.
    guard_base=base_ao if (valid(base_ao) and (not valid(oct_eval) or base_ao['p85_profit']>=oct_eval['p85_profit']-EPS)) else oct_eval
    fallback=False; reason='accepted_full_U_local_deterministic_sequence_only'
    if valid(guard_base) and ((not valid(trial)) or trial.get('p85_profit') is None or trial['p85_profit'] < guard_base['p85_profit']-EPS):
        trial=dict(guard_base); fallback=True; reason='guard_fallback_to_best_of_expanded_octane_and_standard_aoctane_after_mc1000'
    elif (not valid(oct_eval)) and valid(trial): reason='focused_detlocal_rescued_inadmissible_expanded_octane'
    elif valid(oct_eval) and valid(trial) and abs(trial['p85_profit']-oct_eval['p85_profit'])<=EPS: reason='no_paired_mc1000_gain_vs_expanded_octane'
    trial.update({'aOctane_v16_pipeline':'V16C_aOctane_start_plus_full_U_local_sequence_only_moves_with_mc1000_guard','guard_fallback_to_best_baseline':fallback,'aOctane_reason':reason,'base_expanded_octane_admissible':valid(oct_eval),'base_expanded_octane_p85':oct_eval.get('p85_profit'),'standard_aoctane_baseline_p85':base_ao.get('p85_profit'),'same_selected_set_as_expanded_octane':set(trial.get('selected_ids',[]))==set(oct_eval.get('selected_ids',[])),'same_sequence_as_expanded_octane':trial.get('sequence_ids',[])==oct_eval.get('sequence_ids',[]),'sequence_changed_vs_expanded_octane':trial.get('sequence_ids',[])!=oct_eval.get('sequence_ids',[]),'delta_vs_expanded_octane_p85':(trial.get('p85_profit')-oct_eval.get('p85_profit')) if trial.get('p85_profit') is not None and oct_eval.get('p85_profit') is not None else None,'delta_vs_standard_aoctane_baseline_p85':(trial.get('p85_profit')-base_ao.get('p85_profit')) if trial.get('p85_profit') is not None and base_ao.get('p85_profit') is not None else None,'local_candidates_checked':checked,'local_det_feasible_candidates':det_feas,'local_improving_det_candidates':det_improve,'local_accepted_move_count':len(moves),'local_search_controls':{'max_iters':MAX_ITERS,'max_move':MAX_MOVE,'selected_set_fixed':True,'add_drop_replace_allowed':False,'replacement_allowed':False}})
    return trial,oct_eval,base_ao,p,ps,moves

def usage(seed,method,p,ps,md):
    pmap={x.project_id:x for x in ps}; seq=make_seq(pmap,md.get('selected_ids',[]),md.get('sequence_ids',[])); st=eng.stage_sequence(seq,p); rows=[]
    if not st.feasible or not st.records: return rows
    end=max(r.completion_period_1 for r in st.records)
    for t0 in range(end):
        bu=cu=0.0; active=[]
        for rec in st.records:
            if rec.start_period_0<=t0<rec.completion_period_1:
                active.append(rec.project_id); d,b,c=profiles(pmap[rec.project_id]); off=t0-rec.start_period_0; bu+=b[off] if off<len(b) else 0.0; cu+=c[off] if off<len(c) else 0.0
        bcap=p.budget_restriction_profile[t0] if t0<len(p.budget_restriction_profile) else 0.0; ccap=p.constraint_capacity_profile[t0] if t0<len(p.constraint_capacity_profile) else p.constraint_capacity_profile[-1]
        rows.append({'seed':seed,'method':method,'period':t0+1,'active_count':len(active),'active_ids':';'.join(active),'budget_used':bu,'budget_cap':bcap,'budget_util_pct':bu/bcap*100 if bcap else None,'budget_ok':bu<=bcap+1e-9,'constraint_used':cu,'constraint_cap':ccap,'constraint_util_pct':cu/ccap*100 if ccap else None,'constraint_ok':cu<=ccap+1e-9})
    return rows

def metrics(seed,method,p,ps,md):
    pmap={x.project_id:x for x in ps}; u=usage(seed,method,p,ps,md); st=eng.stage_sequence(make_seq(pmap,md.get('selected_ids',[]),md.get('sequence_ids',[])),p)
    if st.feasible and st.records: start=min(r.start_period_0 for r in st.records)+1; end=max(r.completion_period_1 for r in st.records); dur=end-start+1
    else: start=end=dur=None
    ids=md.get('selected_ids',[]); bud=sum(pb(pmap[i]) for i in ids if i in pmap); con=sum(pc(pmap[i]) for i in ids if i in pmap); p85=md.get('p85_profit'); w=[r['active_count'] for r in u]
    horizon=sum(p.budget_restriction_profile[:22]); active=sum(p.budget_restriction_profile[:end]) if end else None
    return {'seed':seed,'method':method,'admissible':valid(md),'stage_feasible':md.get('stage_feasible'),'selected_count':md.get('selected_count'),'p85_profit':p85,'budget_feasibility_rate':md.get('budget_feasibility_rate'),'constraint_feasibility_rate':md.get('constraint_feasibility_rate'),'portfolio_start_period':start,'portfolio_end_period':end,'portfolio_duration_periods':dur,'portfolio_budget_det':bud,'roi_pct_used_budget':p85/bud*100 if p85 is not None and bud>0 else None,'active_budget_envelope':active,'roi_pct_active_budget_envelope':p85/active*100 if p85 is not None and active else None,'full_22p_budget_envelope':horizon,'roi_pct_full_22p_budget_envelope':p85/horizon*100 if p85 is not None and horizon else None,'total_constraint_det':con,'p85_per_constraint_unit':p85/con if p85 is not None and con>0 else None,'wip_min':min(w) if w else None,'wip_max':max(w) if w else None,'wip_avg':sum(w)/len(w) if w else None,'avg_budget_util_pct':sum([r['budget_util_pct'] for r in u])/len(u) if u else None,'max_budget_util_pct':max([r['budget_util_pct'] for r in u],default=None),'avg_constraint_util_pct':sum([r['constraint_util_pct'] for r in u])/len(u) if u else None,'max_constraint_util_pct':max([r['constraint_util_pct'] for r in u],default=None),'all_period_budget_ok':all(r['budget_ok'] for r in u) if u else False,'all_period_constraint_ok':all(r['constraint_ok'] for r in u) if u else False,'near_all_selected':md.get('selected_count',0)>=NEAR_ALL}
outputs=[]; per=[]; wm=[]; period=[]; ao_rows=[]; move_rows=[]; selrows=[]; seqrows=[]
for seed in SEEDS:
    print('seed',seed,flush=True)
    src=json.load(open(SRC/f'seed{seed:03d}.json',encoding='utf-8')); srcm=src['final_mc1000_methods']
    p,ps,pmap=world(seed); scs=eng.generate_mc_scenarios(p,ps,seed*1000+424242)
    methods={}
    for m in ['MSA','Octane','sCPA_lite']:
        md=srcm[m]; methods[m]=eval_md(p,ps,scs,md.get('selected_ids',[]),md.get('sequence_ids',[]))
    ao,oct_eval,std_ao,_,_,moves=optimize_ao(seed,srcm); methods['aOctane']=ao
    for mv in moves: move_rows.append(mv)
    adm3=[(m,methods[m]['p85_profit']) for m in RANKING if valid(methods[m])]; best3=max(adm3,key=lambda x:x[1]) if adm3 else (None,None)
    adm4=[(m,methods[m]['p85_profit']) for m in METHODS if valid(methods[m])]; best4=max(adm4,key=lambda x:x[1]) if adm4 else (None,None)
    delta=methods['sCPA_lite']['p85_profit']-best3[1] if valid(methods['sCPA_lite']) and best3[1] is not None else None
    out={'test_id':TEST_ID,'seed':seed,'pipeline':'V15D standard aOctane start + focused deterministic local U-priority sequence-only moves; no add/drop/replace; final common MC1000 guard.','final_mc1000_methods':methods,'best3_method':best3[0],'best3_p85':best3[1],'best4_method':best4[0],'best4_p85':best4[1],'scpa_delta_vs_best3':delta,'scpa_uplift_pct_vs_best3_positive_denominator_only':delta/best3[1]*100 if delta is not None and best3[1] and best3[1]>EPS else None,'scpa_beats_best3_abs':bool(delta is not None and delta>0)}
    (OUT/f'seed{seed:03d}.json').write_text(json.dumps(out,indent=2,ensure_ascii=False),encoding='utf-8'); outputs.append(out)
    row={'seed':seed,'best3_method':best3[0],'best3_p85':best3[1],'best4_method':best4[0],'best4_p85':best4[1],'scpa_delta_vs_best3':delta,'scpa_beats_best3_abs':out['scpa_beats_best3_abs']}
    for m,md in methods.items():
        sm=metrics(seed,m,p,ps,md); wm.append(sm); period.extend(usage(seed,m,p,ps,md)); row[f'{m}_admissible']=valid(md); row[f'{m}_p85']=md.get('p85_profit'); row[f'{m}_selected_count']=md.get('selected_count'); row[f'{m}_avg_budget_util_pct']=sm.get('avg_budget_util_pct'); row[f'{m}_roi_pct_used_budget']=sm.get('roi_pct_used_budget')
        for idx,pid in enumerate(md.get('selected_ids',[]),1): selrows.append({'seed':seed,'method':m,'rank':idx,'project_id':pid})
        for idx,pid in enumerate(md.get('sequence_ids',[]),1): seqrows.append({'seed':seed,'method':m,'sequence_pos':idx,'project_id':pid})
    ao_rows.append({'seed':seed,'octane_admissible':valid(methods['Octane']),'aoctane_admissible':valid(ao),'same_selected_set':ao.get('same_selected_set_as_expanded_octane'),'same_sequence':ao.get('same_sequence_as_expanded_octane'),'sequence_changed':ao.get('sequence_changed_vs_expanded_octane'),'guard_fallback_to_best_baseline':ao.get('guard_fallback_to_best_baseline'),'aoctane_reason':ao.get('aOctane_reason'),'octane_p85':methods['Octane'].get('p85_profit'),'standard_aoctane_baseline_p85':ao.get('standard_aoctane_baseline_p85'),'aoctane_p85':ao.get('p85_profit'),'delta_vs_expanded_octane_p85':ao.get('delta_vs_expanded_octane_p85'),'delta_vs_standard_aoctane_baseline_p85':ao.get('delta_vs_standard_aoctane_baseline_p85'),'local_candidates_checked':ao.get('local_candidates_checked'),'local_det_feasible_candidates':ao.get('local_det_feasible_candidates'),'local_improving_det_candidates':ao.get('local_improving_det_candidates'),'local_accepted_move_count':ao.get('local_accepted_move_count')})
    per.append(row)
write_csv(OUT/'per_seed_summary.csv',per); write_csv(OUT/'world_method_summary_schedule_budget_wip_roi_utilization.csv',wm); write_csv(OUT/'period_budget_constraint_wip_by_world_method_det.csv',period); write_csv(OUT/'selected_projects_by_world_method.csv',selrows); write_csv(OUT/'sequence_by_world_method.csv',seqrows); write_csv(OUT/'octane_to_v17c_full_u_local_aoctane_audit.csv',ao_rows); write_csv(OUT/'v17c_accepted_local_moves.csv',move_rows)
medrows=[]
for m in METHODS:
    rows=[x for x in wm if x['method']==m and x['admissible']]
    def med(k):
        vals=[x[k] for x in rows if x.get(k) is not None]; return statistics.median(vals) if vals else None
    medrows.append({'method':m,'admissible_worlds':len(rows),'median_selected_count':med('selected_count'),'median_p85_profit':med('p85_profit'),'median_roi_pct_used_budget':med('roi_pct_used_budget'),'median_roi_pct_active_budget_envelope':med('roi_pct_active_budget_envelope'),'median_roi_pct_full_22p_budget_envelope':med('roi_pct_full_22p_budget_envelope'),'median_duration':med('portfolio_duration_periods'),'median_portfolio_budget_det':med('portfolio_budget_det'),'median_avg_budget_util_pct':med('avg_budget_util_pct'),'median_max_budget_util_pct':med('max_budget_util_pct'),'median_avg_constraint_util_pct':med('avg_constraint_util_pct'),'median_max_constraint_util_pct':med('max_constraint_util_pct'),'median_p85_per_constraint_unit':med('p85_per_constraint_unit'),'median_wip_avg':med('wip_avg'),'median_wip_max':med('wip_max'),'near_all_selected_worlds':sum(1 for x in rows if x.get('near_all_selected'))})
write_csv(OUT/'method_level_medians.csv',medrows)
usable=[r['seed'] for r in outputs if r['best3_method']]; strict=[r['seed'] for r in outputs if all(valid(r['final_mc1000_methods'][m]) for m in METHODS)]
paired=[r for r in ao_rows if r['octane_admissible'] and r['aoctane_admissible'] and r['delta_vs_expanded_octane_p85'] is not None]
pos=[r for r in paired if r['delta_vs_expanded_octane_p85']>EPS]
pos2=[r for r in ao_rows if r['delta_vs_standard_aoctane_baseline_p85'] is not None and r['delta_vs_standard_aoctane_baseline_p85']>EPS]
summary={'test_id':TEST_ID,'status':'V17C activation audit: starts from V17C aOctane, fixes selected set to expanded Octane, allows full U-earlier sequence-only moves plus U-priority block, no add/drop/replace, and guards to the better of expanded Octane and prior aOctane baseline.','method_admissible_counts':{m:sum(valid(r['final_mc1000_methods'][m]) for r in outputs) for m in METHODS},'usable_ranking_comparison_worlds':len(usable),'usable_ranking_comparison_seeds':usable,'strict_4way_worlds':len(strict),'strict_4way_seeds':strict,'scpa_beats_best3_abs_worlds':sum(r['scpa_beats_best3_abs'] for r in outputs),'scpa_best4_worlds':sum(r['best4_method']=='sCPA_lite' for r in outputs),'aOctane_diagnostic':{'paired_admissible_worlds':len(paired),'same_selected_set_worlds':sum(1 for r in ao_rows if r['same_selected_set']),'same_sequence_worlds':sum(1 for r in ao_rows if r['same_sequence']),'sequence_changed_worlds':sum(1 for r in ao_rows if r['sequence_changed']),'positive_p85_improvement_vs_expanded_octane_worlds':len(pos),'positive_p85_improvement_vs_standard_aoctane_baseline_worlds':len(pos2),'median_paired_delta_vs_expanded_octane':statistics.median([r['delta_vs_expanded_octane_p85'] for r in paired]) if paired else None,'mean_paired_delta_vs_expanded_octane':statistics.mean([r['delta_vs_expanded_octane_p85'] for r in paired]) if paired else None,'median_positive_delta_only_vs_expanded_octane':statistics.median([r['delta_vs_expanded_octane_p85'] for r in pos]) if pos else None,'median_extra_delta_over_standard_aoctane_positive_only':statistics.median([r['delta_vs_standard_aoctane_baseline_p85'] for r in pos2]) if pos2 else None,'guard_fallback_worlds':sum(1 for r in ao_rows if r['guard_fallback_to_best_baseline']),'total_accepted_local_moves':sum(r.get('local_accepted_move_count') or 0 for r in ao_rows)},'method_level_medians':medrows}
(OUT/'summary.json').write_text(json.dumps({'summary':summary,'per_seed':per,'method_level_medians':medrows,'aOctane_audit':ao_rows,'accepted_local_moves':move_rows},indent=2,ensure_ascii=False),encoding='utf-8')
sus=[]
for x in wm:
    sig=[]
    if x['selected_count'] and x['selected_count']>=NEAR_ALL: sig.append('near_all_selected')
    if x['portfolio_duration_periods'] and x['selected_count'] and x['selected_count']>=24 and x['portfolio_duration_periods']<=8: sig.append('many_projects_short_duration')
    if x['stage_feasible'] and not x['all_period_budget_ok']: sig.append('period_budget_violation')
    if x['stage_feasible'] and not x['all_period_constraint_ok']: sig.append('period_constraint_violation')
    if sig: sus.append({'seed':x['seed'],'method':x['method'],'signals':';'.join(sig),'selected_count':x['selected_count'],'duration':x['portfolio_duration_periods']})
write_csv(OUT/'suspicious_signal_audit.csv',sus)
report=[TEST_ID,'',summary['status'],'',f"Method admissible counts: {summary['method_admissible_counts']}",f"Usable ranking: {len(usable)}/10; strict 4-way: {len(strict)}/10; sCPA beats best ranking: {summary['scpa_beats_best3_abs_worlds']}/{len(usable)}; sCPA best overall: {summary['scpa_best4_worlds']}/10",f"aOctane diagnostic: {summary['aOctane_diagnostic']}",'','Method medians over admissible worlds:']
for r in medrows: report.append(f"- {r['method']}: adm {r['admissible_worlds']}/10; selected {r['median_selected_count']}; P85 {r['median_p85_profit']}; ROI used budget {r['median_roi_pct_used_budget']}%; ROI full 22p {r['median_roi_pct_full_22p_budget_envelope']}%; avg budget util {r['median_avg_budget_util_pct']}%; avg constraint util {r['median_avg_constraint_util_pct']}%; P85/constraint {r['median_p85_per_constraint_unit']}")
report.append('\naOctane seed audit:')
for r in ao_rows: report.append(f"- seed {r['seed']}: Octane adm={r['octane_admissible']} P85={r['octane_p85']}; standardAO={r['standard_aoctane_baseline_p85']}; V17C aOctane adm={r['aoctane_admissible']} P85={r['aoctane_p85']}; delta_vs_O={r['delta_vs_expanded_octane_p85']}; extra_vs_stdAO={r['delta_vs_standard_aoctane_baseline_p85']}; same_seq={r['same_sequence']}; fallback={r['guard_fallback_to_best_baseline']}; accepted_moves={r['local_accepted_move_count']}; reason={r['aoctane_reason']}")
(OUT/'REPORT_BG.txt').write_text('\n'.join(report),encoding='utf-8')
if ZIP.exists(): ZIP.unlink()
with zipfile.ZipFile(ZIP,'w',zipfile.ZIP_DEFLATED) as z:
    for fp in OUT.rglob('*'):
        if fp.is_file(): z.write(fp,arcname=fp.relative_to(OUT))
    z.write('/mnt/data/run_v17c_full_u_local_aoctane.py',arcname='reproduction_scripts/run_v17c_full_u_local_aoctane.py')
print('WROTE',ZIP)
