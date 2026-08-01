import btreeny as bt
import tests.standard_actions as sa


@bt.runner
def test_a_b():
    @bt.action
    def action_a(_):
        def _inner(b: int):
            if b % 2 == 1:
                return bt.FAILURE
            return bt.RUNNING

        yield _inner

    @bt.action
    def action_b(_):
        def _inner(b: int):
            if b % 2 == 0:
                return bt.FAILURE
            return bt.RUNNING

        yield _inner

    def value_fn(k: bool):
        if k:
            return bt.sequential(sa.always_ok(), action_a())
        return bt.sequential(sa.always_ok(), action_b())

    with bt.keyed(lambda i: (i % 2) == 0, value_fn) as foo:
        # Start on A
        assert foo(0) == bt.RUNNING
        assert foo(2) == bt.RUNNING
        # Switch to B
        assert foo(1) == bt.RUNNING
        assert foo(3) == bt.RUNNING
        # Switch back to A
        assert foo(8) == bt.RUNNING
        # Switch back to B
        assert foo(9) == bt.RUNNING
    # We should have recorded the root, the two sequential nodes, and the two
    # leaf nodes per sequential node
    assert bt.viz.get_tree_status().count() == (1 + 2 + 2 + 2)
