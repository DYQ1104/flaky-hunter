"""Flaky network test: fails on every third round."""

import os


def test_fetch_remote():
    round_no = int(os.environ.get("FH_ROUND", "0"))
    if round_no and round_no % 3 == 0:
        raise ConnectionRefusedError("Connection refused: demo-service:8080")
    assert True
