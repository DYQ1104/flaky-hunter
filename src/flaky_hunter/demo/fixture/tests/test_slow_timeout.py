"""Times out on every fourth round."""

import os
import time


def test_slow_call():
    round_no = int(os.environ.get("FH_ROUND", "0"))
    if round_no and round_no % 4 == 0:
        time.sleep(0.01)
        raise TimeoutError("deadline exceeded after 2000ms")
    assert True
