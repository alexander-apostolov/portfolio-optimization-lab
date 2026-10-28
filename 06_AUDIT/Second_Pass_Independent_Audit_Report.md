# Second-Pass Independent Audit Report

**Package:** Portfolio Waste Discovery Lab — Reproduction Pack  
**Audit date:** 2026-06-11  
**Audit status:** READY FOR HANDOFF AFTER SECOND-PASS CHECK  
**Critical issues:** 0  
**Blocking issues:** 0

## Purpose of this second-pass audit

The first audit checked package completeness and baseline consistency. This second-pass audit checks whether the package can actually operate as an autonomous handoff package: clean extraction, package-root audit, full baseline reproduction, content-level comparison of reproduced outputs, continuation smoke testing, and portability caveats.

## Audit gates and results

| Gate | Result | Evidence |
|---|---:|---|
| Clean extraction into a new directory | PASS | Package extracted under a clean `pwdl_clean_audit` directory. |
| Package-root audit script | PASS | `python 06_AUDIT/tools/audit_baseline_and_package.py` returned `READY FOR HANDOFF`, `critical_issues = 0`. |
| Full baseline reproduction wrapper | PASS | `bash 06_AUDIT/tools/run_full_baseline_reproduction.sh` completed successfully. |
| Reproduced V18 output content match | PASS | The reproduced V18 ZIP and included baseline V18 ZIP have identical file lists and identical per-file SHA256 hashes. The outer ZIP hash differs only because ZIP metadata/timestamps differ. |
| Continuation smoke test | PASS | `python 06_AUDIT/tools/run_continuation_smoke_test.py` completed and produced a non-overwriting continuation result with `red_flags = 0`. |
| Re-run audit after smoke test | PASS | Audit script still returned `READY FOR HANDOFF`, `critical_issues = 0`. |
| Baseline preservation | PASS | Continuation smoke test writes under `04_CONTINUATION/continuation_runs/` and does not overwrite current baseline files. |
| Red-flag audit | PASS | Baseline suspicious-signal audit reports no critical/warning signals. |
| Method invariant audit | PASS | No aOctane-below-Octane violation; no structural dependency violation; no period-level budget/constraint violation. |
| Waste recomputation | PASS | Waste is recomputed from raw per-seed values and stored in `06_AUDIT/results/waste_recomputed_from_raw.csv`. |

## Full reproduction headline metrics checked

The full reproduction wrapper regenerated the V18 baseline with the expected headline metrics:

| Metric | Expected / reproduced |
|---|---:|
| MSA admissible | 9/10 |
| Octane admissible | 7/10 |
| aOctane admissible | 10/10 |
| sCPA-lite admissible | 10/10 |
| Usable ranking comparison | 10/10 |
| Strict 4-way comparison | 6/10 |
| sCPA-lite best overall | 10/10 |
| sCPA-lite beats best ranking-family method | 10/10 |

## Method-level medians checked

| Method | Median P85 | ROI on used budget | ROI on full 22-period budget | Avg budget utilization | Avg constraint utilization |
|---|---:|---:|---:|---:|---:|
| MSA | -97.36 | -0.62% | -0.48% | 77.47% | 70.15% |
| Octane | 937.70 | 5.79% | 4.58% | 77.82% | 70.17% |
| aOctane | 1128.19 | 8.42% | 5.51% | 77.36% | 68.78% |
| sCPA-lite | 4162.97 | 28.23% | 20.33% | 80.25% | 68.89% |

## Portability note

The current legacy reproduction scripts were originally produced in a sandbox workflow and contain `/mnt/data` runtime paths. This is documented. The package includes a wrapper, `06_AUDIT/tools/run_full_baseline_reproduction.sh`, that reconstructs the required `/mnt/data` runtime and successfully reproduces the baseline in this environment. Package-root audits and raw-to-summary checks are relative-path based.

For non-sandbox environments, use one of these approaches:

1. Create or mount `/mnt/data` before running the legacy full reproduction wrapper; or
2. Adapt the legacy runner paths to a local temporary runtime while keeping all source files unchanged; or
3. Use the package-root raw-to-summary audit and included baseline outputs for validation if full MC1000 rerun is not required.

This is a documented limitation, not a blocking issue for the present handoff package.

## Final second-pass verdict

The package is ready for handoff as an autonomous research/reproduction package. It contains the current V18 baseline, supporting raw data, method explanations, waste definitions, audit tools, reproduction wrappers, and continuation smoke-test capability.

**Final status:** READY FOR HANDOFF  
**Critical issues:** 0  
**Blocking issues:** 0  
**Known limitations:** documented
