import pytest
import btreeny as bt

import tests.standard_actions as sa


@pytest.mark.parametrize(
    "map_from,map_to,child,expected",
    [
        (bt.SUCCESS, bt.SUCCESS, sa.always_ok, [bt.SUCCESS]),
        (bt.SUCCESS, bt.FAILURE, sa.always_ok, [bt.FAILURE]),
        (bt.SUCCESS, bt.RUNNING, sa.always_ok, [bt.RUNNING]),
        (bt.FAILURE, bt.SUCCESS, sa.always_ok, [bt.SUCCESS]),
        (bt.FAILURE, bt.FAILURE, sa.always_ok, [bt.SUCCESS]),
        (bt.FAILURE, bt.RUNNING, sa.always_ok, [bt.SUCCESS]),
        (bt.RUNNING, bt.SUCCESS, sa.always_ok, [bt.SUCCESS]),
        (bt.RUNNING, bt.FAILURE, sa.always_ok, [bt.SUCCESS]),
        (bt.RUNNING, bt.RUNNING, sa.always_ok, [bt.SUCCESS]),
        (bt.SUCCESS, bt.SUCCESS, sa.always_fail, [bt.FAILURE]),
        (bt.SUCCESS, bt.FAILURE, sa.always_fail, [bt.FAILURE]),
        (bt.SUCCESS, bt.RUNNING, sa.always_fail, [bt.FAILURE]),
        (bt.FAILURE, bt.SUCCESS, sa.always_fail, [bt.SUCCESS]),
        (bt.FAILURE, bt.FAILURE, sa.always_fail, [bt.FAILURE]),
        (bt.FAILURE, bt.RUNNING, sa.always_fail, [bt.RUNNING]),
        (bt.RUNNING, bt.SUCCESS, sa.always_fail, [bt.FAILURE]),
        (bt.RUNNING, bt.FAILURE, sa.always_fail, [bt.FAILURE]),
        (bt.RUNNING, bt.RUNNING, sa.always_fail, [bt.FAILURE]),
        (bt.SUCCESS, bt.SUCCESS, sa.always_running, [bt.RUNNING]),
        (bt.SUCCESS, bt.FAILURE, sa.always_running, [bt.RUNNING]),
        (bt.SUCCESS, bt.RUNNING, sa.always_running, [bt.RUNNING]),
        (bt.FAILURE, bt.SUCCESS, sa.always_running, [bt.RUNNING]),
        (bt.FAILURE, bt.FAILURE, sa.always_running, [bt.RUNNING]),
        (bt.FAILURE, bt.RUNNING, sa.always_running, [bt.RUNNING]),
        (bt.RUNNING, bt.SUCCESS, sa.always_running, [bt.SUCCESS]),
        (bt.RUNNING, bt.FAILURE, sa.always_running, [bt.FAILURE]),
        (bt.RUNNING, bt.RUNNING, sa.always_running, [bt.RUNNING]),
    ],
)
def test_single_remap(map_from, map_to, child, expected):
    with bt.remap(child(), {map_from: map_to}) as action:
        for expected_tick_result in expected:
            result = action(None)
            assert result == expected_tick_result


@pytest.mark.parametrize(
    "map_from,map_to,child,expected",
    [
        (bt.SUCCESS, bt.FAILURE, sa.always_ok, [bt.FAILURE]),
        (bt.SUCCESS, bt.RUNNING, sa.always_ok, [bt.RUNNING]),
        (bt.RUNNING, bt.FAILURE, sa.always_ok, [bt.SUCCESS]),
        (bt.SUCCESS, bt.FAILURE, sa.always_fail, [bt.SUCCESS]),
        (bt.SUCCESS, bt.RUNNING, sa.always_fail, [bt.FAILURE]),
        (bt.RUNNING, bt.FAILURE, sa.always_fail, [bt.RUNNING]),
        (bt.SUCCESS, bt.FAILURE, sa.always_running, [bt.RUNNING]),
        (bt.SUCCESS, bt.RUNNING, sa.always_running, [bt.SUCCESS]),
        (bt.RUNNING, bt.FAILURE, sa.always_running, [bt.FAILURE]),
    ],
)
def test_swap(map_from, map_to, child, expected):
    with bt.swap(child(), from_=map_from, to=map_to) as action:
        for expected_tick_result in expected:
            result = action(None)
            assert result == expected_tick_result
