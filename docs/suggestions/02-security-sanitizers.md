# security/ (sanitizers + filter)

This is the domain with the most raw duplication. **Important framing:** these findings
are about *code shape*, not about whether the sanitization is correct or strong — the
security behaviour is out of scope here. The risk these create is the maintenance kind: a
fix or hardening applied to one worker silently not applied to the others.

The five modality workers (`text` 230, `image` 170, `pdf` 317, `audio` 350, `video` 354)
were clearly written by copy-paste, and have already started to drift.

---

<a id="s1"></a>
## S1 — `_highest_threat` and `_run_worker` are copy-pasted across 4 workers

- **Severity:** High
- **Type:** duplication
- **Locations:** `_highest_threat` at `workers/pdf.py:245`, `workers/text.py:164`,
  `workers/audio.py:264`, `workers/video.py:263`; the per-worker `_run_worker` at
  `workers/pdf.py:260`, `workers/text.py:179`, `workers/audio.py:279`, `workers/video.py:278`.

**Problem.** Four near-identical copies of "reduce a list of worker results to the highest
threat level" and four copies of "run one sub-worker, wrap its errors into a result." The
only differences are the per-modality result *type* (`PdfWorkerResult` vs
`TextWorkerResult` …). The shape is otherwise the same.

**Why it hurts.** Two concrete costs. (1) Any change to threat-reduction or error-wrapping
must be made four times. (2) **It has already drifted** — the workers' result types and
worker signatures diverge in small ways, which is exactly how copy-pasted code rots. A
hardening applied to `pdf._run_worker` won't reach `audio._run_worker` unless someone
remembers it exists in four places.

> Naming hazard: `_run_worker` *also* exists in `runner.py:44`, but means something
> different there (a semaphore-bounded timeout wrapper around a whole modality scan). Same
> name, two unrelated jobs — confusing when grepping.

**Suggestion.** Add `workers/_base.py` with a generic `highest_threat(results)` and a
`run_subworker(worker, payload)` parameterised by the result type (a `Protocol` or a small
generic dataclass with `.threat_level`). The five workers import these instead of
redefining them. Rename `runner.py`'s `_run_worker` to `_bounded_scan` to end the name
clash.

---

<a id="s2"></a>
## S2 — `audio.py` and `video.py` are ~60% identical

- **Severity:** High
- **Type:** duplication
- **Locations:** `workers/audio.py` (350) and `workers/video.py` (354). Normalising the
  `audio`↔`video` naming, only ~138 of ~350 lines differ — the rest is identical
  scaffolding (the `_probe_worker` / `_metadata_worker` / `_sanitize_worker` triad, the
  ffmpeg invocation pattern, temp-file handling, the `scan()` orchestration at
  `audio.py:308` / `video.py:307`).

**Problem.** Two files that are the same ffmpeg-backed media sanitizer with different codec
flags. The shared 60% includes the most security-relevant parts (probe, metadata strip,
re-encode, temp-file lifecycle).

**Why it hurts.** A correctness or hardening fix to the ffmpeg handling — the part most
likely to need future fixes — has to be mirrored by hand between two 350-line files, and
the 60% overlap makes it easy to "fix audio, forget video." This is the highest
duplication-density in the backend.

**Suggestion.** Extract an `workers/_ffmpeg_media.py` base that owns probe → strip
metadata → re-encode → temp-file lifecycle → result assembly, parameterised by the
codec/format specifics. `audio.py` and `video.py` shrink to the handful of lines that are
genuinely modality-specific (the ~138 differing lines, most of which are flags and MIME
handling). Pairs with the S1 base extraction.

---

<a id="s3"></a>
## S3 — Modality→worker binding is a hardcoded `if` ladder

- **Severity:** Medium
- **Type:** scattered logic / coupling
- **Locations:** `security/sanitizers/runner.py:90-94`

```python
if "text"  in modalities: tasks.append(_run_worker(text.scan(raw)))
if "image" in modalities: tasks.append(_run_worker(image.scan(raw)))
if "pdf"   in modalities: tasks.append(_run_worker(pdf.scan(raw)))
if "video" in modalities: tasks.append(_run_worker(video.scan(raw)))
if "audio" in modalities: tasks.append(_run_worker(audio.scan(raw)))
```

**Problem.** The mapping from a modality string to its worker is a five-line `if` ladder.
To add a new modality worker you edit this ladder *and* create the worker file — and the
modality strings here are stringly-typed (`"text"`, …) with no link to the `Modality` enum
in `foundation`.

**Why it hurts.** Adding a modality is a two-place edit with no compiler help, and the
string literals can drift from the `Modality` enum. It also blocks any "list the
sanitizers we run" introspection (e.g. for the UI or logging) because there's no data
structure to read — only control flow.

**Suggestion.** Replace the ladder with one registry the runner iterates:

```python
MODALITY_WORKERS = {
    Modality.TEXT:  text.scan,
    Modality.IMAGE: image.scan,
    Modality.PDF:   pdf.scan,
    Modality.AUDIO: audio.scan,
    Modality.VIDEO: video.scan,
}
tasks = [_bounded_scan(scan(raw)) for m, scan in MODALITY_WORKERS.items() if m in modalities]
```

Now adding a modality is: write the worker, add one map entry. The runner doesn't change,
and the map is readable as data.

---

## Domain summary

The workers are a textbook copy-paste cluster: `_highest_threat` and `_run_worker` exist
four times each with confirmed drift (S1), and `audio.py`/`video.py` are ~60% the same
ffmpeg sanitizer (S2) — so the parts most likely to need future hardening are exactly the
parts duplicated most. The modality dispatch (S3) is a stringly-typed `if` ladder with no
link to the `Modality` enum. All three are fixed by the same move: a small
`workers/_base.py` + `_ffmpeg_media.py` for the shared scaffolding, and a single
`MODALITY_WORKERS` map the runner iterates. After that, "add/harden a worker" is a
one-place change.
