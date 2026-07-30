import functools

import btreeny as bt

from standard_actions import run_then


@bt.runner
def test_repeats_three_nodes():
    run_then_ok = bt.repeat(
        functools.partial(run_then, result=bt.SUCCESS), continue_if=bt.SUCCESS
    )

    with run_then_ok as tick:
        tree = None
        for i in range(10):
            _ = tick({})
            tree = bt.viz.get_tree_status()
            # As IDs are defined by the hash of their parents id and their child index,
            # growth should be bounded
        if tree is not None:
            tree.pprint()
        graph_size = len(bt._ctx.tree_graph.get() or {})
        # Should only have the root repeat, and a single child
        assert tree is not None and graph_size == 2
