import contextlib
from copy import deepcopy
import functools
import itertools
from typing import (
    Callable,
    Generator,
    Iterable,
    Iterator,
    Literal,
    ParamSpec,
    ContextManager,
    TypeVar,
)
import uuid

from ._get_name import get_name
from ._tree_status import TreeStatus
from ._ctx import (
    call_stack as __ctx_call_stack,
    tree_graph as __ctx_tree_graph,
    id_map as __ctx_id_map,
    tree_status as __ctx_tree_status,
)

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
def _manage_call_stack(id: uuid.UUID, name: str):
    _id_map = deepcopy(__ctx_id_map.get())
    _id_map[id] = name
    __ctx_id_map.set(_id_map)
    # When we setup this action, set it on the call stack
    parent = __ctx_call_stack.get()
    # parent = None if len(stack) == 0 else stack[-1]
    __ctx_call_stack.set(id)
    # Add this to the node graph
    _tree_graph = __ctx_tree_graph.get()
    parents_children = _tree_graph.setdefault(parent, [])
    parents_children.append(id)
    __ctx_tree_graph.set(_tree_graph)
    yield
    __ctx_call_stack.set(parent)


def action(
    func: Callable[P, Iterator[TreeTickFunction[BlackboardType]]],
    name: str | None = None,
) -> Callable[P, TreeNode[BlackboardType]]:
    self_name = name if name is not None else get_name(func)

    f = contextlib.contextmanager(func)

    @contextlib.contextmanager
    @functools.wraps(f)
    def inner(*args: P.args, **kwargs: P.kwargs):
        # Each invocation of the action function gets a new ID
        self_id = uuid.uuid4()
        with _manage_call_stack(self_id, self_name):
            with f(*args, **kwargs) as action:

                @functools.wraps(action)
                def action_func(blackboard: BlackboardType):
                    result = action(blackboard)
                    _tree_status = __ctx_tree_status.get()
                    _tree_status[self_id] = result
                    __ctx_tree_status.set(_tree_status)
                    return result

                yield action_func

    return inner


def simple_action(f: TreeTickFunction[BlackboardType]):
    @action
    @functools.wraps(f)
    def _inner():
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
        action_stack = __ctx_call_stack.get()

        @functools.wraps(tick)
        def _inner(b: BlackboardType):
            nonlocal action_stack
            # Fetch the current call stack
            current_stack = __ctx_call_stack.get()
            # Set it to the expected value
            __ctx_call_stack.set(action_stack)
            # Call the tick
            result = tick(b)
            # Update the expected stack
            action_stack = __ctx_call_stack.get()
            # Reset before returning
            __ctx_call_stack.set(current_stack)
            return result

        yield _inner
        # Reset to the actions stack so that the action can do teardown properly
        __ctx_call_stack.set(action_stack)


# ------------------------------------------------------------------------------
# Control flow
# ------------------------------------------------------------------------------


@action
def sequential(*children: TreeNode[BlackboardType]):
    def gen() -> Generator[TreeStatus, BlackboardType, None]:
        blackboard = yield TreeStatus.RUNNING
        for child_context_manager in children:
            with child_context_manager as child_action:
                # TODO: Pyrefly is not happy with blackboard typing - why?
                while (
                    result := child_action(blackboard)  # pyrefly: ignore
                ) == TreeStatus.RUNNING:
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
def fallback(*children: TreeNode[BlackboardType]):
    def gen() -> Generator[TreeStatus, BlackboardType, None]:
        blackboard = yield TreeStatus.RUNNING
        for child_context_manager in children:
            with child_context_manager as child_action:
                # TODO: Pyrefly is not happy with blackboard typing - why?
                while (
                    result := child_action(blackboard)  # pyrefly: ignore
                ) == TreeStatus.RUNNING:
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
    action_factory: Callable[[], TreeNode[BlackboardType]],
    continue_if: Literal[TreeStatus.SUCCESS, TreeStatus.FAILURE],
    count: int | None = None,
):
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
    child: TreeNode[BlackboardType],
    mapping: dict[TreeStatus, TreeStatus],
):
    with child as action:

        def inner(blackboard: BlackboardType) -> TreeStatus:
            result = action(blackboard)
            return mapping.get(result, result)

        yield inner


@action
def swap(
    child: TreeNode[BlackboardType],
    *,
    from_: TreeStatus,
    to: TreeStatus,
):
    if from_ == to:
        raise ValueError(f"Cannot swap {from_} with itself")
    with remap(child, {from_: to, to: from_}) as action:
        yield action


@action
def always_return(
    child: TreeNode[BlackboardType],
    *,
    always_return: TreeStatus,
):
    with child as action:

        def inner(blackboard: BlackboardType) -> TreeStatus:
            _ = action(blackboard)
            return always_return

        yield inner


@action
def failsafe(
    check: Callable[[BlackboardType], bool],
    nominal: TreeNode[BlackboardType],
    failure: TreeNode[BlackboardType],
):
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
                        yield result
                    case _:
                        yield result
                        return
        with failure as failure_action:
            while (
                result := failure_action(blackboard)  # pyrefly: ignore
            ) == TreeStatus.RUNNING:
                blackboard = yield TreeStatus.RUNNING
            yield result
            return
        yield TreeStatus.SUCCESS
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
    *children: TreeNode[BlackboardType],
    result_evaluation_function: Callable[
        [list[TreeStatus]], TreeStatus
    ] = any_running_is_running_allow_max_failures_failures,
):
    """Evaluate multiple nodes in parallel.

    The result type is determined by the provided `result_evaluation_function`, which defaults
    to a FAILURE if, when all actions have finished running, one or more have returned `FAILURE`.
    """

    with contextlib.ExitStack() as stack:
        # We need to be the "parent" of all of these functions
        tick_functions = []
        this_stack = __ctx_call_stack.get()
        for child in children:
            # Reset the call stack
            __ctx_call_stack.set(this_stack)
            # use the _with_stack_reset wrapper to make sure this child manages its call stack properly
            tick_functions.append(stack.enter_context(_with_stack_reset(child)))
        is_done = False

        def _inner(blackboard: BlackboardType):
            nonlocal is_done
            if is_done:
                raise BehaviourCompleteError("Ticked a finished behaviour.")
            results = [func(blackboard) for func in tick_functions]
            result = result_evaluation_function(results)
            is_done = result != RUNNING
            return result

        yield _inner
