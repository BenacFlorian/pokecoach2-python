from pokecoach_python.workflow.registry import deployed_handlers, handler_for, phase_order


def test_phase_order():
    assert phase_order()[0] == "A"


def test_phase_b_handler_registered():
    assert handler_for("B") is not None


def test_deployed_handlers_filters_missing_implementations():
    handlers = deployed_handlers(["A", "B", "C", "D"])
    assert set(handlers) == {"A", "B", "C", "D"}
