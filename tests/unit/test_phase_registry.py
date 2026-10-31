from pokecoach_python.workflow.registry import deployed_handlers, handler_for, phase_order


def test_phase_order():
    assert phase_order()[0] == "A"


def test_only_phase_a_deployed():
    handlers = deployed_handlers(["A", "B"])
    assert set(handlers) == {"A"}
    assert handler_for("B") is None
