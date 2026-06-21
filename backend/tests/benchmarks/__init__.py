"""Benchmark acceptance harnesses for the Clannon V1 attention threshold.

Each module here exercises EXISTING capability against one benchmark's pass
requirements (docs/benchmarks/CLANNON_V1_ATTENTION_THRESHOLD.md) and emits a
structured PASS / PARTIAL / FAIL report via the shared `report` helper. These
harnesses MEASURE; they never implement capability and never fake a pass — an
unmet requirement is reported honestly as PARTIAL or NOT-YET.

All harnesses are hermetic: fake/stubbed external engines (ClamAV, YARA, Presidio)
and a faithful in-process LLM double stand in for anything that would otherwise
need the network or a paid provider key, so the suite runs under plain `pytest`.
"""
