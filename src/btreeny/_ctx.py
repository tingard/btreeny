import contextvars
from ._tree_status import TreeStatus

IdType = bytes

id_map = contextvars.ContextVar[dict[IdType, str] | None]("call_stack", default=None)
call_stack = contextvars.ContextVar[IdType | None]("call_stack", default=None)
tree_graph = contextvars.ContextVar[dict[IdType | None, list[IdType]] | None](
    "tree_graph", default=None
)
tree_status = contextvars.ContextVar[dict[IdType, TreeStatus] | None](
    "tree_status", default=None
)
