# Cross-Artifact Consistency Report

## Coverage

| Spec FR | Constitution principle | Plan section | Tasks |
|---|---|---|---|
| FR-001 `/health` | III, V | Architecture & Data Flow | T050 |
| FR-002 `/separate` | I, II | `/separate` flow | T020–T025 |
| FR-003 cache | IV | Design decisions | T022 |
| FR-004 WS progress | VII | `/separate` flow | T023 |
| FR-005 `/download/{job}/{stem}` | IV | `/separate` flow | T024 |
| FR-006 `/jobs[/id]` | VII | Architecture | T007 |
| FR-007–FR-008 `/align` | II, III | `/align` flow | T030–T036 |
| FR-009–FR-010 `/pitch` | II, V | `/pitch` flow | T040–T045 |
| FR-011 API key | — | Constraints | T052 |
| FR-012 MAX_CONCURRENT | — | Constraints | T008 |
| FR-013 expandable_segments | V | Design decisions | T004 |
| FR-014 torch.load patch | VI | Design decisions | T005 |
| FR-015 background warmup | III | Design decisions | T009 |
| FR-016 `--skip-warmup` | III | Constraints | T051 |
| FR-017 wav2vec2 aligner LRU | V | Design decisions | T010 |

All functional requirements map to constitution principles, plan
sections, and tasks.

## Drift

- **README vs spec**: README documents granularity behaviours and
  warmup states that the spec restates. Consistent. No drift detected.
- **Constitution vs plan**: Plan respects all seven principles; no
  exceptions filed.
- **Tasks vs reality**: All "DONE" tasks correspond to code in
  `server.py`. The "OPEN" tasks are real gaps, not phantom items.

## Gaps

1. **No automated test suite (T011).** Pitch aggregation, octave
   correction, and granularity post-processing are exactly the kind of
   logic that quietly drifts under refactors. A pytest suite would pay
   for itself the first time `whisperx` ships a breaking minor.
2. **API-key wire format undocumented (FR-011 NEEDS CLARIFICATION).**
   The spec marks this clearly, but the README is also silent on the
   header name. Worth a one-line addition to README and a fixture in
   the future test suite.
3. **Disk-cache is unbounded (T054).** Long-lived servers will fill
   their cache disk. No documented eviction policy.
4. **Job table is non-persistent (T027).** A server restart drops job
   metadata; only the cached output survives. Most clients re-derive
   the cache key, so this is mostly cosmetic — but a long-running
   `/jobs` UI would lose history.
5. **Cache key + `--model` interaction (T026 NEEDS CLARIFICATION).**
   Spec flags this. Behaviour should be specified before a user sees
   surprising "stale" stems.
6. **Performance number (SC-001).** "Under 30 s" is unanchored to a
   GPU class. Should pin to a reference (e.g., RTX 3060 12 GB) or
   delete the number.

## Recommendations

1. **Add a minimal `tests/` suite** covering: cache-hit short-circuit,
   granularity tagging (`new_line`, `phoneme`), pitch octave-clamping
   on a synthesised vocal stem, `/health.warmup` shape.
2. **Document the API-key header** in README and the spec's FR-011.
3. **Add a `--cache-max-gb` flag** with simple LRU eviction at startup
   when the cache exceeds the cap.
4. **Anchor SC-001** to a specific reference GPU.
5. **Cache-key extension**: include the model name in the cache key
   so `--model` switches coexist instead of colliding.
6. **Optional**: split `server.py` into `server.py` + `pitch.py` +
   `align.py` + `separate.py` once a test suite exists, not before —
   the monolith is currently a feature, not a bug.
