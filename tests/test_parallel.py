import pytest
import btreeny as bt

import tests.standard_actions as sa


@pytest.mark.parametrize(
    "children,expected",
    [
        ([sa.always_ok], [bt.SUCCESS]),
        ([sa.always_fail], [bt.FAILURE]),
        ([sa.always_running], [bt.RUNNING]),
        ([sa.always_ok, sa.always_ok], [bt.SUCCESS]),
        ([sa.always_fail, sa.always_ok], [bt.FAILURE]),
        ([sa.always_running, sa.always_ok], [bt.RUNNING]),
        ([sa.always_running, sa.always_fail], [bt.RUNNING]),
        ([sa.always_running, sa.always_running], [bt.RUNNING]),
        ([sa.run_then_ok], [bt.RUNNING, bt.SUCCESS]),
        ([sa.run_then_fail], [bt.RUNNING, bt.FAILURE]),
        ([sa.run_then_ok, sa.always_ok], [bt.RUNNING, bt.SUCCESS]),
        ([sa.run_then_ok, sa.always_fail], [bt.RUNNING, bt.FAILURE]),
        ([sa.run_then_ok, sa.always_running], [bt.RUNNING, bt.RUNNING]),
        ([sa.run_then_fail, sa.always_ok], [bt.RUNNING, bt.FAILURE]),
        ([sa.run_then_fail, sa.always_fail], [bt.RUNNING, bt.FAILURE]),
        ([sa.run_then_ok, sa.run_then_ok], [bt.RUNNING, bt.SUCCESS]),
        ([sa.run_then_fail, sa.run_then_ok], [bt.RUNNING, bt.FAILURE]),
        ([sa.run_then_fail, sa.run_then_fail], [bt.RUNNING, bt.FAILURE]),
    ],
)
@bt.runner
def test_expected_behavior_parallel(children, expected):
    with bt.parallel(*(child() for child in children)) as action:
        for expected_tick_result in expected:
            result = action(None)
            assert result == expected_tick_result


@bt.runner
def test_expected_behavior_deep_parallel():
    expected = [bt.RUNNING, bt.RUNNING, bt.SUCCESS]
    with bt.parallel(
        bt.sequential(sa.run_then_ok(), sa.run_then_ok()),
        bt.sequential(sa.run_then_ok(), sa.run_then_ok()),
    ) as action:
        for expected_tick_result in expected:
            result = action(None)
            assert result == expected_tick_result


@bt.runner
def test_raises_if_ticked_when_done():
    with bt.parallel(sa.always_ok()) as action:
        result = action(None)
        assert result == bt.SUCCESS
        with pytest.raises(bt.BehaviourCompleteError):
            _ = action(None)

@bt.runner
def test_handles_differing_length_chains():
    result = bt.RUNNING
    i = 0
    with bt.parallel(
        bt.redo(sa.run_then_ok, count=3),
        bt.redo(sa.run_then_ok, count=2),
    ) as action:
        while result == bt.RUNNING:
            result = action(None)
            i += 1
    assert i == 3
