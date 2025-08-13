import pytest
import btreeny as bt

import tests.standard_actions as sa


@pytest.mark.parametrize(
    "children,expected",
    [
        # Sequential
        ([sa.always_ok], [bt.SUCCESS]),
        ([sa.always_fail], [bt.FAILURE]),
        ([sa.always_running], [bt.RUNNING]),
        ([sa.always_ok, sa.always_ok], [bt.SUCCESS]),
        ([sa.always_ok, sa.always_fail], [bt.FAILURE]),
        ([sa.always_ok, sa.always_running], [bt.RUNNING]),
        ([sa.always_fail, sa.never_runs], [bt.FAILURE]),
        ([sa.always_running, sa.never_runs], [bt.RUNNING]),
        ([sa.run_then_ok], [bt.RUNNING, bt.SUCCESS]),
        ([sa.run_then_fail], [bt.RUNNING, bt.FAILURE]),
        ([sa.run_then_ok, sa.always_ok], [bt.RUNNING, bt.SUCCESS]),
        ([sa.run_then_ok, sa.always_fail], [bt.RUNNING, bt.FAILURE]),
        ([sa.run_then_fail, sa.never_runs], [bt.RUNNING, bt.FAILURE]),
        ([sa.run_then_ok, sa.run_then_ok], [bt.RUNNING, bt.RUNNING, bt.SUCCESS]),
        ([sa.run_then_ok, sa.run_then_fail], [bt.RUNNING, bt.RUNNING, bt.FAILURE]),
    ],
)
def test_expected_behavior_sequential(children, expected):
    with bt.sequential(*(child() for child in children)) as action:
        for expected_tick_result in expected:
            result = action(None)
            assert result == expected_tick_result


def test_raises_if_ticked_when_done():
    with bt.fallback(sa.always_ok()) as action:
        result = action(None)
        assert result == bt.SUCCESS
        with pytest.raises(bt.BehaviourCompleteError):
            _ = action(None)
