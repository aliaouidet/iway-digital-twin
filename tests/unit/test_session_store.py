"""Unit tests for the agent-handoff queue position."""
import os
os.environ.setdefault("GOOGLE_API_KEY", "offline")

from backend.services.session_store import SESSIONS, queue_position


def test_queue_position_counts_other_pending_sessions():
    SESSIONS.clear()
    SESSIONS["a"] = {"status": "handoff_pending"}
    SESSIONS["b"] = {"status": "handoff_pending"}
    SESSIONS["c"] = {"status": "active"}          # not waiting → not counted
    SESSIONS["d"] = {"status": "resolved"}        # not waiting → not counted
    # Two sessions waiting; each is "1 other ahead + itself" = 2.
    assert queue_position("a") == 2
    assert queue_position("b") == 2


def test_queue_position_first_in_line():
    SESSIONS.clear()
    SESSIONS["only"] = {"status": "handoff_pending"}
    assert queue_position("only") == 1


def test_queue_position_ignores_non_pending():
    SESSIONS.clear()
    SESSIONS["x"] = {"status": "active"}
    # A session not awaiting an agent still reports a truthful 1 (no one ahead).
    assert queue_position("x") == 1
