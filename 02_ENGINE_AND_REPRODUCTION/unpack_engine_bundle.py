#!/usr/bin/env python3
from pathlib import Path
import zipfile, shutil
root = Path(__file__).resolve().parent
bundle = root / "engine_v28_bundle.zip"
out = root / "engine_current_v28"
if not bundle.exists():
    raise SystemExit(f"Missing {bundle}")
if out.exists():
    shutil.rmtree(out)
out.mkdir(parents=True, exist_ok=True)
with zipfile.ZipFile(bundle) as z:
    z.extractall(out)
print(f"Engine unpacked to {out / 'engine_v28'}")
