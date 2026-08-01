import pytest
import btreeny as bt
import tests.standard_actions as sa


@pytest.mark.xfail
@bt.runner
def test_raises_if_action():
    action = sa.run_then_ok()

    with action as tick:
        tick(None)

    # Attempting to get a tick function raises. We do not currently
    # have a good way to capture this and change the returned error
    with pytest.raises(bt.ReusedActionError):
        with action as tick:
            tick(None)
