#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
import random
import sys
import time
from dataclasses import asdict
from pathlib import Path
from statistics import mean, median
from typing import Dict, Iterable, List, Sequence, Tuple, Set, Optional


def load_modules(engine_root: str):
    scripts = Path(engine_root) / "scripts"
    if not scripts.exists():
        raise FileNotFoundError(f"Cannot find scripts folder under {engine_root}")
    sys.path.insert(0, str(scripts))
    import pol_step1_reference_generators as gens
    import pol_step1_reference_common as common
    eng = common.eng
    return eng, gens, common


def det(x):
    if hasattr(x, 'deterministic'):
        return float(x.deterministic())
    return float(x)


def budget_total(eng, p):
    d = p.deterministic_duration()
    prof = eng._derive_budget_profile(p, d)
    return sum(det(v) for v in prof)


def constraint_total(eng, p):
    d = p.deterministic_duration()
    prof = eng._normalize_profile(p.constraint_usage_profile, d)
    return sum(det(v) for v in prof)


def constraint_peak(eng, p):
    d = p.deterministic_duration()
    vals = [det(v) for v in eng._normalize_profile(p.constraint_usage_profile, d)]
    return max(vals or [0.0])


def time_pressure(p):
    cot = p.cost_of_time_profile
    if cot.profile_type.value == 'Linear':
        return abs(det(cot.linear_delta_per_period)) / max(abs(p.deterministic_base_profit()), 1e-9)
    if cot.profile_type.value == 'Cliff':
        return 1.0
    return 0.0


def project_maps(projects):
    return {p.project_id: p for p in projects}


def dependency_closure_ids(eng, ids: Iterable[str], pmap: Dict[str, object]) -> List[str]:
    # preserve a deterministic order from the project map insertion order
    selected = set(ids)
    changed = True
    while changed:
        changed = False
        for pid in list(selected):
            for dep in pmap[pid].structural_dependencies:
                if dep not in selected:
                    selected.add(dep)
                    changed = True
    return [pid for pid in pmap if pid in selected]


def structural_cleanup_ids(ids: Iterable[str], pmap: Dict[str, object]) -> List[str]:
    selected = set(ids)
    changed = True
    while changed:
        changed = False
        for pid in list(selected):
            if not set(pmap[pid].structural_dependencies).issubset(selected):
                selected.remove(pid)
                changed = True
    return [pid for pid in pmap if pid in selected]


def sequence_by_order(eng, selected_ids: Iterable[str], pmap: Dict[str, object], order: Sequence[str]):
    s = set(selected_ids)
    seq = [pmap[pid] for pid in order if pid in s]
    # add any missing selected ids at the end in map order
    seq += [p for pid, p in pmap.items() if pid in s and pid not in set(order)]
    return eng._dependency_aware_stable_order(seq)


def make_orders(eng, projects, method_sequences: Dict[str, List[str]]) -> Dict[str, List[str]]:
    pids = [p.project_id for p in projects]
    orders = {}
    orders['profit_desc'] = [p.project_id for p in sorted(projects, key=lambda p: (-p.deterministic_base_profit(), p.project_id))]
    orders['pcucu_desc'] = [p.project_id for p in sorted(projects, key=lambda p: (-eng.octane_score(p), constraint_peak(eng, p), p.project_id))]
    orders['low_budget'] = [p.project_id for p in sorted(projects, key=lambda p: (budget_total(eng, p), -p.deterministic_base_profit(), p.project_id))]
    orders['low_constraint'] = [p.project_id for p in sorted(projects, key=lambda p: (constraint_total(eng, p), -p.deterministic_base_profit(), p.project_id))]
    orders['time_pressure'] = [p.project_id for p in sorted(projects, key=lambda p: (-time_pressure(p), -p.deterministic_base_profit(), p.project_id))]
    orders['blend_profit_pcucu'] = [p.project_id for p in sorted(projects, key=lambda p: (-(0.5 * norm_profit(p, projects) + 0.5 * norm_pcucu(eng, p, projects)), p.project_id))]
    for m, seq in method_sequences.items():
        if seq:
            orders[f'{m}_sequence'] = seq
    return orders


def norm_profit(p, projects):
    vals = [x.deterministic_base_profit() for x in projects]
    lo, hi = min(vals), max(vals)
    return (p.deterministic_base_profit() - lo) / max(hi - lo, 1e-9)


def norm_pcucu(eng, p, projects):
    vals = [eng.octane_score(x) for x in projects]
    lo, hi = min(vals), max(vals)
    return (eng.octane_score(p) - lo) / max(hi - lo, 1e-9)


def build_candidate_pool(eng, projects, method_selected: Dict[str, List[str]], max_pool: int) -> List[str]:
    pmap = project_maps(projects)
    pool: Set[str] = set()
    for ids in method_selected.values():
        pool.update(ids)
    lists = [
        sorted(projects, key=lambda p: (-p.deterministic_base_profit(), p.project_id)),
        sorted(projects, key=lambda p: (-eng.octane_score(p), constraint_peak(eng, p), p.project_id)),
        sorted(projects, key=lambda p: (budget_total(eng, p), -p.deterministic_base_profit(), p.project_id)),
        sorted(projects, key=lambda p: (constraint_total(eng, p), -p.deterministic_base_profit(), p.project_id)),
        sorted(projects, key=lambda p: (-time_pressure(p), -p.deterministic_base_profit(), p.project_id)),
    ]
    k = max(6, min(12, max_pool // 2))
    for lst in lists:
        pool.update(p.project_id for p in lst[:k])
    # Add dependencies and synergy-related projects for pool integrity.
    pool = set(dependency_closure_ids(eng, pool, pmap))
    for p in projects:
        if p.project_id in pool:
            for syn in p.synergies:
                pool.add(syn.target_project_id)
                pool.update(syn.related_project_ids)
    pool = set(dependency_closure_ids(eng, pool, pmap))
    # If too large, rank by broad usefulness but preserve selected method IDs and deps.
    must = set()
    for ids in method_selected.values():
        must.update(ids)
    must = set(dependency_closure_ids(eng, must, pmap))
    if len(pool) > max_pool:
        def usefulness(pid):
            p = pmap[pid]
            return 1.25 * norm_profit(p, projects) + 1.25 * norm_pcucu(eng, p, projects) + 0.5 * time_pressure(p) - 0.25 * constraint_total(eng, p) / max(1e-9, max(constraint_total(eng, x) for x in projects))
        optional = sorted([pid for pid in pool if pid not in must], key=lambda pid: (-usefulness(pid), pid))
        keep = list(must)
        for pid in optional:
            if len(set(keep)) >= max_pool:
                break
            keep.append(pid)
        pool = set(dependency_closure_ids(eng, keep, pmap))
        # If deps pushed over max, leave it; correctness beats exact size.
    return [pid for pid in pmap if pid in pool]


def deterministic_profit(eng, selected, stage):
    if not selected or not stage.feasible:
        return 0.0
    return eng._profit_with_cost_and_synergy(selected, stage)


def slack_score(stage):
    if not stage.feasible:
        return -1e9
    return len(stage.records)


def evaluate_candidate_sequences(eng, portfolio, pmap, ids, orders, scenarios, max_sequences=10, do_local_swap=True):
    ids = list(dict.fromkeys(ids))
    selected = [pmap[pid] for pid in ids]
    best = None
    tried = 0
    sequence_variants = []
    for name, order in orders.items():
        seq = sequence_by_order(eng, ids, pmap, order)
        key = tuple(p.project_id for p in seq)
        if key not in [k for k, _, _ in sequence_variants]:
            sequence_variants.append((key, name, seq))
    for key, name, seq in sequence_variants[:max_sequences]:
        stage = eng.stage_sequence(seq, portfolio)
        if not stage.feasible:
            continue
        br, cr, adm, p85, profits = eng.evaluate_stochastic_from_scenarios(portfolio, selected, seq, subset_scenarios(eng, scenarios, ids), optimistic_prefilter=False)
        cand = {
            'sequence_name': name,
            'selected_ids': [p.project_id for p in selected],
            'sequence_ids': [p.project_id for p in seq],
            'stage_feasible': stage.feasible,
            'budget_feasibility_rate': br,
            'constraint_feasibility_rate': cr,
            'admissible': bool(adm),
            'p85_profit': p85,
            'evaluated_profit': p85,
            'deterministic_profit': deterministic_profit(eng, selected, stage),
            'selected_count': len(selected),
        }
        tried += 1
        if best is None or candidate_better(cand, best):
            best = cand
        if do_local_swap and len(selected) <= 30:
            subsc = subset_scenarios(eng, scenarios, ids)
            loc_seq, loc_stage, _ = eng.improve_aoctane_sequence(selected, seq, portfolio, scenarios=subsc)
            loc_key = tuple(p.project_id for p in loc_seq)
            if loc_stage.feasible and loc_key != key:
                br, cr, adm, p85, profits = eng.evaluate_stochastic_from_scenarios(portfolio, selected, loc_seq, subsc, optimistic_prefilter=False)
                loc = {
                    'sequence_name': name + '+local_swap',
                    'selected_ids': [p.project_id for p in selected],
                    'sequence_ids': [p.project_id for p in loc_seq],
                    'stage_feasible': loc_stage.feasible,
                    'budget_feasibility_rate': br,
                    'constraint_feasibility_rate': cr,
                    'admissible': bool(adm),
                    'p85_profit': p85,
                    'evaluated_profit': p85,
                    'deterministic_profit': deterministic_profit(eng, selected, loc_stage),
                    'selected_count': len(selected),
                }
                tried += 1
                if best is None or candidate_better(loc, best):
                    best = loc
    return best, tried


def subset_scenarios(eng, scenarios, ids):
    ids = set(ids)
    return [eng.MonteCarloScenario(
        project_vectors={pid: sc.project_vectors[pid] for pid in ids},
        linear_cot_deltas={pid: sc.linear_cot_deltas[pid] for pid in ids if pid in sc.linear_cot_deltas},
        piecewise_cot_values={pid: sc.piecewise_cot_values[pid] for pid in ids if pid in sc.piecewise_cot_values},
        synergy_values={(pid, i): v for (pid, i), v in sc.synergy_values.items() if pid in ids},
    ) for sc in scenarios]


def candidate_better(a, b):
    # Prefer admissible; then higher evaluated profit; then deterministic profit.
    if bool(a.get('admissible')) != bool(b.get('admissible')):
        return bool(a.get('admissible'))
    if abs(a.get('evaluated_profit', 0) - b.get('evaluated_profit', 0)) > 1e-9:
        return a.get('evaluated_profit', 0) > b.get('evaluated_profit', 0)
    return a.get('deterministic_profit', 0) > b.get('deterministic_profit', 0)


def score_partial(eng, portfolio, pmap, ids, order):
    selected = [pmap[pid] for pid in ids]
    seq = sequence_by_order(eng, ids, pmap, order)
    stage = eng.stage_sequence(seq, portfolio)
    if not stage.feasible:
        return None
    det_profit = deterministic_profit(eng, selected, stage)
    # Penalize large resource load gently, but primarily use deterministic profit.
    total_b = sum(budget_total(eng, pmap[pid]) for pid in ids)
    total_c = sum(constraint_total(eng, pmap[pid]) for pid in ids)
    return det_profit - 0.001 * total_b - 0.01 * total_c


def scpa_lite_search(eng, portfolio, projects, baseline_world, world_seed, max_pool=24, beam_width=150, max_eval_candidates=250, target_uplift=0.05):
    t0 = time.time()
    pmap = project_maps(projects)
    method_selected = {m: baseline_world['methods'][m].get('selected_ids', []) for m in ['MSA', 'Octane', 'aOctane']}
    method_sequences = {m: baseline_world['methods'][m].get('sequence_ids', []) for m in ['MSA', 'Octane', 'aOctane']}
    pool_ids = build_candidate_pool(eng, projects, method_selected, max_pool=max_pool)
    pool_projects = [pmap[pid] for pid in pool_ids]
    orders = make_orders(eng, pool_projects, method_sequences)
    scenarios = eng.generate_mc_scenarios(portfolio, projects, world_seed * 1000 + 424242)

    # Best of the three ranking methods.
    admissible_methods = []
    for m in ['MSA', 'Octane', 'aOctane']:
        md = baseline_world['methods'][m]
        if md.get('admissible') and md.get('stage_feasible') and md.get('selected_count', len(md.get('selected_ids', []))) > 0:
            admissible_methods.append((m, md.get('evaluated_profit', md.get('p85_profit', 0.0))))
    best3_method, best3_profit = max(admissible_methods, key=lambda x: x[1]) if admissible_methods else (None, None)

    evaluated = []
    seen = set()

    def add_subset(ids, source):
        ids2 = tuple(dependency_closure_ids(eng, ids, pmap))
        if not ids2 or ids2 in seen:
            return
        seen.add(ids2)
        # first score using profit desc order for deterministic feasible beam support
        evaluated.append((list(ids2), source))

    # Add method selected sets and prefixes from every order.
    for m, ids in method_selected.items():
        add_subset(ids, f'{m}_selected')
    for oname, order in orders.items():
        current = []
        for pid in order:
            if pid not in pool_ids:
                continue
            current.append(pid)
            if len(current) >= 2:
                add_subset(current, f'prefix_{oname}_{len(current)}')

    # Beam search over pool using several orderings; keep deterministic-stageable partials.
    for oname, order in list(orders.items())[:6]:
        candidates = [([], 0.0)]
        for pid in [x for x in order if x in pool_ids]:
            new_states = candidates[:]
            for ids, _score in candidates:
                trial = dependency_closure_ids(eng, ids + [pid], pmap)
                key = tuple(trial)
                seq = sequence_by_order(eng, trial, pmap, order)
                stage = eng.stage_sequence(seq, portfolio)
                if stage.feasible:
                    sc = score_partial(eng, portfolio, pmap, trial, order)
                    if sc is not None:
                        new_states.append((trial, sc))
            # Dedupe and trim.
            tmp = {}
            for ids, sc in new_states:
                tmp[tuple(ids)] = max(sc, tmp.get(tuple(ids), -1e18))
            candidates = sorted([(list(k), v) for k, v in tmp.items()], key=lambda x: -x[1])[:beam_width]
        for ids, sc in candidates[:beam_width]:
            if len(ids) >= 2:
                add_subset(ids, f'beam_{oname}')

    # Rank candidate subsets by quick deterministic score before stochastic evaluation.
    scored = []
    for ids, source in evaluated:
        best_det = None
        for oname, order in orders.items():
            sc = score_partial(eng, portfolio, pmap, ids, order)
            if sc is not None:
                best_det = sc if best_det is None else max(best_det, sc)
        if best_det is not None:
            scored.append((ids, source, best_det))
    scored.sort(key=lambda x: -x[2])

    best = None
    tried_sequences = 0
    tried_subsets = 0
    target_hit = False
    for ids, source, detscore in scored[:max_eval_candidates]:
        tried_subsets += 1
        cand, nseq = evaluate_candidate_sequences(eng, portfolio, pmap, ids, orders, scenarios, max_sequences=10, do_local_swap=True)
        tried_sequences += nseq
        if cand:
            cand['source'] = source
            cand['deterministic_search_score'] = detscore
            if best is None or candidate_better(cand, best):
                best = cand
                if best3_profit and best.get('admissible'):
                    uplift = (best['evaluated_profit'] - best3_profit) / best3_profit
                    if uplift >= target_uplift:
                        target_hit = True
                        # Stop early once a strong target has been found.
                        break

    if best is None:
        best = {'admissible': False, 'selected_ids': [], 'sequence_ids': [], 'evaluated_profit': 0.0, 'p85_profit': 0.0}
    if best3_profit and best.get('admissible'):
        best['uplift_vs_best3_pct'] = (best['evaluated_profit'] - best3_profit) / best3_profit * 100.0
        best['meets_5pct_target'] = best['uplift_vs_best3_pct'] >= 5.0
    else:
        best['uplift_vs_best3_pct'] = None
        best['meets_5pct_target'] = False

    return {
        'portfolio_id': portfolio.portfolio_id,
        'world_seed': world_seed,
        'pool_size': len(pool_ids),
        'pool_ids': pool_ids,
        'candidate_subsets_generated': len(evaluated),
        'candidate_subsets_deterministic_feasible': len(scored),
        'candidate_subsets_stochastic_evaluated': tried_subsets,
        'candidate_sequences_stochastic_evaluated': tried_sequences,
        'runtime_seconds': time.time() - t0,
        'best3_method': best3_method,
        'best3_profit': best3_profit,
        'best3_admissible_methods': [{'method': m, 'profit': p} for m, p in admissible_methods],
        'target_uplift_pct': target_uplift * 100.0,
        'target_hit': target_hit,
        'scpa_lite': best,
    }


def serialize_baseline(eng, world):
    return eng.serialize_world_result(world)


def run_one(args):
    eng, gens, common = load_modules(args.engine_root)
    if args.regime not in gens.GENS:
        raise ValueError(f"Unknown regime {args.regime}; available: {sorted(gens.GENS)}")
    gen = gens.GENS[args.regime]
    portfolio, projects = gen(args.seed, args.mc)
    baseline_world_obj = eng.run_world(portfolio, projects, world_seed=args.seed * 1000)
    baseline = serialize_baseline(eng, baseline_world_obj)
    res = scpa_lite_search(
        eng, portfolio, projects, baseline,
        world_seed=args.seed,
        max_pool=args.max_pool,
        beam_width=args.beam_width,
        max_eval_candidates=args.max_eval_candidates,
        target_uplift=args.target_uplift / 100.0,
    )
    out = {
        'engine_version': eng.ENGINE_VERSION,
        'regime': args.regime,
        'seed': args.seed,
        'mc': args.mc,
        'project_count': len(projects),
        'baseline': {
            'accepted_for_comparative_analysis': baseline.get('accepted_for_comparative_analysis'),
            'methods': {
                m: {
                    'selected_count': baseline['methods'][m].get('selected_count', len(baseline['methods'][m].get('selected_ids', []))),
                    'stage_feasible': baseline['methods'][m].get('stage_feasible'),
                    'admissible': baseline['methods'][m].get('admissible'),
                    'evaluated_profit': baseline['methods'][m].get('evaluated_profit', baseline['methods'][m].get('p85_profit')),
                    'budget_feasibility_rate': baseline['methods'][m].get('budget_feasibility_rate'),
                    'constraint_feasibility_rate': baseline['methods'][m].get('constraint_feasibility_rate'),
                } for m in ['MSA', 'Octane', 'aOctane']
            },
        },
        'scpa_lite_result': res,
    }
    return out


def main():
    ap = argparse.ArgumentParser(description='Experimental POL sCPA-lite runner for Hypothesis 1 observed benchmark dominance.')
    ap.add_argument('--engine-root', required=True, help='Path to unpacked POL Step 1 engine package root')
    ap.add_argument('--regime', required=True)
    ap.add_argument('--seed', type=int, required=True)
    ap.add_argument('--mc', type=int, default=100)
    ap.add_argument('--max-pool', type=int, default=24)
    ap.add_argument('--beam-width', type=int, default=150)
    ap.add_argument('--max-eval-candidates', type=int, default=250)
    ap.add_argument('--target-uplift', type=float, default=5.0, help='Target uplift over Best3 in percent')
    ap.add_argument('--out', required=True)
    args = ap.parse_args()
    result = run_one(args)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding='utf-8')
    print(json.dumps({
        'regime': result['regime'],
        'seed': result['seed'],
        'project_count': result['project_count'],
        'best3_method': result['scpa_lite_result']['best3_method'],
        'best3_profit': result['scpa_lite_result']['best3_profit'],
        'scpa_admissible': result['scpa_lite_result']['scpa_lite'].get('admissible'),
        'scpa_profit': result['scpa_lite_result']['scpa_lite'].get('evaluated_profit'),
        'uplift_vs_best3_pct': result['scpa_lite_result']['scpa_lite'].get('uplift_vs_best3_pct'),
        'target_hit': result['scpa_lite_result']['target_hit'],
        'runtime_seconds': result['scpa_lite_result']['runtime_seconds'],
        'out': str(out),
    }, indent=2, ensure_ascii=False))


if __name__ == '__main__':
    main()
