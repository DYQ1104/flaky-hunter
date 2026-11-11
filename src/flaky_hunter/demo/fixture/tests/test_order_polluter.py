"""Marks shared state as dirty, which breaks ``test_order_victim``.

The mutation lives in ``os.environ`` so it survives inside one pytest process
but disappears between probes, which is exactly the pollution pattern locate is
designed to find.
"""

import os


def test_write_shared_state():
    os.environ["FH_DEMO_STATE"] = "dirty"
    assert True
