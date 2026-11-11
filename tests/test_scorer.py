from flaky_hunter.analyze.scorer import classify_outcome, compute_score
from flaky_hunter.models import Classification


def test_coin_flip_reaches_full_score():
    assert compute_score(20, 10) == 100


def test_single_failure_in_twenty_rounds():
    assert compute_score(20, 1) == 19


def test_score_is_symmetric_around_half():
    assert compute_score(20, 4) == compute_score(20, 16)


def test_small_sample_is_discounted():
    assert compute_score(3, 1) < compute_score(20, 7)


def test_extremes_score_zero():
    assert compute_score(0, 0) == 0
    assert compute_score(10, 0) == 0
    assert compute_score(10, 10) == 0


def test_classification_buckets():
    assert classify_outcome(2, 1, min_attempts=5) == Classification.INSUFFICIENT
    assert classify_outcome(10, 0, min_attempts=5) == Classification.STABLE
    assert classify_outcome(10, 10, min_attempts=5) == Classification.BROKEN
    assert classify_outcome(10, 3, min_attempts=5) == Classification.FLAKY
