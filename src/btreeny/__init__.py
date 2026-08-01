import contextlib
import contextvars
import functools
import hashlib
import itertools
import time
from typing import (
    Callable,
    Concatenate,
    Generator,
    Iterable,
    Iterator,
    Literal,
    ParamSpec,
    ContextManager,
    TypeVar,
)

from ._get_name import get_name
from ._tree_status import TreeStatus
from ._ctx import IdType, update_name
from . import viz, _ctx

BlackboardType = TypeVar("BlackboardType")
TreeTickFunction = Callable[[BlackboardType], TreeStatus]
TreeNode = ContextManager[TreeTickFunction[BlackboardType]]

RUNNING = TreeStatus.RUNNING
SUCCESS = TreeStatus.SUCCESS
FAILURE = TreeStatus.FAILURE

P = ParamSpec("P")
T = TypeVar("T")


class BehaviourCompleteError(RuntimeError):
    pass


@contextlib.contextmanager
def _manage_call_stack(
    node_id: IdType | None, name: str
) -> Generator[IdType, None, None]:
    # When we setup this action, set it on the call stack
    parent = _ctx.call_stack.get()
    _tree_graph = _ctx.tree_graph.get() or {}
    parents_children = _tree_graph.setdefault(parent, [])
    if node_id is None:
        h = hashlib.sha256()
        if parent is None:
            h.update(b"__root")
        else:
            h.update(parent)
        # Encode the number of previous children using a 64-bit big-endigan
        h.update(len(parents_children).to_bytes(length=8, byteorder="big"))
        node_id = h.digest()

    _id_map = _ctx.id_map.get() or {}
    _id_map[node_id] = name
    _ctx.id_map.set(_id_map)
    # parent = None if len(stack) == 0 else stack[-1]
    _ctx.call_stack.set(node_id)
    # Add this to the node graph
    parents_children.append(node_id)
    _ctx.tree_graph.set(_tree_graph)
    try:
        yield node_id
    finally:
        _ctx.call_stack.set(parent)


def action(
    func: Callable[Concatenate[IdType, P], Iterator[TreeTickFunction[BlackboardType]]],
    name: str | None = None,
) -> Callable[P, TreeNode[BlackboardType]]:
    self_name = name if name is not None else get_name(func)

    f = contextlib.contextmanager(func)

    @contextlib.contextmanager
    @functools.wraps(f)
    def inner(*args: P.args, **kwargs: P.kwargs):
        # Each invocation of the action function gets a new ID
        with _manage_call_stack(None, self_name) as managed_node_id:
            with f(managed_node_id, *args, **kwargs) as action:

                @functools.wraps(action)
                def action_func(blackboard: BlackboardType):
                    result = action(blackboard)
                    _tree_status = _ctx.tree_status.get() or {}
                    _tree_status[managed_node_id] = result
                    _ctx.tree_status.set(_tree_status)
                    return result

                yield action_func

    return inner


def simple_action(
    f: TreeTickFunction[BlackboardType],
) -> Callable[[], TreeNode[BlackboardType]]:
    @action
    @functools.wraps(f)
    def _inner(node_id: IdType):
        yield f

    return _inner


@contextlib.contextmanager
def _with_stack_reset(f: TreeNode[BlackboardType]):
    """Reset the stack to a known state before calling the tick function of this child.
    Enables more complex stack manipulation (e.g. as required for `parallel`)

    We try to avoid needing this wrapper as it adds overhead to function calls.
    """
    with f as tick:
        # Set the expected call stack at the start of running this action
        action_stack = _ctx.call_stack.get()

        @functools.wraps(tick)
        def _inner(b: BlackboardType):
            nonlocal action_stack
            # Fetch the current call stack
            current_stack = _ctx.call_stack.get()
            # Set it to the expected value
            _ctx.call_stack.set(action_stack)
            # Call the tick
            result = tick(b)
            # Update the expected stack
            action_stack = _ctx.call_stack.get()
            # Reset before returning
            _ctx.call_stack.set(current_stack)
            return result

        yield _inner
        # Reset to the actions stack so that the action can do teardown properly
        _ctx.call_stack.set(action_stack)


# ------------------------------------------------------------------------------
# Control flow
# ------------------------------------------------------------------------------


@action
def sequential(
    node_id: IdType, *children: TreeNode[BlackboardType]
) -> Iterator[TreeTickFunction[BlackboardType]]:
    def gen() -> Generator[TreeStatus, BlackboardType, None]:
        blackboard = yield TreeStatus.RUNNING
        for child_context_manager in children:
            with child_context_manager as child_action:
                while (result := child_action(blackboard)) == TreeStatus.RUNNING:
                    blackboard = yield TreeStatus.RUNNING
                if result == TreeStatus.FAILURE:
                    yield result
                    return
        yield TreeStatus.SUCCESS
        return

    stepper = gen()
    next(stepper)

    def inner(blackboard: BlackboardType) -> TreeStatus:
        nonlocal stepper
        try:
            return stepper.send(blackboard)
        except StopIteration:
            # Raise an exception if we try to tick the tree when it's finished
            raise BehaviourCompleteError("Ticked a finished behaviour.")

    try:
        yield inner
    finally:
        stepper.close()


@action
def fallback(
    node_id: IdType, *children: TreeNode[BlackboardType]
) -> Iterator[TreeTickFunction[BlackboardType]]:
    def gen() -> Generator[TreeStatus, BlackboardType, None]:
        blackboard = yield TreeStatus.RUNNING
        for child_context_manager in children:
            with child_context_manager as child_action:
                while (result := child_action(blackboard)) == TreeStatus.RUNNING:
                    blackboard = yield TreeStatus.RUNNING
                if result == TreeStatus.SUCCESS:
                    yield result
                    return
        yield TreeStatus.FAILURE
        return

    stepper = gen()
    next(stepper)

    def inner(blackboard: BlackboardType):
        nonlocal stepper
        try:
            return stepper.send(blackboard)
        except StopIteration:
            # Raise an exception if we try to tick the tree when it's finished
            raise BehaviourCompleteError("Ticked a finished behaviour.")

    try:
        yield inner
    finally:
        stepper.close()


@action
def repeat(
    node_id: IdType,
    action_factory: Callable[[], TreeNode[BlackboardType]],
    continue_if: Literal[TreeStatus.SUCCESS, TreeStatus.FAILURE],
    count: int | None = None,
) -> Iterator[TreeTickFunction[BlackboardType]]:
    """Repeat an action while it returns a specific value (success or failure).

    Parameters
    ----------
    action_factory: () -> TreeNode[BlackboardType]
        A function used to generate the action node to repeat. This needs to be a
        function as we perform action setup and teardown on each repeat.
    count: int, default=None
        The number of repeats to try. If `None` then repeat to failure.
    continue_if: TreeStatus.SUCCESS | TreeStatus.FAILURE
        The return value which should trigger a repeat
    """
    # Create children which is an inf
    if count is None:
        children = map(lambda factory: factory(), itertools.repeat(action_factory))
    else:
        children = map(
            lambda factory: factory(), itertools.repeat(action_factory, count)
        )

    def gen() -> Generator[TreeStatus, BlackboardType, None]:
        blackboard = yield TreeStatus.RUNNING
        result = TreeStatus.SUCCESS
        for i, child_context_manager in enumerate(children):
            with child_context_manager as child_action:
                while (result := child_action(blackboard)) == TreeStatus.RUNNING:
                    blackboard = yield TreeStatus.RUNNING
                if result == continue_if:
                    # If this is the last child then return
                    if count is not None and i >= count - 1:
                        yield result
                        return
                    blackboard = yield TreeStatus.RUNNING
                else:
                    yield result
                    return
            # Clear the child tree graph for this node - this will result in child nodes overriding
            # IDs of previous repetitions.
            _ctx.clear_subtree(node_id)
        yield result
        return

    stepper = gen()
    next(stepper)

    def inner(blackboard: BlackboardType):
        nonlocal stepper
        try:
            return stepper.send(blackboard)
        except StopIteration:
            # Raise an exception if we try to tick the tree when it's finished
            raise BehaviourCompleteError("Ticked a finished behaviour.")

    try:
        yield inner
    finally:
        stepper.close()


retry = functools.partial(repeat, continue_if=TreeStatus.FAILURE)
redo = functools.partial(repeat, continue_if=TreeStatus.SUCCESS)


@action
def remap(
    node_id: IdType,
    child: TreeNode[BlackboardType],
    mapping: dict[TreeStatus, TreeStatus],
) -> Iterator[TreeTickFunction[BlackboardType]]:
    with child as action:

        def inner(blackboard: BlackboardType) -> TreeStatus:
            result = action(blackboard)
            return mapping.get(result, result)

        yield inner


@action
def swap(
    node_id: IdType,
    child: TreeNode[BlackboardType],
    *,
    from_: TreeStatus,
    to: TreeStatus,
) -> Iterator[TreeTickFunction[BlackboardType]]:
    if from_ == to:
        raise ValueError(f"Cannot swap {from_} with itself")
    with remap(child, {from_: to, to: from_}) as action:
        yield action


@action
def always_return(
    node_id: IdType,
    child: TreeNode[BlackboardType],
    *,
    always_return: TreeStatus,
) -> Iterator[TreeTickFunction[BlackboardType]]:
    with child as action:

        def inner(blackboard: BlackboardType) -> TreeStatus:
            _ = action(blackboard)
            return always_return

        yield inner


@action
def failsafe(
    node_id: IdType,
    check: Callable[[BlackboardType], bool],
    nominal: TreeNode[BlackboardType],
    failure: TreeNode[BlackboardType],
) -> Iterator[TreeTickFunction[BlackboardType]]:
    """Run a check on each tick, as soon as the check returns ``False`` move from a "nominal"
    mode to an "error" mode.
    """

    def gen() -> Generator[TreeStatus, BlackboardType, None]:
        nonlocal nominal
        blackboard = yield TreeStatus.RUNNING
        result = TreeStatus.SUCCESS
        with nominal as nominal_action:
            while check(blackboard):
                result = nominal_action(blackboard)
                match result:
                    case TreeStatus.RUNNING:
                        blackboard = yield result
                    case _:
                        blackboard = yield result
                        return
            # An interrupt has occurred - we should mark all current RUNNING child nodes as cancelled
            _ctx.cancel_running_children(node_id)
        with failure as failure_action:
            while (result := failure_action(blackboard)) == TreeStatus.RUNNING:
                blackboard = yield TreeStatus.RUNNING
            yield result
            return

    stepper = gen()
    next(stepper)

    def inner(blackboard: BlackboardType):
        nonlocal stepper
        try:
            return stepper.send(blackboard)
        except StopIteration:
            raise BehaviourCompleteError("Ticked a finished behaviour.")

    try:
        yield inner
    finally:
        stepper.close()


def any_running_is_running_allow_max_failures_failures(
    results: Iterable[TreeStatus], max_failures: int = 0
) -> TreeStatus:
    """Given an interable of `TreeStatus` results, return an overall status.

    If any result is `RUNNING`, return `RUNNING`.

    Else if n or more results are `FAILURE`, return `FAILURE`.

    Otherwise return `SUCCESS`.
    """
    n_failing = 0
    for result in results:
        match result:
            case TreeStatus.FAILURE:
                n_failing += 1
            case TreeStatus.RUNNING:
                return TreeStatus.RUNNING
    if n_failing > max_failures:
        return TreeStatus.FAILURE
    return TreeStatus.SUCCESS


@action
def parallel(
    node_id: IdType,
    *children: TreeNode[BlackboardType],
    result_evaluation_function: Callable[
        [list[TreeStatus]], TreeStatus
    ] = any_running_is_running_allow_max_failures_failures,
) -> Iterator[TreeTickFunction[BlackboardType]]:
    """Evaluate multiple nodes in parallel.

    The result type is determined by the provided `result_evaluation_function`, which defaults
    to a FAILURE if, when all actions have finished running, one or more have returned `FAILURE`.
    """

    with contextlib.ExitStack() as stack:
        # We need to be the "parent" of all of these functions
        tick_functions = []
        this_stack = _ctx.call_stack.get()
        for child in children:
            # Reset the call stack
            _ctx.call_stack.set(this_stack)
            # use the _with_stack_reset wrapper to make sure this child manages its call stack properly
            tick_functions.append(stack.enter_context(_with_stack_reset(child)))
        latched: list[TreeStatus | None] = [None for _ in range(len(tick_functions))]
        is_done = False

        def _inner(blackboard: BlackboardType):
            nonlocal is_done
            if is_done:
                raise BehaviourCompleteError("Ticked a finished behaviour.")
            results: list[TreeStatus] = []
            for i, func in enumerate(tick_functions):
                if (prev := latched[i]) is not None:
                    results.append(prev)
                    continue
                r = func(blackboard)
                if r != TreeStatus.RUNNING:
                    latched[i] = r
                results.append(r)
            result = result_evaluation_function(results)
            is_done = result != TreeStatus.RUNNING
            return result

        yield _inner


def runner(f: Callable[P, T]) -> Callable[P, T]:
    @functools.wraps(f)
    def _inner(*a: P.args, **k: P.kwargs) -> T:
        def reset_then_run() -> T:
            _ctx.reset()
            return f(*a, **k)

        ctx = contextvars.copy_context()
        return ctx.run(reset_then_run)

    return _inner


@contextlib.contextmanager
def rate_limit(period_ns: int):
    tick_start = time.monotonic_ns()
    tick_end = tick_start + period_ns
    yield
    # Wait until the expected end time
    time.sleep(max(0, tick_end - time.monotonic_ns()) / 1e9)


__all__ = (
    "action",
    "always_return",
    "failsafe",
    "fallback",
    "IdType",
    "parallel",
    "rate_limit",
    "redo",
    "remap",
    "repeat",
    "retry",
    "runner",
    "sequential",
    "simple_action",
    "swap",
    "TreeStatus",
    "update_name",
    "viz",
)
