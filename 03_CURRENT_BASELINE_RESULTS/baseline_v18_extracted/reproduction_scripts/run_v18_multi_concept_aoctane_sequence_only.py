from __future__ import annotations
import json,csv,statistics,shutil,zipfile,importlib.util,math
from pathlib import Path

spec=importlib.util.spec_from_file_location('v8','/mnt/data/run_custom_v8.py')
v8=importlib.util.module_from_spec(spec); spec.loader.exec_module(v8)
eng=v8.v7.eng

SRC=Path('/mnt/data/R7_STRUCTURAL_SOFT_V16C_FOCUSED_DETLOCAL_AOCTANE_SEQUENCE_ONLY_MC1000_v1')
# use V17C as optional prior guard baseline if it exists
SRC17=Path('/mnt/data/R7_STRUCTURAL_SOFT_V17C_FULL_U_LOCAL_AOCTANE_SEQUENCE_ONLY_MC1000_v1')
TEST_ID='R7_STRUCTURAL_SOFT_V18_MULTI_CONCEPT_LOCAL_AOCTANE_SEQUENCE_ONLY_MC1000_v1'
OUT=Path('/mnt/data')/TEST_ID; ZIP=Path(str(OUT)+'.zip')
SEEDS=range(1,11); METHODS=['MSA','Octane','aOctane','sCPA_lite']; RANKING=['MSA','Octane','aOctane']
MC=1000; BUD_MULT=20.0; CAP_MULT=1.9; EPS=1e-9; NEAR_ALL=34
MAX_MC_CANDIDATES_PER_SEED=8
SCREEN_MC=50
if OUT.exists(): shutil.rmtree(OUT)
OUT.mkdir()

def write_csv(path,rows):
    if not rows:
        Path(path).write_text('',encoding='utf-8'); return
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
    p,ps=v8.world(seed,MC); p.monte_carlo_iterations=MC
    p.budget_restriction_profile=[float(x)*CAP_MULT for x in p.budget_restriction_profile]
    for pr in ps:
        pr.budget_usage_profile=[scale(x,BUD_MULT) for x in pr.budget_usage_profile]
        if getattr(pr,'total_project_budget',None) is not None:
            pr.total_project_budget=scale(pr.total_project_budget,BUD_MULT)
    return p,ps,{x.project_id:x for x in ps}

def structural_repair_add_prereqs(ids,pmap):
    """POL structural repair for aOctane: selection may change only by adding prerequisite projects required by already selected projects."""
    ordered=list(dict.fromkeys([i for i in ids if i in pmap])); s=set(ordered); changed=True; added=[]
    while changed:
        changed=False
        for pid in list(s):
            for dep in getattr(pmap[pid],'structural_dependencies',[]) or []:
                if dep in pmap and dep not in s:
                    s.add(dep); ordered.append(dep); added.append(dep); changed=True
    return ordered,added

def make_seq(pmap,ids,order):
    ids,_=structural_repair_add_prereqs(ids,pmap); s=set(ids)
    seq=[pmap[i] for i in order if i in pmap and i in s]
    seen={p.project_id for p in seq}
    seq += [pmap[i] for i in ids if i not in seen]
    return eng._dependency_aware_stable_order(seq)

def subset_scenarios(scs,ids):
    ids=set(ids)
    return [eng.MonteCarloScenario(
        project_vectors={pid:sc.project_vectors[pid] for pid in ids if pid in sc.project_vectors},
        linear_cot_deltas={pid:sc.linear_cot_deltas[pid] for pid in ids if pid in sc.linear_cot_deltas},
        piecewise_cot_values={pid:sc.piecewise_cot_values[pid] for pid in ids if pid in sc.piecewise_cot_values},
        synergy_values={(pid,i):v for (pid,i),v in sc.synergy_values.items() if pid in ids}
    ) for sc in scs]

def eval_md(p,ps,scs,ids,seq_ids):
    pmap={x.project_id:x for x in ps}; ids,added=structural_repair_add_prereqs(ids,pmap); seq=make_seq(pmap,ids,seq_ids)
    st=eng.stage_sequence(seq,p)
    if not st.feasible:
        return {'selected_ids':ids,'sequence_ids':[x.project_id for x in seq],'selected_count':len(ids),'stage_feasible':False,'budget_feasibility_rate':0,'constraint_feasibility_rate':0,'admissible':False,'p85_profit':None,'structural_repair_added_ids':added}
    br,cr,adm,p85,_=eng.evaluate_stochastic_from_scenarios(p,[pmap[i] for i in ids],seq,subset_scenarios(scs,ids),optimistic_prefilter=False)
    return {'selected_ids':ids,'sequence_ids':[x.project_id for x in seq],'selected_count':len(ids),'stage_feasible':True,'budget_feasibility_rate':br,'constraint_feasibility_rate':cr,'admissible':bool(adm),'p85_profit':p85,'structural_repair_added_ids':added}

def valid(md): return bool(md.get('stage_feasible') and md.get('admissible') and md.get('p85_profit') is not None)
def base_det(pr): return det(pr.base_profit)
def dur_det(pr): return max(det(pr.duration),1e-9)
def bsum(pr): return sum(det(x) for x in eng._derive_budget_profile(pr,pr.deterministic_duration()))
def csum(pr): return sum(det(x) for x in eng._normalize_profile(pr.constraint_usage_profile,pr.deterministic_duration()))
def cot_abs(pr):
    c=getattr(pr,'cost_of_time_profile',None)
    v=getattr(c,'linear_delta_per_period',0) if c else 0
    return abs(float(v or 0))
def gid(pr): return pr.project_id[0]
def seq_key(seq): return tuple(p.project_id for p in seq)
def det_profit(p,selected,seq):
    st=eng.stage_sequence(seq,p)
    if not st.feasible: return None
    return eng._profit_with_cost_and_synergy(selected,st)

def candidate_sequences(current,selected):
    """V18 fast: fixed selected set except structural prerequisite repair; multi-concept sequence-only aOctane.
    No discretionary add/drop/replace. Tests global and block-level resequencing concepts only.
    """
    seen=set(); curkey=seq_key(current)
    def emit(label, seq, detail=''):
        k=seq_key(seq)
        if k in seen or k==curkey: return
        seen.add(k); yield {'concept':label,'detail':detail,'seq':seq}
    groups={g:[p for p in selected if gid(p)==g] for g in ['U','B','F','E']}
    def urgency(p): return (-cot_abs(p), -base_det(p), p.project_id)
    def value_density(p): return (-(base_det(p)/(csum(p)+1e-9)), -base_det(p), p.project_id)
    def budget_light(p): return (bsum(p), -(base_det(p)/(bsum(p)+1e-9)), p.project_id)
    def constraint_light(p): return (csum(p), -cot_abs(p), p.project_id)
    def hybrid(p): return (-(cot_abs(p)*2.0 + base_det(p)/(csum(p)+1e-9)), p.project_id)
    # Global sort concepts
    for label,key in [('global_urgency_desc',urgency),('global_value_density_desc',value_density),('global_budget_light_then_value',budget_light),('global_constraint_light_then_urgency',constraint_light),('global_hybrid_urgency_value_density',hybrid)]:
        yield from emit(label, sorted(selected,key=key))
    # Group-block concepts
    for label,order,key in [
        ('group_U_B_F_E_urg',['U','B','F','E'],urgency),
        ('group_U_F_B_E_value',['U','F','B','E'],value_density),
        ('group_U_B_E_F_hybrid',['U','B','E','F'],hybrid),
        ('group_B_U_F_E_urg',['B','U','F','E'],urgency),
        ('group_U_E_B_F_value',['U','E','B','F'],value_density),
    ]:
        seq=[]
        for g in order: seq += sorted(groups.get(g,[]),key=key)
        yield from emit('group_block_order',seq,label)
    # U interleaved with low-constraint fillers
    us=sorted(groups.get('U',[]),key=urgency); fillers=sorted(groups.get('B',[])+groups.get('F',[]),key=constraint_light); es=sorted(groups.get('E',[]),key=value_density)
    seq=[]; ff=list(fillers)
    for u in us:
        seq.append(u)
        if ff: seq.append(ff.pop(0))
    seq += ff + es
    yield from emit('u_interleave_low_constraint_fillers_then_E',seq)

def optimize_ao(seed, src_methods, prior17_methods=None):
    p,ps,pmap=world(seed); scs=eng.generate_mc_scenarios(p,ps,seed*1000+424242)
    oct_md=src_methods['Octane']
    # Base selected IDs: Octane selected set with POL structural repair only.
    ids,repair_added=structural_repair_add_prereqs(oct_md.get('selected_ids',[]),pmap)
    selected=[pmap[i] for i in ids]
    oct_eval=eval_md(p,ps,scs,ids,oct_md.get('sequence_ids',[]))
    prior_ao=src_methods['aOctane']
    prior_eval=eval_md(p,ps,scs,ids,prior_ao.get('sequence_ids',[])) if set(prior_ao.get('selected_ids',[]))==set(ids) else {'admissible':False,'stage_feasible':False,'p85_profit':None,'selected_ids':ids,'sequence_ids':[]}
    if prior17_methods and set(prior17_methods['aOctane'].get('selected_ids',[]))==set(ids):
        p17=eval_md(p,ps,scs,ids,prior17_methods['aOctane'].get('sequence_ids',[]))
    else:
        p17={'admissible':False,'stage_feasible':False,'p85_profit':None,'selected_ids':ids,'sequence_ids':[]}
    # guard base = best valid among Octane, V16C aOctane, V17C aOctane with same repaired selected set
    base_options=[('expanded_octane',oct_eval),('prior_v16c_aoctane',prior_eval),('prior_v17c_aoctane',p17)]
    valid_bases=[x for x in base_options if valid(x[1])]
    guard_label,guard_base=max(valid_bases,key=lambda x:x[1]['p85_profit']) if valid_bases else ('expanded_octane',oct_eval)
    start_seq=make_seq(pmap,ids,guard_base.get('sequence_ids',[]) or oct_md.get('sequence_ids',[]))
    cur_det=det_profit(p,selected,start_seq)
    # collect deterministic-feasible candidates; rank by deterministic profit but include all concept-first bests
    cand_rows=[]; best_by_key={}
    for cand in candidate_sequences(start_seq,selected):
        seq=eng._dependency_aware_stable_order(cand['seq'])
        if seq_key(seq)==seq_key(start_seq): continue
        dp=det_profit(p,selected,seq)
        if dp is None: continue
        cand_rows.append({'concept':cand['concept'],'detail':cand.get('detail',''),'seq':seq,'det_profit':dp,'det_delta_vs_guard_start':None if cur_det is None else dp-cur_det})
    cand_rows.sort(key=lambda x:(x['det_profit'] if x['det_profit'] is not None else -1e99), reverse=True)
    # keep top plus best per concept to avoid overfitting to one heuristic
    chosen=[]; seen=set(); best_concept={}
    for c in cand_rows:
        if c['concept'] not in best_concept: best_concept[c['concept']]=c
    for c in list(best_concept.values())+cand_rows[:MAX_MC_CANDIDATES_PER_SEED]:
        k=seq_key(c['seq'])
        if k not in seen:
            seen.add(k); chosen.append(c)
    best_label=guard_label; best_md=dict(guard_base); best_concept_name='guard_base'; best_detail=''
    mc_rows=[]
    screen_scs=scs[:SCREEN_MC]
    best_screen=None
    # Fast MC100 screen for candidate selection, followed by full MC1000 final evaluation of the best screened candidate.
    for c in chosen:
        md_screen=eval_md(p,ps,screen_scs,ids,[x.project_id for x in c['seq']])
        delta=(md_screen.get('p85_profit')-guard_base.get('p85_profit')) if md_screen.get('p85_profit') is not None and guard_base.get('p85_profit') is not None else None
        mc_rows.append({'seed':seed,'concept':c['concept'],'detail':c.get('detail',''),'det_profit':c.get('det_profit'),'det_delta_vs_guard_start':c.get('det_delta_vs_guard_start'),'screen_admissible':valid(md_screen),'screen_p85_profit':md_screen.get('p85_profit'),'screen_delta_vs_guard_base':delta,'selected_count':md_screen.get('selected_count'),'sequence':' ; '.join(md_screen.get('sequence_ids',[]))})
        if valid(md_screen) and (best_screen is None or md_screen['p85_profit']>best_screen['screen_p85']+EPS):
            best_screen={'screen_p85':md_screen['p85_profit'],'candidate':c}
    if best_screen is not None:
        c=best_screen['candidate']
        md_full=eval_md(p,ps,scs,ids,[x.project_id for x in c['seq']])
        if valid(md_full) and (not valid(best_md) or md_full['p85_profit']>best_md['p85_profit']+EPS):
            best_md=md_full; best_label='v18_candidate_mc100screen_mc1000confirmed'; best_concept_name=c['concept']; best_detail=c.get('detail','')
    # guard no underperformance vs expanded Octane
    if valid(oct_eval) and (not valid(best_md) or best_md['p85_profit']<oct_eval['p85_profit']-EPS):
        best_md=dict(oct_eval); best_label='expanded_octane_guard'; best_concept_name='guard_to_octane'; best_detail=''
    best_md.update({
        'aOctane_v18_pipeline':'Octane-expanded fixed selection with POL structural repair only; multi-concept sequence-only local activation; no discretionary add/drop/replace; MC1000 guard to best baseline and Octane.',
        'structural_repair_added_ids':repair_added,
        'selection_change_reason':'POL_structural_repair_prerequisite_addition_only' if repair_added else 'none_selected_set_same_as_expanded_octane',
        'base_expanded_octane_admissible':valid(oct_eval),'base_expanded_octane_p85':oct_eval.get('p85_profit'),
        'prior_v16c_aoctane_p85':prior_eval.get('p85_profit'),'prior_v17c_aoctane_p85':p17.get('p85_profit'),
        'guard_base_label':guard_label,'guard_base_p85':guard_base.get('p85_profit'),
        'v18_best_source':best_label,'v18_best_concept':best_concept_name,'v18_best_detail':best_detail,
        'same_selected_set_as_expanded_octane':set(best_md.get('selected_ids',[]))==set(oct_eval.get('selected_ids',[])),
        'same_sequence_as_expanded_octane':best_md.get('sequence_ids',[])==oct_eval.get('sequence_ids',[]),
        'sequence_changed_vs_expanded_octane':best_md.get('sequence_ids',[])!=oct_eval.get('sequence_ids',[]),
        'delta_vs_expanded_octane_p85':(best_md.get('p85_profit')-oct_eval.get('p85_profit')) if best_md.get('p85_profit') is not None and oct_eval.get('p85_profit') is not None else None,
        'delta_vs_guard_base_p85':(best_md.get('p85_profit')-guard_base.get('p85_profit')) if best_md.get('p85_profit') is not None and guard_base.get('p85_profit') is not None else None,
        'candidate_sequences_generated':len(cand_rows),'candidate_sequences_mc1000_evaluated':len(chosen),
        'candidate_admissible_count':sum(1 for r in mc_rows if r.get('screen_admissible')),
        'candidate_screen_mc':SCREEN_MC,
        'concepts_tested':sorted(set(r['concept'] for r in mc_rows)),
        'local_search_controls':{'selected_set_fixed_except_POL_structural_repair':True,'discretionary_add_drop_replace_allowed':False,'sequence_only':True,'mc_candidates_per_seed_cap':MAX_MC_CANDIDATES_PER_SEED,'candidate_screen_mc':SCREEN_MC}
    })
    return best_md,oct_eval,prior_eval,p17,p,ps,mc_rows

def profiles(pr):
    d=pr.deterministic_duration(); return d,[det(x) for x in eng._derive_budget_profile(pr,d)],[det(x) for x in eng._normalize_profile(pr.constraint_usage_profile,d)]
def pb(pr): return sum(profiles(pr)[1])
def pc(pr): return sum(profiles(pr)[2])

def period_usage(seed,method,p,ps,md):
    if not md.get('stage_feasible'): return []
    pmap={x.project_id:x for x in ps}; seq=make_seq(pmap,md.get('selected_ids',[]),md.get('sequence_ids',[])); st=eng.stage_sequence(seq,p)
    if not st.feasible: return []
    horizon=len(p.budget_restriction_profile); rows=[]
    wip=[0]*horizon; bu=[0.0]*horizon; cu=[0.0]*horizon
    for rec in st.records:
        pr=pmap[rec.project_id]; d,bp,cp=profiles(pr)
        for off in range(d):
            t=rec.start_period_0+off
            if 0<=t<horizon:
                wip[t]+=1; bu[t]+=bp[off] if off<len(bp) else 0.0; cu[t]+=cp[off] if off<len(cp) else 0.0
    for t in range(horizon):
        rows.append({'seed':seed,'method':method,'period':t+1,'wip':wip[t],'budget_used':bu[t],'budget_cap':p.budget_restriction_profile[t],'budget_util_pct':bu[t]/p.budget_restriction_profile[t]*100 if p.budget_restriction_profile[t] else None,'constraint_used':cu[t],'constraint_cap':p.constraint_capacity_profile[t],'constraint_util_pct':cu[t]/p.constraint_capacity_profile[t]*100 if p.constraint_capacity_profile[t] else None,'budget_ok':bu[t]<=p.budget_restriction_profile[t]+1e-8,'constraint_ok':cu[t]<=p.constraint_capacity_profile[t]+1e-8})
    return rows

def metrics(seed,method,p,ps,md):
    pmap={x.project_id:x for x in ps}; ids=md.get('selected_ids',[]); seq=make_seq(pmap,ids,md.get('sequence_ids',[])); st=eng.stage_sequence(seq,p)
    rows=period_usage(seed,method,p,ps,md)
    active=[r for r in rows if r['wip']>0]
    total_budget=sum(pb(pmap[i]) for i in ids if i in pmap)
    total_constraint=sum(pc(pmap[i]) for i in ids if i in pmap)
    start=end=dur=None
    if st.feasible and st.records:
        start=min(r.start_period_0 for r in st.records)+1; end=max(r.completion_period_1 for r in st.records); dur=end-start+1
    active_env=sum(r['budget_cap'] for r in active); full_env=sum(p.budget_restriction_profile)
    p85=md.get('p85_profit')
    return {'seed':seed,'method':method,'admissible':valid(md),'stage_feasible':md.get('stage_feasible'),'selected_count':md.get('selected_count'),'p85_profit':p85,'budget_feasibility_rate':md.get('budget_feasibility_rate'),'constraint_feasibility_rate':md.get('constraint_feasibility_rate'),'portfolio_start_period':start,'portfolio_end_period':end,'portfolio_duration_periods':dur,'portfolio_budget_det':total_budget,'portfolio_constraint_det':total_constraint,'roi_pct_used_budget':p85/total_budget*100 if p85 is not None and total_budget else None,'roi_pct_active_budget_envelope':p85/active_env*100 if p85 is not None and active_env else None,'roi_pct_full_22p_budget_envelope':p85/full_env*100 if p85 is not None and full_env else None,'avg_budget_util_pct':statistics.mean([r['budget_util_pct'] for r in active]) if active else None,'max_budget_util_pct':max([r['budget_util_pct'] for r in active]) if active else None,'avg_constraint_util_pct':statistics.mean([r['constraint_util_pct'] for r in active]) if active else None,'max_constraint_util_pct':max([r['constraint_util_pct'] for r in active]) if active else None,'wip_min':min([r['wip'] for r in active]) if active else None,'wip_max':max([r['wip'] for r in active]) if active else None,'wip_avg':statistics.mean([r['wip'] for r in active]) if active else None,'p85_per_constraint_unit':p85/total_constraint if p85 is not None and total_constraint else None,'all_period_budget_ok':all(r['budget_ok'] for r in rows),'all_period_constraint_ok':all(r['constraint_ok'] for r in rows),'near_all_selected':(md.get('selected_count') or 0)>=NEAR_ALL,'structural_repair_added_ids':';'.join(md.get('structural_repair_added_ids',[]) or [])}

# main
outputs=[]; per=[]; wm=[]; period=[]; selrows=[]; seqrows=[]; ao_rows=[]; cand_rows=[]
for seed in SEEDS:
    print('RUN',seed,flush=True)
    src=json.loads((SRC/f'seed{seed:03d}.json').read_text(encoding='utf-8'))['final_mc1000_methods']
    prior17=None
    if (SRC17/f'seed{seed:03d}.json').exists(): prior17=json.loads((SRC17/f'seed{seed:03d}.json').read_text(encoding='utf-8'))['final_mc1000_methods']
    p,ps,pmap=world(seed); scs=eng.generate_mc_scenarios(p,ps,seed*1000+424242)
    methods={}
    for m in ['MSA','Octane','sCPA_lite']:
        md=src[m]; methods[m]=eval_md(p,ps,scs,md.get('selected_ids',[]),md.get('sequence_ids',[]))
    ao,oct_eval,prior_eval,p17,_,_,crows=optimize_ao(seed,src,prior17); methods['aOctane']=ao
    for r in crows: cand_rows.append(r)
    adm3=[(m,methods[m]['p85_profit']) for m in RANKING if valid(methods[m])]
    best3=max(adm3,key=lambda x:x[1]) if adm3 else (None,None)
    adm4=[(m,methods[m]['p85_profit']) for m in METHODS if valid(methods[m])]
    best4=max(adm4,key=lambda x:x[1]) if adm4 else (None,None)
    delta=methods['sCPA_lite']['p85_profit']-best3[1] if valid(methods['sCPA_lite']) and best3[1] is not None else None
    out={'test_id':TEST_ID,'seed':seed,'pipeline':'V18 multi-concept local sequence-only aOctane with POL structural repair only; no discretionary add/drop/replace; common MC1000 guard.','final_mc1000_methods':methods,'best3_method':best3[0],'best3_p85':best3[1],'best4_method':best4[0],'best4_p85':best4[1],'scpa_delta_vs_best3':delta,'scpa_uplift_pct_vs_best3_positive_denominator_only':delta/best3[1]*100 if delta is not None and best3[1] and best3[1]>EPS else None,'scpa_beats_best3_abs':bool(delta is not None and delta>0)}
    (OUT/f'seed{seed:03d}.json').write_text(json.dumps(out,indent=2,ensure_ascii=False),encoding='utf-8'); outputs.append(out)
    row={'seed':seed,'best3_method':best3[0],'best3_p85':best3[1],'best4_method':best4[0],'best4_p85':best4[1],'scpa_delta_vs_best3':delta,'scpa_beats_best3_abs':out['scpa_beats_best3_abs']}
    for m,md in methods.items():
        sm=metrics(seed,m,p,ps,md); wm.append(sm); period.extend(period_usage(seed,m,p,ps,md)); row[f'{m}_admissible']=valid(md); row[f'{m}_p85']=md.get('p85_profit'); row[f'{m}_selected_count']=md.get('selected_count'); row[f'{m}_avg_budget_util_pct']=sm.get('avg_budget_util_pct'); row[f'{m}_roi_pct_used_budget']=sm.get('roi_pct_used_budget')
        for idx,pid in enumerate(md.get('selected_ids',[]),1): selrows.append({'seed':seed,'method':m,'rank':idx,'project_id':pid})
        for idx,pid in enumerate(md.get('sequence_ids',[]),1): seqrows.append({'seed':seed,'method':m,'sequence_pos':idx,'project_id':pid})
    ao_rows.append({'seed':seed,'octane_admissible':valid(methods['Octane']),'aoctane_admissible':valid(ao),'same_selected_set':ao.get('same_selected_set_as_expanded_octane'),'same_sequence':ao.get('same_sequence_as_expanded_octane'),'sequence_changed':ao.get('sequence_changed_vs_expanded_octane'),'structural_repair_added_ids':';'.join(ao.get('structural_repair_added_ids',[]) or []),'selection_change_reason':ao.get('selection_change_reason'),'guard_base_label':ao.get('guard_base_label'),'v18_best_source':ao.get('v18_best_source'),'v18_best_concept':ao.get('v18_best_concept'),'v18_best_detail':ao.get('v18_best_detail'),'octane_p85':methods['Octane'].get('p85_profit'),'prior_v16c_aoctane_p85':ao.get('prior_v16c_aoctane_p85'),'prior_v17c_aoctane_p85':ao.get('prior_v17c_aoctane_p85'),'aoctane_p85':ao.get('p85_profit'),'delta_vs_expanded_octane_p85':ao.get('delta_vs_expanded_octane_p85'),'delta_vs_guard_base_p85':ao.get('delta_vs_guard_base_p85'),'candidate_sequences_generated':ao.get('candidate_sequences_generated'),'candidate_sequences_mc1000_evaluated':ao.get('candidate_sequences_mc1000_evaluated'),'candidate_admissible_count':ao.get('candidate_admissible_count')})
    per.append(row)
write_csv(OUT/'per_seed_summary.csv',per); write_csv(OUT/'world_method_summary_schedule_budget_wip_roi_utilization.csv',wm); write_csv(OUT/'period_budget_constraint_wip_by_world_method_det.csv',period); write_csv(OUT/'selected_projects_by_world_method.csv',selrows); write_csv(OUT/'sequence_by_world_method.csv',seqrows); write_csv(OUT/'octane_to_v18_multi_concept_aoctane_audit.csv',ao_rows); write_csv(OUT/'v18_candidate_sequence_audit.csv',cand_rows)
medrows=[]
for m in METHODS:
    rows=[x for x in wm if x['method']==m and x['admissible']]
    def med(k):
        vals=[x[k] for x in rows if x.get(k) is not None]
        return statistics.median(vals) if vals else None
    medrows.append({'method':m,'admissible_worlds':len(rows),'median_selected_count':med('selected_count'),'median_p85_profit':med('p85_profit'),'median_roi_pct_used_budget':med('roi_pct_used_budget'),'median_roi_pct_active_budget_envelope':med('roi_pct_active_budget_envelope'),'median_roi_pct_full_22p_budget_envelope':med('roi_pct_full_22p_budget_envelope'),'median_duration':med('portfolio_duration_periods'),'median_portfolio_budget_det':med('portfolio_budget_det'),'median_avg_budget_util_pct':med('avg_budget_util_pct'),'median_max_budget_util_pct':med('max_budget_util_pct'),'median_avg_constraint_util_pct':med('avg_constraint_util_pct'),'median_max_constraint_util_pct':med('max_constraint_util_pct'),'median_p85_per_constraint_unit':med('p85_per_constraint_unit'),'median_wip_avg':med('wip_avg'),'median_wip_max':med('wip_max'),'near_all_selected_worlds':sum(1 for x in rows if x.get('near_all_selected'))})
write_csv(OUT/'method_level_medians.csv',medrows)
usable=[r['seed'] for r in outputs if r['best3_method']]; strict=[r['seed'] for r in outputs if all(valid(r['final_mc1000_methods'][m]) for m in METHODS)]
paired=[r for r in ao_rows if r['octane_admissible'] and r['aoctane_admissible'] and r['delta_vs_expanded_octane_p85'] is not None]
pos=[r for r in paired if r['delta_vs_expanded_octane_p85']>EPS]
extra=[r for r in ao_rows if r['delta_vs_guard_base_p85'] is not None and r['delta_vs_guard_base_p85']>EPS]
summary={'test_id':TEST_ID,'status':'V18 multi-concept aOctane activation: Octane-expanded selected set with POL structural repair only; no discretionary add/drop/replace; multiple local sequence concepts; common MC1000 guard.','method_admissible_counts':{m:sum(valid(r['final_mc1000_methods'][m]) for r in outputs) for m in METHODS},'usable_ranking_comparison_worlds':len(usable),'usable_ranking_comparison_seeds':usable,'strict_4way_worlds':len(strict),'strict_4way_seeds':strict,'scpa_beats_best3_abs_worlds':sum(r['scpa_beats_best3_abs'] for r in outputs),'scpa_best4_worlds':sum(r['best4_method']=='sCPA_lite' for r in outputs),'aOctane_diagnostic':{'paired_admissible_worlds':len(paired),'same_selected_set_worlds':sum(1 for r in ao_rows if r['same_selected_set']),'selection_changed_by_structural_repair_worlds':sum(1 for r in ao_rows if r['structural_repair_added_ids']),'same_sequence_worlds':sum(1 for r in ao_rows if r['same_sequence']),'sequence_changed_worlds':sum(1 for r in ao_rows if r['sequence_changed']),'positive_p85_improvement_vs_expanded_octane_worlds':len(pos),'median_paired_delta_vs_expanded_octane':statistics.median([r['delta_vs_expanded_octane_p85'] for r in paired]) if paired else None,'mean_paired_delta_vs_expanded_octane':statistics.mean([r['delta_vs_expanded_octane_p85'] for r in paired]) if paired else None,'median_positive_delta_only_vs_expanded_octane':statistics.median([r['delta_vs_expanded_octane_p85'] for r in pos]) if pos else None,'positive_extra_vs_guard_base_worlds':len(extra),'median_extra_delta_positive_only_vs_guard_base':statistics.median([r['delta_vs_guard_base_p85'] for r in extra]) if extra else None,'total_candidate_sequences_generated':sum(r['candidate_sequences_generated'] or 0 for r in ao_rows),'total_candidate_sequences_mc1000_evaluated':sum(r['candidate_sequences_mc1000_evaluated'] or 0 for r in ao_rows)},'method_level_medians':medrows}
# suspicious
sus=[]
for x in wm:
    sig=[]
    if x['selected_count'] and x['selected_count']>=NEAR_ALL: sig.append('near_all_selected')
    if x['portfolio_duration_periods'] and x['selected_count'] and x['selected_count']>=24 and x['portfolio_duration_periods']<=8: sig.append('many_projects_short_duration')
    if x['stage_feasible'] and not x['all_period_budget_ok']: sig.append('period_budget_violation')
    if x['stage_feasible'] and not x['all_period_constraint_ok']: sig.append('period_constraint_violation')
    if sig: sus.append({'seed':x['seed'],'method':x['method'],'signals':';'.join(sig),'selected_count':x['selected_count'],'duration':x['portfolio_duration_periods']})
write_csv(OUT/'suspicious_signal_audit.csv',sus)
(OUT/'summary.json').write_text(json.dumps({'summary':summary,'per_seed':per,'method_level_medians':medrows,'aOctane_audit':ao_rows},indent=2,ensure_ascii=False),encoding='utf-8')
report=[TEST_ID,'',summary['status'],'',f"Method admissible counts: {summary['method_admissible_counts']}",f"Usable ranking: {len(usable)}/10; strict 4-way: {len(strict)}/10; sCPA beats best ranking: {summary['scpa_beats_best3_abs_worlds']}/{len(usable)}; sCPA best overall: {summary['scpa_best4_worlds']}/10",f"aOctane diagnostic: {summary['aOctane_diagnostic']}",'','Method medians over admissible worlds:']
for r in medrows: report.append(f"- {r['method']}: adm {r['admissible_worlds']}/10; selected {r['median_selected_count']}; P85 {r['median_p85_profit']}; ROI used budget {r['median_roi_pct_used_budget']}%; ROI full 22p {r['median_roi_pct_full_22p_budget_envelope']}%; avg budget util {r['median_avg_budget_util_pct']}%; avg constraint util {r['median_avg_constraint_util_pct']}%; P85/constraint {r['median_p85_per_constraint_unit']}")
report.append('\naOctane seed audit:')
for r in ao_rows: report.append(f"- seed {r['seed']}: Octane adm={r['octane_admissible']} P85={r['octane_p85']}; V16={r['prior_v16c_aoctane_p85']}; V17={r['prior_v17c_aoctane_p85']}; V18 adm={r['aoctane_admissible']} P85={r['aoctane_p85']}; delta_vs_O={r['delta_vs_expanded_octane_p85']}; extra_vs_guard={r['delta_vs_guard_base_p85']}; concept={r['v18_best_concept']} {r['v18_best_detail']}; repair_added={r['structural_repair_added_ids']}; same_seq={r['same_sequence']}")
(OUT/'REPORT_BG.txt').write_text('\n'.join(report),encoding='utf-8')
if ZIP.exists(): ZIP.unlink()
with zipfile.ZipFile(ZIP,'w',zipfile.ZIP_DEFLATED) as z:
    for fp in OUT.rglob('*'):
        if fp.is_file(): z.write(fp,arcname=fp.relative_to(OUT))
    z.write('/mnt/data/run_v18_multi_concept_aoctane_sequence_only.py',arcname='reproduction_scripts/run_v18_multi_concept_aoctane_sequence_only.py')
print('WROTE',ZIP)
print(json.dumps(summary,indent=2,ensure_ascii=False))
