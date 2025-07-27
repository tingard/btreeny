import contextvars
import uuid
from ._tree_status import TreeStatus

id_map = contextvars.ContextVar[dict[uuid.UUID, str]]("call_stack", default={})
call_stack = contextvars.ContextVar[uuid.UUID | None]("call_stack", default=None)
tree_graph = contextvars.ContextVar[dict[uuid.UUID | None, list[uuid.UUID]]](
    "tree_graph", default={}
)
tree_status = contextvars.ContextVar[dict[uuid.UUID, TreeStatus]](
    "tree_status", default={}
)
