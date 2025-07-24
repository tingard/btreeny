import btreeny as bt
import btreeny.viz
import tests.standard_actions as sa


def test_can_get_context():
    root = bt.sequential(sa.always_ok())

    with root as tick:
        _ = tick(None)
        tree = btreeny.viz.get_tree_status()

    assert isinstance(tree, btreeny.viz.TreeStatusGraph)
    assert tree.node == "sequential"
    assert tree.status == bt.SUCCESS
    assert len(tree.children) == 1
    assert tree.children[0].node == "always_ok"
    assert tree.children[0].status == bt.SUCCESS
