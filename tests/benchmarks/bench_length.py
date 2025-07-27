import functools
import itertools
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


class RunThenOk(py_trees.behaviour.Behaviour):
    """A skeleton behaviour that inherits from the PyTrees Behaviour class."""

    c: bool

    def __init__(self, name: str) -> None:
        super().__init__(name)

    def setup(self, **kwargs: Any) -> None:
        self.logger.debug("  %s [Foo::setup()]" % self.name)

    def initialise(self) -> None:
        self.c = False
        self.logger.debug("  %s [Foo::initialise()]" % self.name)

    def update(self) -> py_trees.common.Status:
        r = py_trees.common.Status.SUCCESS if self.c else py_trees.common.Status.RUNNING
        self.c = True
        return r

    def terminate(self, new_status: py_trees.common.Status) -> None:
        self.c = False
        self.logger.debug(
            "  %s [Foo::terminate().terminate()][%s->%s]"
            % (self.name, self.status, new_status)
        )


def py_trees_run(
    length: int = 1,
    n_ticks: int = 500,
):
    children = itertools.chain(
        (RunThenOk(f"child {i}") for i in range(length - 1)),
        (AlwaysRunning(f"child {length - 1}"),),
    )
    root = py_trees.composites.Sequence("root", memory=True, children=list(children))

    behaviour_tree = py_trees.trees.BehaviourTree(root=root)
    behaviour_tree.setup(timeout=15)
    for _ in range(n_ticks):
        behaviour_tree.tick()


def btreeny_run(
    length: int = 1,
    n_ticks: int = 500,
):
    children = itertools.chain(
        (sa.run_then_ok() for _ in range(length - 1)),
        (sa.always_running(),),
    )
    action = bt.sequential(*children)

    with action as tick:
        for _ in range(n_ticks):
            _ = tick(None)


__benchmarks__ = [
    (
        functools.partial(py_trees_run, length=2),
        functools.partial(btreeny_run, length=2),
        "Length 2 sequential",
    ),
    (
        functools.partial(py_trees_run, length=10),
        functools.partial(btreeny_run, length=10),
        "Length 10 sequential",
    ),
    (
        functools.partial(py_trees_run, length=100),
        functools.partial(btreeny_run, length=100),
        "Length 100 sequential",
    ),
]
