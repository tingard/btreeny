import time

import btreeny as bt
import pytest


@pytest.mark.parametrize("dt", (1e8, 2e8, 5e8))
def test_rate_limit_works_1s(dt: float):
    t0 = time.monotonic_ns()
    expected_end = t0 + dt
    with bt.rate_limit(int(dt)):
        pass
    # Assert to within 20% - this is very dependent on the system
    # being used to test
    assert abs(time.monotonic_ns() - expected_end) < dt * 0.2
