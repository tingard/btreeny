import contextvars
import uuid
from ._tree_status import TreeStatus

id_map = contextvars.ContextVar[dict[uuid.UUID, str]]("call_stack")
id_map.set({})
call_stack = contextvars.ContextVar[list[uuid.UUID]]("call_stack")
call_stack.set([])
tree_graph = contextvars.ContextVar[dict[uuid.UUID | None, list[uuid.UUID]]](
    "tree_graph"
)
tree_graph.set({})
tree_status = contextvars.ContextVar[dict[uuid.UUID, TreeStatus]]("tree_status")
tree_status.set({})
