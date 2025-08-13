from dataclasses import dataclass
from typing import Any
import pytest
import btreeny as bt

import tests.standard_actions as sa


@dataclass
class CountingBlackboard:
    count: int = 0


def check_always_true(b: Any):
    return True


def check_always_false(b: Any):
    return False


def check_false_after_count(b: CountingBlackboard, max_count: int = 1):
    return b.count < max_count


@pytest.mark.parametrize(
    "check,nominal,failure,expected",
    [
        (check_always_true, sa.always_ok, sa.never_runs, [bt.SUCCESS]),
        (check_always_true, sa.always_fail, sa.never_runs, [bt.FAILURE]),
        (check_always_true, sa.always_running, sa.never_runs, [bt.RUNNING, bt.RUNNING]),
        (check_always_false, sa.never_runs, sa.always_ok, [bt.SUCCESS]),
        (check_always_false, sa.never_runs, sa.always_fail, [bt.FAILURE]),
        (
            check_always_false,
            sa.never_runs,
            sa.always_running,
            [bt.RUNNING, bt.RUNNING],
        ),
        (check_false_after_count, sa.always_fail, sa.never_runs, [bt.FAILURE]),
        (
            check_false_after_count,
            sa.run_then_fail,
            sa.always_ok,
            [bt.RUNNING, bt.SUCCESS],
        ),
        (
            check_false_after_count,
            sa.run_then_fail,
            sa.run_then_ok,
            [bt.RUNNING, bt.RUNNING, bt.SUCCESS],
        ),
    ],
)
def test_failsafe(check, nominal, failure, expected):
    b = CountingBlackboard()
    with bt.failsafe(check, nominal(), failure()) as action:
        for expected_tick_result in expected:
            result = action(b)
            assert result == expected_tick_result
            b.count += 1


def test_raises_if_ticked_when_done():
    with bt.failsafe(check_always_true, sa.always_ok(), sa.always_ok()) as action:
        result = action(None)
        assert result == bt.SUCCESS
        with pytest.raises(bt.BehaviourCompleteError):
            _ = action(None)
