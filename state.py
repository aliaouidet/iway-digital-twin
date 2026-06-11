"""Compatibility shim — the real module moved to backend/domain/state.py.

Kept so external scripts and old notebooks importing `from state import ...`
keep working; all in-repo code now imports backend.domain.state directly
(no longer depends on the repo root being on sys.path).
"""
from backend.domain.state import *  # noqa: F401,F403
