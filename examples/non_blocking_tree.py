from concurrent.futures import Future, ThreadPoolExecutor, CancelledError, TimeoutError
from dataclasses import dataclass
import functools
import logging
from rich.live import Live
import time

import btreeny as bt


@dataclass
class Blackboard:
    pool: ThreadPoolExecutor
    logger: logging.Logger = logging.getLogger(__file__)


def slow_task(n: float):
    time.sleep(n)
    return True


@bt.action
def long_running_action(node_id: bytes, n: int):
    bt.update_name(node_id, f"spawn_task_{n}")

    _current_response: Future[bool] | None = None

    def _inner(blackboard: Blackboard) -> bt.TreeStatus:
        nonlocal _current_response
        if _current_response is None:
            blackboard.logger.debug("[%s] Running slow_task for: %s", node_id.hex, n)
            _current_response = blackboard.pool.submit(functools.partial(slow_task, n))
            return bt.RUNNING
        if not _current_response.done():
            return bt.RUNNING
        try:
            result = _current_response.result(timeout=0)
            blackboard.logger.debug("[%s] Received %s", node_id.hex, result)
        except CancelledError:
            blackboard.logger.warning(
                "[%s] Future was cancelled", node_id, exc_info=True
            )
            return bt.FAILURE
        except TimeoutError:
            return bt.RUNNING
        return bt.SUCCESS

    yield _inner


@bt.simple_action
def print_done(*a):
    print("Done")
    return bt.SUCCESS


@bt.runner
def main():
    root = bt.redo(
        lambda: bt.sequential(
            bt.parallel(
                long_running_action(1),
                # long_running_action(4),
                long_running_action(2),
                long_running_action(3),
            ),
            print_done(),
        ),
        count=2,
    )
    # By setting the pool size to smaller than the number of parallel tasks, we
    # see the scheduling affect completion times in the printed tree - the 3rd
    # and 4th tasks need to wait for previous tasks to complete, despite having
    # shorter run durations
    blackboard = Blackboard(pool=ThreadPoolExecutor(max_workers=2))
    blackboard.logger.setLevel(logging.DEBUG)
    result = bt.RUNNING
    with Live(auto_refresh=False) as live, root as tick:
        while result == bt.RUNNING:
            # Tick at 1hz
            with bt.rate_limit(10**9):
                result = tick(blackboard)
                live.update(bt.viz.get_rich_tree(), refresh=True)


if __name__ == "__main__":
    logging.getLogger(__file__).setLevel(logging.DEBUG)
    main()
