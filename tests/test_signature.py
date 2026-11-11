from flaky_hunter.analyze.signature import normalize_text, signature_for


def test_volatile_parts_are_normalized():
    first = signature_for(
        "Connection refused: demo-service:5432 at 2026-11-11T10:00:00.123", ""
    )
    second = signature_for(
        "Connection refused: demo-service:6379 at 2026-11-11T11:22:33.456", ""
    )
    assert first.signature == second.signature


def test_exception_type_separates_signatures():
    timeout = signature_for("TimeoutError: deadline exceeded", "")
    assertion = signature_for("AssertionError: nope", "")
    assert timeout.signature != assertion.signature
    assert timeout.exception == "TimeoutError"
    assert assertion.exception == "AssertionError"


def test_library_frames_are_ignored():
    trace = (
        'File "C:\\Python\\lib\\site-packages\\requests\\api.py", line 61, in get\n'
        'File "tests/test_api.py", line 10, in test_get\n'
    )
    info = signature_for("AssertionError", trace)
    assert info.frames == ["test_api.py:test_get"]


def test_normalize_keeps_identifiers_intact():
    text = normalize_text("value 123 in test_2fa")
    assert "test_2fa" in text
