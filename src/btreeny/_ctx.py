import contextvars
import functools
import uuid
from typing import Callable, ParamSpec, TypeVar
from .tree_status import TreeStatus

P = ParamSpec("P")
T = TypeVar("T")

# A node identifier is (parent_name, action_name, child_index)
# NodeIdent = tuple[str, str, int]

id_map = contextvars.ContextVar[dict[uuid.UUID, str]]("call_stack", default={})
call_stack = contextvars.ContextVar[uuid.UUID | None]("call_stack", default=None)
tree_graph = contextvars.ContextVar[dict[uuid.UUID | None, list[uuid.UUID]]](
    "tree_graph", default={}
)
tree_status = contextvars.ContextVar[dict[uuid.UUID, TreeStatus]](
    "tree_status", default={}
)


def runner(f: Callable[P, T]) -> Callable[[], T]:
    ctx = contextvars.copy_context()

    @functools.wraps(f)
    def _inner(*a, **k):
        functools.partial(f, *a, **k)
        return ctx.run(functools.partial(f, *a, **k))

    return _inner
