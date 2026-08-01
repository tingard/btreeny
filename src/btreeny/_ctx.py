from collections import deque
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


def reset():
    for v in (id_map, tree_graph, tree_status, call_stack):
        v.set(None)


def clear_subtree(node_id: IdType):
    to_search = deque((node_id,))
    to_clear = set()
    curr_tree_graph = tree_graph.get() or {}
    # BFS down the tree from this node
    while len(to_search) > 0:
        p = to_search.pop()
        c_of_p = curr_tree_graph.get(p, None)
        if c_of_p is None:
            continue
        to_search.extend(c_of_p)
        to_clear.update(c_of_p)
    # If we are about to clear a node that is currently active, abort
    if call_stack.get() in to_clear:
        raise RuntimeError("Attempted to clear a node that is currently active.")

    curr_tree_status = tree_status.get() or {}
    curr_id_map = id_map.get() or {}

    # Clear the children of the parent node
    curr_tree_graph.pop(node_id, None)

    # Remove all descendents from the graph
    for descendant_node_id in to_clear:
        curr_id_map.pop(descendant_node_id, None)
        curr_tree_graph.pop(descendant_node_id, None)
        curr_tree_status.pop(descendant_node_id, None)
    tree_graph.set(curr_tree_graph)
    tree_status.set(curr_tree_status)
    id_map.set(curr_id_map)


def cancel_running_children(node_id: IdType):
    to_search = deque((node_id,))
    curr_tree_graph = tree_graph.get() or {}
    curr_status = tree_status.get() or {}
    # BFS down the tree from this node
    while len(to_search) > 0:
        p = to_search.pop()
        c_of_p = curr_tree_graph.get(p, None)
        if c_of_p is None:
            continue
        to_search.extend(c_of_p)
        for child in c_of_p:
            if curr_status.get(child, None) == TreeStatus.RUNNING:
                curr_status[child] = TreeStatus.CANCELLED
    tree_status.set(curr_status)


def update_name(node_id: IdType, new_name: str):
    if (curr_id_map := id_map.get()) is not None:
        curr_id_map[node_id] = new_name
        id_map.set(curr_id_map)
