import functools

import btreeny as bt

from standard_actions import run_then


@bt.runner
def test_repeats_three_nodes():
    run_then_ok = bt.repeat(
        functools.partial(run_then, result=bt.SUCCESS), continue_if=bt.SUCCESS
    )
    with run_then_ok as tick:
        for i in range(1000):
            _ = tick({})
            tree = bt.viz.get_tree_status()
            # As we re-mint a UUID whenever an action is first setup, this
            # grows in an unbounded way.
            assert tree.count() == 2 + i // 2
