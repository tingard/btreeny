from collections import deque
from dataclasses import dataclass
from typing import Callable
import uuid

try:
    import rerun as rr

    __has_rerun = True
except ImportError:
    __has_rerun = False

from ._ctx import (
    tree_graph as __ctx_tree_graph,
    id_map as __ctx_id_map,
    tree_status as __ctx_tree_status,
)
from ._tree_status import TreeStatus


@dataclass
class TreeStatusGraph:
    node: str
    status: TreeStatus
    children: "list[TreeStatusGraph]"


def get_tree_status() -> TreeStatusGraph:
    _id_map = __ctx_id_map.get()
    _tree_graph = __ctx_tree_graph.get()
    _tree_status = __ctx_tree_status.get()

    root_actions = _tree_graph[None]
    assert len(root_actions) == 1
    root_action = root_actions[0]
    node_map: dict[uuid.UUID, TreeStatusGraph] = {}
    node_map[root_action] = TreeStatusGraph(
        node=_id_map[root_action], status=_tree_status[root_action], children=[]
    )
    q = deque[uuid.UUID]([])
    q.append(root_action)
    while len(q) > 0:
        action = q.popleft()
        children = _tree_graph[action]
        for child in children:
            node_map[action].children.append(
                TreeStatusGraph(
                    node=_id_map[child], status=_tree_status[child], children=[]
                )
            )
            q.append(child)
    return node_map[root_action]


def print_trace(print_func: Callable[[str], None] = print):
    _id_map = __ctx_id_map.get()
    _tree_graph = __ctx_tree_graph.get()
    _tree_status = __ctx_tree_status.get()
    root_actions = _tree_graph[None]
    q = deque()
    print_func(f"\n{' Trace ':-^50}")
    for action_id in root_actions:
        q.append((action_id, 0))
    while len(q) > 0:
        action_id, indent_count = q.popleft()
        indent = " " * indent_count * 4
        action_name = _id_map[action_id]
        action_status = _tree_status.get(action_id, None)
        if action_status is not None:
            action_status = action_status.value
        print_func(f"{indent}{action_id} {action_name} - {action_status}")
        for child in _tree_graph.get(action_id, [])[::-1]:
            q.appendleft((child, indent_count + 1))
    print_func("-" * 50 + "\n")


if __has_rerun:

    def rerun_log_trace(
        rec: rr.RecordingStream | None = None, entity_path: str = "btreeny/tree"
    ):
        _id_map = __ctx_id_map.get()
        _tree_graph = __ctx_tree_graph.get()
        _tree_status = __ctx_tree_status.get()
        keys = list(_tree_status.keys())

        def _color_from_status(s: TreeStatus) -> int:
            match s:
                case TreeStatus.SUCCESS:
                    return 0x119911FF
                case TreeStatus.FAILURE:
                    return 0x991111FF
                case TreeStatus.RUNNING:
                    return 0xBB6633FF
                case _:
                    raise RuntimeError(f"Not a valid status {s}")

        (rec or rr).log(
            entity_path,
            rr.GraphNodes(
                node_ids=list(map(str, keys)),
                labels=[f"{_id_map[k]}\n{_tree_status[k]}" for k in keys],
                colors=[_color_from_status(_tree_status[k]) for k in keys],
                show_labels=True,
            ),
            rr.GraphEdges(
                edges=[
                    (str(parent), str(child))
                    for parent in keys
                    for child in _tree_graph.get(parent, [])
                ],
                # Optional: graphs are undirected by default.
                graph_type="directed",
            ),
        )
