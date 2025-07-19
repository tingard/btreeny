import contextlib
from copy import deepcopy
import functools
import itertools
from typing import (
    Any,
    Callable,
    Generator,
    Iterator,
    Literal,
    ParamSpec,
    ContextManager,
    TypeVar,
    cast,
)
import uuid

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

P = ParamSpec("P")
T = TypeVar("T")


def get_name(obj: Any) -> str:
    if (name := getattr(obj, "__name__", None)) is not None:
        return name
    elif (cls := getattr(obj, "__class__", None)) is not None:
        return getattr(cls, "__name__", str(obj))
    return str(obj)


def action(
    func: Callable[P, Iterator[TreeTickFunction[BlackboardType]]],
) -> Callable[P, TreeNode[BlackboardType]]:
    self_name = get_name(func)

    f = contextlib.contextmanager(func)

    @contextlib.contextmanager
    @functools.wraps(f)
    def inner(*args: P.args, **kwargs: P.kwargs):
        # Each invocation of the action function gets a new ID
        self_id = uuid.uuid4()
        # Store the ID
        _id_map = deepcopy(__ctx_id_map.get())
        _id_map[self_id] = self_name
        __ctx_id_map.set(_id_map)
        # When we setup this action, set it on the call stack
        stack = __ctx_call_stack.get()
        parent = None if len(stack) == 0 else stack[-1]
        __ctx_call_stack.set(stack + [self_id])

        _tree_graph = deepcopy(__ctx_tree_graph.get())
        if parent not in _tree_graph:
            _tree_graph[parent] = []
        _tree_graph[parent].append(self_id)
        __ctx_tree_graph.set(_tree_graph)
        with f(*args, **kwargs) as action:

            @functools.wraps(action)
            def action_func(blackboard: BlackboardType):
                result = action(blackboard)
                _tree_status = deepcopy(__ctx_tree_status.get())
                _tree_status[self_id] = result
                __ctx_tree_status.set(_tree_status)
                return result

            yield action_func

        # Drain all values including and after this ID from the stack
        # Raises ValueError if ID not in stack
        stack = __ctx_call_stack.get()
        id_in_stack = stack.index(self_id)
        __ctx_call_stack.set(stack[:id_in_stack])

    return inner


def simple_action(f: TreeTickFunction[BlackboardType]):
    @action
    @functools.wraps(f)
    def _inner():
        yield f

    return _inner


@action
def sequential(*children: TreeNode[BlackboardType]):
    def gen() -> Generator[TreeStatus, BlackboardType, TreeStatus]:
        blackboard = yield TreeStatus.RUNNING
        for child_context_manager in children:
            with child_context_manager as child_action:
                # TODO: Pyrefly is not happy with blackboard typing - why?
                while (
                    result := child_action(blackboard)  # pyrefly: ignore
                ) == TreeStatus.RUNNING:
                    blackboard = yield TreeStatus.RUNNING
                if result == TreeStatus.FAILURE:
                    return result
        return TreeStatus.SUCCESS

    stepper = gen()
    next(stepper)

    def inner(blackboard: BlackboardType) -> TreeStatus:
        nonlocal stepper
        try:
            return stepper.send(blackboard)
        except StopIteration as e:
            return cast(TreeStatus, e.value)

    try:
        yield inner
    finally:
        stepper.close()


@action
def fallback(*children: TreeNode[BlackboardType]):
    def gen() -> Generator[TreeStatus, BlackboardType, TreeStatus]:
        blackboard = yield TreeStatus.RUNNING
        for child_context_manager in children:
            with child_context_manager as child_action:
                # TODO: Pyrefly is not happy with blackboard typing - why?
                while (
                    result := child_action(blackboard)  # pyrefly: ignore
                ) == TreeStatus.RUNNING:
                    blackboard = yield TreeStatus.RUNNING
                if result == TreeStatus.SUCCESS:
                    return result
        return TreeStatus.FAILURE

    stepper = gen()
    next(stepper)

    def inner(blackboard: BlackboardType):
        nonlocal stepper
        try:
            return stepper.send(blackboard)
        except StopIteration as e:
            return cast(TreeStatus, e.value)

    try:
        yield inner
    finally:
        stepper.close()


@action
def repeat(
    action_factory: Callable[[], TreeNode[BlackboardType]],
    count: int | None = None,
    continue_if: Literal[TreeStatus.SUCCESS, TreeStatus.FAILURE] = TreeStatus.SUCCESS,
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

    def gen() -> Generator[TreeStatus, BlackboardType, TreeStatus]:
        blackboard = yield TreeStatus.RUNNING
        result = TreeStatus.SUCCESS
        for i, child_context_manager in enumerate(children):
            with child_context_manager as child_action:
                while (result := child_action(blackboard)) == TreeStatus.RUNNING:
                    blackboard = yield TreeStatus.RUNNING
                if result == continue_if:
                    # If this is the last child then return
                    if count is not None and i >= count - 1:
                        return result
                    blackboard = yield TreeStatus.RUNNING
                else:
                    return result
        return result

    stepper = gen()
    next(stepper)

    def inner(blackboard: BlackboardType):
        nonlocal stepper
        try:
            return stepper.send(blackboard)
        except StopIteration as e:
            return cast(TreeStatus, e.value)

    try:
        yield inner
    finally:
        stepper.close()


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
    from_: TreeStatus,
    to: TreeStatus,
):
    if from_ == to:
        raise ValueError(f"Cannot swap {from_} with itself")
    with child as action:

        def inner(blackboard: BlackboardType) -> TreeStatus:
            result = action(blackboard)
            if result == from_:
                return to
            elif result == to:
                return from_
            return result

        yield inner


@action
def react(
    condition: Callable[[BlackboardType], bool],
    nominal: TreeNode[BlackboardType],
    failure: TreeNode[BlackboardType],
):
    """A react node allows highly reactive behavior, switching between multiple
    actions depending on the currently evaluated state of the `condition` function.

    Parameters
    ----------
    condition: (BlackboardType) -> bool
        The function to call to determine if we are in the "nominal" or "failure" mode
    nominal: Tree
    """
    # We need to carefully manage the call stack, inserting and removing children
    # as we switch between modes
    initial_call_stack = __ctx_call_stack.get()
    initial_graph = __ctx_tree_graph.get()
    # Get the failure call stack
    failure_action = failure.__enter__()
    failure_call_stack = __ctx_call_stack.get()
    failure_graph = __ctx_tree_graph.get()
    __ctx_call_stack.set(initial_call_stack)
    __ctx_tree_graph.set(initial_graph)
    # Get the nominal call stack
    nominal_action = nominal.__enter__()
    nominal_call_stack = __ctx_call_stack.get()
    nominal_graph = __ctx_tree_graph.get()
    # Intial mode is nominal
    mode: Literal["nominal", "failure"] = "nominal"

    def inner(blackboard: BlackboardType) -> TreeStatus:
        nonlocal \
            nominal_call_stack, \
            failure_call_stack, \
            nominal_graph, \
            failure_graph, \
            mode
        match (mode, condition(blackboard)):
            # Mode is nominal, condtion passes
            case ("nominal", True):
                # Run the nominal action
                return nominal_action(blackboard)
            # Mode is nominal, condtion failes - transition to fail
            case ("nominal", False):
                mode = "failure"
                # Update the nominal call stack
                nominal_call_stack = __ctx_call_stack.get()
                nominal_graph = __ctx_tree_graph.get()
                # Set the current call stack as the failure stack
                __ctx_call_stack.set(failure_call_stack)
                __ctx_tree_graph.set(failure_graph)
                # Run the failure action
                return failure_action(blackboard)
            # Mode is failure, but the condition has started passing - transition to nominal
            case ("failure", True):
                mode = "nominal"
                failure_call_stack = __ctx_call_stack.get()
                failure_graph = __ctx_tree_graph.get()
                __ctx_call_stack.set(nominal_call_stack)
                __ctx_tree_graph.set(nominal_graph)
                return nominal_action(blackboard)
            # Mode is failure and the condition is failing
            case ("failure", False):
                return failure_action(blackboard)
            case _:
                raise RuntimeError("Impossible branch")

    try:
        yield inner
    finally:
        # Cleanup - being careful to reset stack as appropriate
        match mode:
            case "nominal":
                nominal.__exit__(None, None, None)
                __ctx_call_stack.set(failure_call_stack)
                failure.__exit__(None, None, None)
            case "failure":
                failure.__exit__(None, None, None)
                __ctx_call_stack.set(nominal_call_stack)
                nominal.__exit__(None, None, None)
