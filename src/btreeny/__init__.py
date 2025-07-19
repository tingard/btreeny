from collections import deque
import contextlib
import contextvars
from copy import deepcopy
from enum import Enum
import functools
import itertools
from typing import Any, Callable, Generator, Iterator, Literal, ParamSpec, ContextManager, TypeVar, cast
import uuid

from ._tree_status import TreeStatus
from ._ctx import (
    call_stack as __ctx_call_stack,
    tree_graph as __ctx_tree_graph,
    id_map as __ctx_id_map,
    tree_status as __ctx_tree_status,
)

BlackboardType = TypeVar("BlackboardType")

P = ParamSpec("P")
T = TypeVar("T")



def get_name(obj: Any) -> str:
    if (name := getattr(obj, "__name__", None)) is not None:
        return name
    elif (cls := getattr(obj, "__class__", None)) is not None:
        return getattr(cls, "__name__", str(obj))
    return str(obj)


def action(func: Callable[P, Iterator[Callable[[BlackboardType], TreeStatus]]]):
    self_name = get_name(func)

    f = contextlib.contextmanager(func)
    @contextlib.contextmanager
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
        should_gen_exit = False
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
        if should_gen_exit:
            raise GeneratorExit
    return inner

def simple_action(f: Callable[[BlackboardType], TreeStatus]):
    @action
    def _inner():
        yield f
    return _inner

@action
def sequential(*children: ContextManager[Callable[[BlackboardType], TreeStatus]]):
    def gen():
        blackboard = yield TreeStatus.RUNNING
        for child_context_manager in children:
            with child_context_manager as child_action:
                while (result := child_action(blackboard)) == TreeStatus.RUNNING:
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
            return e.value
    yield inner

@action
def fallback(*children: ContextManager[Callable[[BlackboardType], TreeStatus]]):
    def gen():
        blackboard = yield TreeStatus.RUNNING
        for child_context_manager in children:
            with child_context_manager as child_action:
                while (result := child_action(blackboard)) == TreeStatus.RUNNING:
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
    yield inner
    stepper.close()


@action
def repeat(
    action_factory: Callable[[], ContextManager[Callable[[BlackboardType], TreeStatus]]],
    count: int | None = None,
):
    # Create children which is an inf
    if count is None:
        children = map(lambda factory: factory(), itertools.repeat(action_factory))
    else:
        children = map(lambda factory: factory(), itertools.repeat(action_factory, count))
    def gen() -> Generator[TreeStatus, BlackboardType, TreeStatus]:
        blackboard = yield TreeStatus.RUNNING
        result = TreeStatus.SUCCESS
        for i, child_context_manager in enumerate(children):
            with child_context_manager as child_action:
                while (result := child_action(blackboard)) == TreeStatus.RUNNING:
                    blackboard = yield TreeStatus.RUNNING
                if result == TreeStatus.SUCCESS:
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
    yield inner
    # TODO: Cleanup currently open action
    stepper.close()

@action
def remap(
    child: ContextManager[Callable[[BlackboardType], TreeStatus]],
    mapping: dict[TreeStatus, TreeStatus],
):
    with child as action:
        def inner(blackboard: BlackboardType) -> TreeStatus:
            result = action(blackboard)
            return mapping.get(result, result)
        yield inner


@action
def swap(
    child: ContextManager[Callable[[BlackboardType], TreeStatus]],
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
    nominal: ContextManager[Callable[[BlackboardType], TreeStatus]],
    failure: ContextManager[Callable[[BlackboardType], TreeStatus]],
):
    """A react node allows highly reactive behavior, switching between multiple actions
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
        nonlocal nominal_call_stack, failure_call_stack, nominal_graph, failure_graph, mode
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
    yield inner
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

def print_trace():
    _id_map = __ctx_id_map.get()
    _tree_graph = __ctx_tree_graph.get()
    _tree_status = __ctx_tree_status.get()
    root_actions = _tree_graph[None]
    q = deque()
    print(f'\n{" Trace ":-^50}')
    for action_id in root_actions:
        q.append((action_id, 0))
    while len(q) > 0:
        action_id, indent_count = q.popleft()
        indent = ' ' * indent_count * 4
        action_name = _id_map[action_id]
        action_status = _tree_status.get(action_id, None)
        if action_status is not None:
            action_status = action_status.value
        print(f"{indent}{action_id} {action_name} - {action_status}")
        for child in _tree_graph.get(action_id, [])[::-1]:
            q.appendleft((child, indent_count + 1))
    print('-'*50 + '\n')
