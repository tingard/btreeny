import btreeny as bt

import tests.standard_actions as sa


def test_isolates_runs():
    @bt.runner
    def episode():
        with bt.redo(lambda: bt.sequential(sa.run_then_ok()), count=None) as tick:
            for _ in range(20):
                tick({})
        return len(bt._ctx.id_map.get() or {})

    for i in range(4):
        n_nodes = episode()
        assert n_nodes == 3


def test_isolates_runs_dirty_context():
    @bt.runner
    def episode():
        with bt.redo(lambda: bt.sequential(sa.run_then_ok()), count=None) as tick:
            for _ in range(20):
                tick({})
        return len(bt._ctx.id_map.get() or {})

    with sa.run_then_fail() as tick:
        tick(None)
    n_nodes = episode()
    assert n_nodes == 3
