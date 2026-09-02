"""
Regression coverage for ``core.memory.Memory``.

Covers:
- Basic ``add_message`` / ``get_history`` round-trip
- ``max_history * 2`` truncation policy
- ``clear`` removes a session
- ``persist_path`` round-trips across instances
- ``persist_path=None`` (pure in-memory mode)
- Bug-17 regression: bare filename (no directory) does not crash on save
- Bug-9 regression: concurrent writers do not lose messages
"""
import json
import os
import threading


from core.memory import Memory


def test_add_and_get_history_basic():
    mem = Memory(max_history=10)
    mem.add_message("s1", "user", "hello")
    mem.add_message("s1", "assistant", "hi")
    history = mem.get_history("s1")
    assert [m["role"] for m in history] == ["user", "assistant"]
    assert [m["content"] for m in history] == ["hello", "hi"]


def test_get_history_unknown_session_returns_empty():
    mem = Memory(max_history=10)
    assert mem.get_history("never-existed") == []


def test_max_history_truncation():
    # max_history=2 keeps the most recent 4 messages (2 user + 2 assistant).
    mem = Memory(max_history=2)
    for i in range(10):
        mem.add_message("s", "user", f"u{i}")
        mem.add_message("s", "assistant", f"a{i}")
    history = mem.get_history("s")
    assert len(history) == 4
    # Oldest two messages are dropped; the last 4 are kept.
    assert history[0]["content"] == "u8"
    assert history[-1]["content"] == "a9"


def test_clear_removes_session():
    mem = Memory(max_history=10)
    mem.add_message("s", "user", "hi")
    assert mem.get_history("s")
    mem.clear("s")
    assert mem.get_history("s") == []


def test_clear_unknown_session_is_noop():
    mem = Memory(max_history=10)
    # Should not raise.
    mem.clear("never-existed")


def test_sessions_are_isolated():
    mem = Memory(max_history=10)
    mem.add_message("s1", "user", "in-s1")
    mem.add_message("s2", "user", "in-s2")
    assert len(mem.get_history("s1")) == 1
    assert len(mem.get_history("s2")) == 1
    assert mem.get_history("s1")[0]["content"] == "in-s1"
    assert mem.get_history("s2")[0]["content"] == "in-s2"


def test_persist_path_round_trip(tmpdir):
    path = os.path.join(str(tmpdir), "nested", "memory.json")
    mem1 = Memory(max_history=10, persist_path=path)
    mem1.add_message("s", "user", "persisted")
    # Force a fresh instance to read back from disk.
    mem2 = Memory(max_history=10, persist_path=path)
    history = mem2.get_history("s")
    assert len(history) == 1
    assert history[0]["content"] == "persisted"


def test_persist_path_none_is_in_memory_only(tmpdir):
    mem = Memory(max_history=10, persist_path=None)
    mem.add_message("s", "user", "ephemeral")
    # No file should ever have been written.
    assert not os.listdir(str(tmpdir))


def test_b17_bare_filename_does_not_crash(tmpdir):
    """
    Bug-17 regression: a persist_path with no directory component
    (e.g. "memory.json") used to crash inside os.makedirs(os.path.dirname(...))
    because os.path.dirname returns "".
    """
    # cd into tmpdir so the bare filename lands somewhere predictable.
    cwd = os.getcwd()
    try:
        os.chdir(str(tmpdir))
        mem = Memory(max_history=10, persist_path="memory.json")
        mem.add_message("s", "user", "ok")
        # File written in CWD.
        assert os.path.isfile("memory.json")
        with open("memory.json", "r", encoding="utf-8") as f:
            data = json.load(f)
        assert data["s"][0]["content"] == "ok"
    finally:
        os.chdir(cwd)


def test_b09_concurrent_writers_do_not_lose_messages(tmpdir):
    """
    Bug-9 regression: 10 threads concurrently call add_message on the SAME
    session_id. Before the lock was added, each thread did load→modify→write
    independently and the second-to-last writer would clobber the last one,
    dropping messages. After the fix, all 10 messages survive.
    """
    path = os.path.join(str(tmpdir), "mem.json")
    mem = Memory(max_history=1000, persist_path=path)

    N_THREADS = 10
    barrier = threading.Barrier(N_THREADS)

    def writer(i):
        barrier.wait()  # release all threads at once to maximize contention
        mem.add_message("shared", "user", f"msg-{i}")

    threads = [threading.Thread(target=writer, args=(i,)) for i in range(N_THREADS)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    history = mem.get_history("shared")
    assert len(history) == N_THREADS
    # Each message content must appear exactly once.
    contents = sorted(m["content"] for m in history)
    assert contents == [f"msg-{i}" for i in range(N_THREADS)]

    # Reload from disk and verify persistence wasn't corrupted either.
    mem2 = Memory(max_history=1000, persist_path=path)
    history2 = mem2.get_history("shared")
    assert len(history2) == N_THREADS
