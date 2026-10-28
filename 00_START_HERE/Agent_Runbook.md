# Agent Runbook

1. Read the `00_START_HERE` files.
2. Read `01_METHOD_GUIDE/Method_Comparison_Guide.md` and `Portfolio_Waste_Metrics.md`.
3. Run the continuation smoke test and baseline audit.
4. Run the full baseline reproduction wrapper if the environment supports `/mnt/data`.
5. Do not start new tests until the current baseline is reproduced or any deviations are explained.

Continuation rules: use the same worlds and common MC scenarios; preserve aOctane guard; report waste per world; do not overwrite the baseline; always generate selected projects, sequences, schedules, utilization, WIP, ROI, reserve-adjusted ROI, waste, and suspicious-signal audit.
