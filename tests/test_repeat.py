import pytest
import btreeny as bt

import tests.standard_actions as sa


@pytest.mark.parametrize(
    "child,continue_if,expected",
    [
        (sa.always_ok, bt.SUCCESS, [bt.RUNNING, bt.RUNNING]),
        (sa.always_fail, bt.SUCCESS, [bt.FAILURE]),
        (sa.always_running, bt.SUCCESS, [bt.RUNNING]),
        (sa.run_then_fail, bt.SUCCESS, [bt.RUNNING, bt.FAILURE]),
        (sa.run_then_ok, bt.SUCCESS, [bt.RUNNING, bt.RUNNING]),
        (sa.always_ok, bt.FAILURE, [bt.SUCCESS]),
        (sa.always_fail, bt.FAILURE, [bt.RUNNING, bt.RUNNING]),
        (sa.always_running, bt.FAILURE, [bt.RUNNING]),
        (sa.run_then_fail, bt.FAILURE, [bt.RUNNING, bt.RUNNING]),
        (sa.run_then_ok, bt.FAILURE, [bt.RUNNING, bt.SUCCESS]),
    ],
)
@bt.runner
def test_repeat(child, continue_if, expected):
    with bt.repeat(child, continue_if) as action:
        for expected_tick_result in expected:
            result = action(None)
            assert result == expected_tick_result


@pytest.mark.xfail
@bt.runner
def test_raises_on_reused_action():
    action = sa.run_then_ok()

    tree = bt.redo(lambda: action)
    with tree as tick:
        tick(None)
        tick(None)
        with pytest.raises(bt.ReusedActionError):
            tick(None)
