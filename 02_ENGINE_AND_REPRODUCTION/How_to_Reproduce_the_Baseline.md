# How to Reproduce the Baseline

Run from package root:

```bash
bash 06_AUDIT/tools/run_full_baseline_reproduction.sh
```

The wrapper recreates the legacy `/mnt/data` runtime, extracts the source R7 package and required V16C/V17C packages, sets `PYTHONPATH` to engine v28 scripts, and runs the V18 MC1000 reproduction script.
