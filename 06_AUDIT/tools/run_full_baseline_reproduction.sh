#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
LOG="$ROOT/06_AUDIT/logs/full_baseline_reproduction.log"
mkdir -p "$ROOT/06_AUDIT/logs" /mnt/data
cp -f "$ROOT"/02_ENGINE_AND_REPRODUCTION/scripts/*.py /mnt/data/
cp -f "$ROOT"/02_ENGINE_AND_REPRODUCTION/source_zips/*.zip /mnt/data/ || true
cp -f "$ROOT"/05_ARCHIVE_AND_TRACEABILITY/prior_key_result_packages/*.zip /mnt/data/ || true
rm -rf /mnt/data/r7_s1p18_v1
mkdir -p /mnt/data/r7_s1p18_v1
python - <<'PYINNER'
from pathlib import Path
import zipfile, shutil
src=Path('/mnt/data/POL_R7_asymmetric_paired_4method_MC1000_s1p18bc0p20_TARGETED_v1.zip')
out=Path('/mnt/data/r7_s1p18_v1')
if not src.exists(): raise SystemExit('Missing source zip: '+str(src))
with zipfile.ZipFile(src) as z: z.extractall(out)
for name in ['R7_STRUCTURAL_SOFT_V16C_FOCUSED_DETLOCAL_AOCTANE_SEQUENCE_ONLY_MC1000_v1.zip','R7_STRUCTURAL_SOFT_V17C_FULL_U_LOCAL_AOCTANE_SEQUENCE_ONLY_MC1000_v1.zip']:
    zpath=Path('/mnt/data')/name; outdir=Path('/mnt/data')/name[:-4]
    if zpath.exists():
        if outdir.exists(): shutil.rmtree(outdir)
        outdir.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(zpath) as z: z.extractall(outdir)
PYINNER
# Unpack the engine bundle on demand. The package stores the engine as a nested ZIP
# to avoid very long paths in the top-level archive on Windows.
if [ ! -d "$ROOT/02_ENGINE_AND_REPRODUCTION/engine_current_v28/engine_v28/scripts" ]; then
  python "$ROOT/02_ENGINE_AND_REPRODUCTION/unpack_engine_bundle.py"
fi
ENGINE="$ROOT/02_ENGINE_AND_REPRODUCTION/engine_current_v28/engine_v28/scripts"
PYTHONPATH="$ENGINE" python /mnt/data/run_v18_multi_concept_aoctane_sequence_only.py | tee "$LOG"
echo "Full baseline reproduction log written to $LOG"
