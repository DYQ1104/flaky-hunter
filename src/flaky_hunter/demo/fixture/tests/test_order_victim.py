"""Passes alone, fails after ``test_order_polluter`` dirties shared state."""

import os


def test_read_shared_state():
    state = os.environ.get("FH_DEMO_STATE", "clean")
    assert state == "clean", f"shared state was polluted: {state}"
