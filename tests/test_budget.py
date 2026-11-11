from flaky_hunter.locate import ProbeBudget


def test_budget_defaults_to_sixty_probes():
    budget = ProbeBudget()

    assert budget.max_probes == 60
    assert budget.used == 0
    assert budget.can_probe() is True
    assert budget.exhausted is False
    assert str(budget) == "0/60"


def test_consume_tracks_usage_and_exhaustion():
    budget = ProbeBudget(max_probes=2)

    budget.consume()
    assert budget.used == 1
    assert budget.can_probe() is True
    assert budget.exhausted is False

    budget.consume()
    assert budget.used == 2
    assert budget.can_probe() is False
    assert budget.exhausted is True
    assert str(budget) == "2/2"


def test_zero_budget_is_immediately_exhausted():
    budget = ProbeBudget(max_probes=0)

    assert budget.can_probe() is False
    assert budget.exhausted is True
