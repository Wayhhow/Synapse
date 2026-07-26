"""
Regression coverage for ``core.skill_registry.SkillRegistry``.

Covers:
- ``register`` creates new entries with default stats
- Bug-5: ``register`` updates description for existing skills
- ``record_execution`` accumulates total/success/failure counts
- ``record_execution(success=True)`` clears stale last_error (Bug-7 related)
- ``record_execution(success=False)`` stores error string
- ``get_stats`` / ``get_all_stats`` round-trip
- Persistence round-trip across instances
- Bug-19: no `health_score` field is written; stale values are migrated on load
- Bug-17: bare filename persist_path does not crash
- Bug-9: concurrent record_execution calls do not lose increments
"""
import json
import os
import threading

import pytest

from core.skill_registry import SkillRegistry


def test_register_creates_new_entry(tmpdir):
    reg = SkillRegistry(persist_path=os.path.join(str(tmpdir), "r.json"))
    reg.register("skill_a", "first description")
    stats = reg.get_stats("skill_a")
    assert stats is not None
    assert stats["description"] == "first description"
    assert stats["total_count"] == 0
    assert stats["success_count"] == 0
    assert stats["failure_count"] == 0
    assert stats["last_error"] is None


def test_b05_register_updates_description_for_existing_skill(tmpdir):
    """
    Bug-5 regression: calling register() with a non-empty description on an
    already-registered skill must update the description rather than being
    silently ignored. This is how the SkillRouter refreshes descriptions on
    startup, and how SkillCreator replaces its placeholder description later.
    """
    reg = SkillRegistry(persist_path=os.path.join(str(tmpdir), "r.json"))
    reg.register("skill_a", "placeholder")
    assert reg.get_stats("skill_a")["description"] == "placeholder"

    reg.register("skill_a", "real description")
    assert reg.get_stats("skill_a")["description"] == "real description"


def test_b05_register_with_empty_description_does_not_clobber(tmpdir):
    """
    Bug-5 follow-up: if a caller passes an empty description, we must NOT
    overwrite the existing non-empty description. Otherwise record_execution's
    implicit register(skill_name) call (when a new skill is observed) would
    wipe out the description set by SkillRouter.
    """
    reg = SkillRegistry(persist_path=os.path.join(str(tmpdir), "r.json"))
    reg.register("skill_a", "real description")
    reg.register("skill_a", "")  # should be a no-op
    assert reg.get_stats("skill_a")["description"] == "real description"


def test_record_execution_success_increments_success_count(tmpdir):
    reg = SkillRegistry(persist_path=os.path.join(str(tmpdir), "r.json"))
    reg.record_execution("skill_a", success=True, execution_time=0.1)
    reg.record_execution("skill_a", success=True, execution_time=0.2)
    stats = reg.get_stats("skill_a")
    assert stats["total_count"] == 2
    assert stats["success_count"] == 2
    assert stats["failure_count"] == 0
    assert stats["last_error"] is None


def test_record_execution_failure_stores_error(tmpdir):
    reg = SkillRegistry(persist_path=os.path.join(str(tmpdir), "r.json"))
    reg.record_execution("skill_a", success=False, execution_time=0.1, error="boom")
    stats = reg.get_stats("skill_a")
    assert stats["failure_count"] == 1
    assert stats["last_error"] == "boom"


def test_record_execution_success_clears_stale_last_error(tmpdir):
    """
    Bug-7 related regression: a previous failure leaves `last_error` set.
    A subsequent success must clear it, otherwise operators inspecting /stats
    would see a stale error message that no longer applies.
    """
    reg = SkillRegistry(persist_path=os.path.join(str(tmpdir), "r.json"))
    reg.record_execution("skill_a", success=False, error="first failure")
    assert reg.get_stats("skill_a")["last_error"] == "first failure"
    reg.record_execution("skill_a", success=True)
    assert reg.get_stats("skill_a")["last_error"] is None


def test_record_execution_auto_registers_unknown_skill(tmpdir):
    reg = SkillRegistry(persist_path=os.path.join(str(tmpdir), "r.json"))
    # record_execution on a skill that was never explicitly registered
    # should auto-create the entry so the stat is not lost.
    reg.record_execution("ghost", success=True)
    stats = reg.get_stats("ghost")
    assert stats is not None
    assert stats["total_count"] == 1


def test_get_stats_returns_defensive_copy(tmpdir):
    reg = SkillRegistry(persist_path=os.path.join(str(tmpdir), "r.json"))
    reg.register("skill_a", "desc")
    stats = reg.get_stats("skill_a")
    stats["description"] = "mutated-by-caller"
    # Internal state must not be affected by external mutation.
    assert reg.get_stats("skill_a")["description"] == "desc"


def test_get_all_stats_returns_defensive_copy(tmpdir):
    reg = SkillRegistry(persist_path=os.path.join(str(tmpdir), "r.json"))
    reg.register("skill_a", "desc")
    all_stats = reg.get_all_stats()
    all_stats["skill_a"]["description"] = "mutated-by-caller"
    assert reg.get_stats("skill_a")["description"] == "desc"


def test_persistence_round_trip(tmpdir):
    path = os.path.join(str(tmpdir), "r.json")
    reg1 = SkillRegistry(persist_path=path)
    reg1.register("skill_a", "desc")
    reg1.record_execution("skill_a", success=True, execution_time=0.05)

    reg2 = SkillRegistry(persist_path=path)
    stats = reg2.get_stats("skill_a")
    assert stats is not None
    assert stats["description"] == "desc"
    assert stats["total_count"] == 1
    assert stats["success_count"] == 1


def test_b19_no_health_score_field_in_persisted_file(tmpdir):
    """
    Bug-19 regression: the `health_score` field was previously persisted but
    never updated, giving the false impression that every skill was perfectly
    healthy. The field is no longer written.
    """
    path = os.path.join(str(tmpdir), "r.json")
    reg = SkillRegistry(persist_path=path)
    reg.register("skill_a", "desc")
    with open(path, "r", encoding="utf-8") as f:
        raw = json.load(f)
    assert "health_score" not in raw["skill_a"]


def test_b19_stale_health_score_migrated_on_load(tmpdir):
    """
    Bug-19 regression: an existing on-disk JSON file that still contains
    `health_score` from an older Synapse version must be loaded successfully,
    with the stale field dropped silently during load.
    """
    path = os.path.join(str(tmpdir), "r.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump({
            "skill_a": {
                "description": "old",
                "created_at": "2026-01-01T00:00:00",
                "total_count": 0,
                "success_count": 0,
                "failure_count": 0,
                "last_error": None,
                "avg_execution_time": 0.0,
                "health_score": 100.0,  # stale
            }
        }, f)
    reg = SkillRegistry(persist_path=path)
    stats = reg.get_stats("skill_a")
    assert stats is not None
    assert "health_score" not in stats
    # The next save should not re-add it.
    reg.register("skill_b", "new")
    with open(path, "r", encoding="utf-8") as f:
        raw = json.load(f)
    assert "health_score" not in raw["skill_a"]
    assert "health_score" not in raw["skill_b"]


def test_b17_bare_filename_does_not_crash(tmpdir):
    """
    Bug-17 regression: a persist_path with no directory component
    (e.g. "registry.json") used to crash inside os.makedirs("").
    """
    cwd = os.getcwd()
    try:
        os.chdir(str(tmpdir))
        reg = SkillRegistry(persist_path="registry.json")
        reg.register("skill_a", "desc")
        assert os.path.isfile("registry.json")
    finally:
        os.chdir(cwd)


def test_b09_concurrent_record_execution_does_not_lose_increments(tmpdir):
    """
    Bug-9 regression: 10 threads concurrently record executions on the SAME
    skill. Without the lock, the load→modify→write cycle could lose updates
    (both threads load total=0, both write total=1, ending up with 1 instead
    of 10). After the fix, all 10 increments survive.
    """
    path = os.path.join(str(tmpdir), "r.json")
    reg = SkillRegistry(persist_path=path)
    reg.register("skill_a", "desc")

    N_THREADS = 10
    barrier = threading.Barrier(N_THREADS)

    def writer():
        barrier.wait()
        reg.record_execution("skill_a", success=True, execution_time=0.001)

    threads = [threading.Thread(target=writer) for _ in range(N_THREADS)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    stats = reg.get_stats("skill_a")
    assert stats["total_count"] == N_THREADS
    assert stats["success_count"] == N_THREADS
