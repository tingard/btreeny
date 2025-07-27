import functools
from typing import Any
import py_trees
import btreeny as bt
import tests.standard_actions as sa


class AlwaysRunning(py_trees.behaviour.Behaviour):
    """A skeleton behaviour that inherits from the PyTrees Behaviour class."""

    def __init__(self, name: str) -> None:
        super().__init__(name)

    def setup(self, **kwargs: Any) -> None:
        self.logger.debug("  %s [Foo::setup()]" % self.name)

    def initialise(self) -> None:
        self.logger.debug("  %s [Foo::initialise()]" % self.name)

    def update(self) -> py_trees.common.Status:
        return py_trees.common.Status.RUNNING

    def terminate(self, new_status: py_trees.common.Status) -> None:
        self.logger.debug(
            "  %s [Foo::terminate().terminate()][%s->%s]"
            % (self.name, self.status, new_status)
        )


def py_trees_run(
    depth: int = 1,
    n_ticks: int = 500,
):
    action = AlwaysRunning("always running")
    for i in range(depth):
        action = py_trees.composites.Sequence(
            f"parent_{i}", memory=True, children=[action]
        )

    behaviour_tree = py_trees.trees.BehaviourTree(root=action)
    behaviour_tree.setup(timeout=15)
    for _ in range(n_ticks):
        behaviour_tree.tick()


def btreeny_run(
    depth: int = 1,
    n_ticks: int = 500,
):
    action = sa.always_running()
    for _ in range(depth):
        action = bt.sequential(action)

    with action as tick:
        for _ in range(n_ticks):
            _ = tick(None)


__benchmarks__ = [
    (
        functools.partial(py_trees_run, depth=1),
        functools.partial(btreeny_run, depth=1),
        "Depth 1 sequential",
    ),
    (
        functools.partial(py_trees_run, depth=10),
        functools.partial(btreeny_run, depth=10),
        "Depth 10 sequential",
    ),
    (
        functools.partial(py_trees_run, depth=100),
        functools.partial(btreeny_run, depth=100),
        "Depth 100 sequential",
    ),
]
