# Portfolio Waste Discovery Lab — Reproduction Pack

**Current date of package currency:** 2026-06-11

This package is a reproducible portfolio waste-discovery and method-comparison laboratory for portfolio allocation and reallocation decisions. It compares four portfolio methods in a controlled context and measures the economic value left unrealized by weaker portfolio selection, sequencing, staging, or timing.

## What it is
A handoff-grade research package that lets another AI agent inspect the current validated baseline, reproduce/audit it, run a continuation smoke test, and continue experiments without the original chat.

## What it is not
It is not a detailed project scheduling product and it does not compete with detailed scheduling tools such as Spider Project. The current benchmark uses a master portfolio macro-schedule with Drum-Buffer-Rope concepts as the staging context. The lab itself is a method-comparison and waste-discovery framework, not a DBR method.

## First commands
```bash
python 06_AUDIT/tools/run_continuation_smoke_test.py
python 06_AUDIT/tools/audit_baseline_and_package.py
bash 06_AUDIT/tools/run_full_baseline_reproduction.sh
python 06_AUDIT/tools/audit_baseline_and_package.py
```


## Windows-safe v4 note

This v4 archive stores the current engine as `02_ENGINE_AND_REPRODUCTION/engine_v28_bundle.zip` instead of expanding the full engine tree in the top-level ZIP. This avoids long internal file paths that may prevent some Windows tools from opening or extracting the package. The reproduction wrapper unpacks the engine automatically; it can also be unpacked manually with:

```bash
python 02_ENGINE_AND_REPRODUCTION/unpack_engine_bundle.py
```
