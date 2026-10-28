# Windows-safe repack note — v4

The previous v3 package passed ZIP integrity testing, but it contained many long internal paths inside the extracted engine tree. Some desktop tools, especially on Windows, may fail to open or extract such archives.

This v4 package keeps the content and license update, but stores the engine tree as `02_ENGINE_AND_REPRODUCTION/engine_v28_bundle.zip` with a short internal root. The reproduction wrapper now unpacks the engine bundle automatically before running the V18 baseline reproduction.

Status: package re-zipped, integrity tested, clean-extraction tested, and package audit rerun.
