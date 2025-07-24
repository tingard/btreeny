import functools
import itertools
from typing import Any
import btreeny as bt


@bt.simple_action
def always_ok(b: Any):
    return bt.SUCCESS


@bt.simple_action
def always_running(b: Any):
    return bt.RUNNING


@bt.simple_action
def always_fail(b: Any):
    return bt.FAILURE


@bt.simple_action
def never_runs(b: Any):
    assert False, "Action should not run"


@bt.action
def run_then(result: bt.TreeStatus = bt.SUCCESS, count: int = 1):
    c = itertools.chain([bt.RUNNING] * count, itertools.repeat(result))
    yield lambda b: next(c)


run_then_ok = functools.partial(run_then, result=bt.SUCCESS)
run_then_fail = functools.partial(run_then, result=bt.FAILURE)
