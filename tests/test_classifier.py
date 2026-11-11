from flaky_hunter.analyze.classifier import classify_message


def test_labels_are_matched_in_priority_order():
    assert classify_message("ConnectionError: ECONNREFUSED") == "network"
    assert classify_message("TimeoutError: timed out") == "timeout"
    assert classify_message("UNIQUE constraint failed: users.email") == "data-residue"
    assert classify_message("deadlock detected") == "concurrency"
    assert classify_message("Too many open files") == "resource"
    assert classify_message("AssertionError: expected 1") == "assertion-mismatch"
    assert classify_message("something odd happened") == "unknown"
    assert classify_message("") == "unknown"
