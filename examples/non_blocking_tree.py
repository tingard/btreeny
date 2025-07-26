from concurrent.futures import Future, ThreadPoolExecutor, CancelledError, TimeoutError
from dataclasses import dataclass
import functools
import logging
from rich.live import Live
import time

import btreeny
import btreeny.viz


@dataclass
class Blackboard:
    pool: ThreadPoolExecutor
    logger: logging.Logger = logging.getLogger(__file__)


def slow_task(n: float):
    time.sleep(n)
    return True


def spawn_task(n: float):
    _current_response: Future[bool] | None = None

    def _inner(blackboard: Blackboard) -> btreeny.TreeStatus:
        nonlocal _current_response
        if _current_response is None:
            blackboard.logger.debug("Running slow_task for: %s", n)
            _current_response = blackboard.pool.submit(functools.partial(slow_task, n))
            return btreeny.RUNNING
        if not _current_response.done():
            return btreeny.RUNNING
        try:
            result = _current_response.result(timeout=0)
            blackboard.logger.debug("Received %s", result)
        except CancelledError:
            blackboard.logger.warning("Future was cancelled", exc_info=True)
            return btreeny.FAILURE
        except TimeoutError:
            return btreeny.RUNNING
        return btreeny.SUCCESS

    yield _inner


def main():
    root = btreeny.redo(
        lambda: btreeny.parallel(
            # Slightly hacky way of altering task names to reflect params
            btreeny.action(spawn_task, name="spawn_task_1")(1),
            btreeny.action(spawn_task, name="spawn_task_4")(4),
            btreeny.action(spawn_task, name="spawn_task_2")(2),
            btreeny.action(spawn_task, name="spawn_task_3")(3),
        ),
        count=2,
    )
    # By setting the pool size to smaller than the number of parallel tasks, we
    # see the scheduling affect completion times in the printed tree - the 3rd
    # and 4th tasks need to wait for previous tasks to complete, despite having
    # shorter run durations
    blackboard = Blackboard(pool=ThreadPoolExecutor(max_workers=2))
    blackboard.logger.setLevel(logging.DEBUG)
    result = btreeny.RUNNING
    with Live() as live, root as tick:
        while result == btreeny.RUNNING:
            result = tick(blackboard)
            live.update(btreeny.viz.get_rich_tree())
            time.sleep(0.1)


if __name__ == "__main__":
    import contextvars

    ctx = contextvars.copy_context()
    logging.getLogger(__file__).setLevel(logging.DEBUG)
    ctx.run(main)
