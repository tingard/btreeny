import btreeny as bt

from standard_actions import run_then_ok


def test_isolates_runs():
    @bt.runner
    def episode():
        with bt.redo(lambda: bt.sequential(run_then_ok()), count=None) as tick:
            for _ in range(20):
                tick({})
        return len(bt._ctx.id_map.get() or {})

    for i in range(4):
        n_nodes = episode()
        assert n_nodes == 3
