"""The cache must honour the requested STEM SET, not just the audio and the model. (#10)

`job_id` is `(audio_hash, model)` and deliberately does not include the stem set. That's
fine for the on-disk cache — `_check_cache` requires every requested stem to be present —
but `_enqueue_job` short-circuited on the in-memory jobs table and returned a completed
job's stems *regardless of what had been asked for*:

    POST /separate?model=bs_roformer_sw                         -> drums, bass, vocals, other
    POST /separate?model=bs_roformer_sw&stems=...,guitar,piano  -> drums, bass, vocals, other

...in 0 ms, with no error. The caller asked for guitar and piano, got neither, and the
response *looked* like a fast success. Silent and fast is the worst combination: nothing
tells you the answer is stale rather than authoritative.

Extracted via AST, like test_cache_cleanup, to avoid server.py's torch/whisperx import
chain — which is exactly why this can run in CI.
"""
import ast
import collections
import threading
import time
from pathlib import Path

import pytest

SERVER_PY = Path(__file__).parent.parent / "server.py"


def _load_enqueue_job(jobs, max_concurrent=2):
    """Extract _enqueue_job with a namespace standing in for server.py's module globals."""
    tree = ast.parse(SERVER_PY.read_text(encoding="utf-8"))
    node = next(n for n in ast.iter_child_nodes(tree)
                if isinstance(n, ast.FunctionDef) and n.name == "_enqueue_job")
    mod = ast.Module(body=[node], type_ignores=[])
    ast.copy_location(mod, node)

    started = []

    class _FakeThread:
        def __init__(self, target=None, args=(), daemon=None):
            self._args = args

        def start(self):
            started.append(self._args)      # record; never actually separate anything

    ns = {
        "jobs": jobs,
        "jobs_lock": threading.Lock(),
        "active_lock": threading.Lock(),
        "active_count": 0,
        "MAX_CONCURRENT": max_concurrent,
        "threading": type("T", (), {"Thread": _FakeThread}),
        "time": time,
        "_run_roformer": lambda *a: None,
        "_run_demucs": lambda *a: None,
        "_is_roformer_model": lambda m: "roformer" in m,
    }
    exec(compile(ast.unparse(mod), "<test>", "exec"), ns)
    return ns["_enqueue_job"], started


JOB_ID = "deadbeef-bs-roformer-sw"
FOUR = {"drums": "/download/x/drums.flac", "bass": "/download/x/bass.flac",
        "vocals": "/download/x/vocals.flac", "other": "/download/x/other.flac"}
SIX = dict(FOUR, guitar="/download/x/guitar.flac", piano="/download/x/piano.flac")
SIX_NAMES = ["drums", "bass", "vocals", "other", "guitar", "piano"]


def _completed(stems_all, stem_list=None):
    return collections.OrderedDict({JOB_ID: {
        "job_id": JOB_ID, "status": "complete", "progress": 100,
        "stems": dict(stems_all), "stems_all": dict(stems_all),
        "stem_list": list(stem_list or stems_all), "missing": [],
        "error": None, "model": "bs_roformer_sw", "created_at": time.time(),
    }})


def _in_flight(stem_list):
    return collections.OrderedDict({JOB_ID: {
        "job_id": JOB_ID, "status": "processing", "progress": 40,
        "stems": {}, "stems_all": {}, "stem_list": list(stem_list), "missing": [],
        "error": None, "model": "bs_roformer_sw", "created_at": time.time(),
    }})


def test_superset_request_is_not_served_from_a_smaller_completed_job():
    """THE bug: a 6-stem request answered with the cached 4, instantly, with no error."""
    jobs = _completed(FOUR)
    enqueue, started = _load_enqueue_job(jobs)
    result = enqueue(JOB_ID, "/tmp/a.ogg", SIX_NAMES, "bs_roformer_sw")

    assert result.get("cached") is not True, (
        "serving the cached 4-stem result for a 6-stem request is silent data loss — the "
        "caller asked for guitar and piano and got neither, with no error"
    )
    assert started, "it must actually re-separate rather than return a short result"


def test_exact_match_is_served_from_cache():
    jobs = _completed(SIX)
    enqueue, started = _load_enqueue_job(jobs)
    result = enqueue(JOB_ID, "/tmp/a.ogg", SIX_NAMES, "bs_roformer_sw")
    assert result["cached"] is True
    assert set(result["stems"]) == set(SIX)
    assert not started


def test_subset_request_is_served_from_a_larger_completed_job():
    """Fewer stems than were computed is a legitimate hit — and returns only what was asked
    for, not everything we happen to have lying around."""
    jobs = _completed(SIX)
    enqueue, started = _load_enqueue_job(jobs)
    result = enqueue(JOB_ID, "/tmp/a.ogg", ["vocals", "drums"], "bs_roformer_sw")
    assert result["cached"] is True
    assert set(result["stems"]) == {"vocals", "drums"}
    assert not started


def test_case_and_whitespace_do_not_defeat_the_coverage_check():
    jobs = _completed(SIX)
    enqueue, _ = _load_enqueue_job(jobs)
    assert enqueue(JOB_ID, "/tmp/a.ogg", [" Vocals ", "DRUMS"], "bs_roformer_sw")["cached"]


def test_a_job_from_before_this_fix_still_serves_its_stems():
    # Old jobs carry only `stems` (no `stems_all`). Coverage must fall back to it, or every
    # pre-existing entry would be needlessly re-separated.
    jobs = collections.OrderedDict({JOB_ID: {
        "job_id": JOB_ID, "status": "complete", "progress": 100,
        "stems": dict(SIX), "error": None, "model": "bs_roformer_sw",
        "created_at": time.time(),
    }})
    enqueue, started = _load_enqueue_job(jobs)
    result = enqueue(JOB_ID, "/tmp/a.ogg", ["vocals", "guitar"], "bs_roformer_sw")
    assert result["cached"] is True
    assert not started


def test_in_flight_job_with_a_smaller_set_is_not_silently_joined():
    """Riding along on a running 4-stem job completes without guitar/piano — the same silent
    loss, merely delayed."""
    jobs = _in_flight(["drums", "bass", "vocals", "other"])
    enqueue, _ = _load_enqueue_job(jobs)
    result = enqueue(JOB_ID, "/tmp/a.ogg", SIX_NAMES, "bs_roformer_sw")
    assert "error" in result
    assert result.get("status") != "processing"


def test_in_flight_job_that_covers_us_is_joined():
    jobs = _in_flight(SIX_NAMES)
    enqueue, started = _load_enqueue_job(jobs)
    result = enqueue(JOB_ID, "/tmp/a.ogg", ["vocals", "guitar"], "bs_roformer_sw")
    assert result["status"] == "processing"
    assert not started, "must attach to the running job, not start a second separation"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
