import uuid
from collections import deque
from dataclasses import asdict, dataclass
from typing import Callable

from ._ctx import (
    id_map as __ctx_id_map,
)
from ._ctx import (
    tree_graph as __ctx_tree_graph,
)
from ._ctx import (
    tree_status as __ctx_tree_status,
)
from .tree_status import TreeStatus


def print_trace(print_func: Callable[[str], None] = print):
    """Print the current state of the tree using a specified function.

    Parameters
    ----------
    print_func: (str) -> None
        The printing function to use, defaults to the builtin `print` function.
    """
    _id_map = __ctx_id_map.get() or {}
    _tree_graph = __ctx_tree_graph.get() or {}
    _tree_status = __ctx_tree_status.get() or {}
    root_actions = _tree_graph[None]
    print_func(f"\n{' Trace ':-^50}")
    q = deque((action_id, 0) for action_id in root_actions)
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


@dataclass
class TreeStatusGraph:
    node: str
    status: TreeStatus
    children: "list[TreeStatusGraph]"

    def pprint(self):
        pprint(asdict(self))

    def count(self):
        c = 1
        to_iter = deque(self.children)
        while len(to_iter):
            subgraph = to_iter.popleft()
            c += 1
            to_iter.extend(subgraph.children)
        return c


def get_tree_status() -> "TreeStatusGraph":
    """Fetch the current state of the tree as a tree datastructure.

    Returns
    -------
    TreeStatus:
        The root of the behavior tree.
    """
    _id_map = __ctx_id_map.get() or {}
    _tree_graph = __ctx_tree_graph.get() or {}
    _tree_status = __ctx_tree_status.get() or {}

    root_actions = _tree_graph[None]
    assert len(root_actions) == 1, "Expected one root action"
    root_action = root_actions[0]
    node_map: dict[uuid.UUID, TreeStatusGraph] = {}
    node_map[root_action] = TreeStatusGraph(
        node=_id_map[root_action], status=_tree_status[root_action], children=[]
    )
    q = deque[uuid.UUID]([])
    q.append(root_action)
    while len(q) > 0:
        action = q.popleft()
        try:
            children = _tree_graph[action]
        except KeyError:
            continue
        for child in children:
            child_name = _id_map[child]
            child_status = _tree_status[child]
            node_map[child] = TreeStatusGraph(
                node=child_name, status=child_status, children=[]
            )
            node_map[action].children.append(node_map[child])
            q.append(child)
    return node_map[root_action]


try:
    import rerun as rr

    @dataclass
    class RerunGraph:
        nodes: rr.GraphNodes
        edges: rr.GraphEdges

    def rerun_tree_graph() -> RerunGraph:
        _id_map = __ctx_id_map.get() or {}
        _tree_graph = __ctx_tree_graph.get() or {}
        _tree_status = __ctx_tree_status.get() or {}
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

        return RerunGraph(
            nodes=rr.GraphNodes(
                node_ids=list(map(str, keys)),
                labels=[f"{_id_map[k]}\n{_tree_status[k]}" for k in keys],
                colors=[_color_from_status(_tree_status[k]) for k in keys],
                show_labels=True,
            ),
            edges=rr.GraphEdges(
                edges=[
                    (str(parent), str(child))
                    for parent in keys
                    for child in _tree_graph.get(parent, [])
                ],
                graph_type="directed",
            ),
        )
except ImportError:
    pass


try:
    from rich.pretty import pprint
    from rich.tree import Tree

    def get_rich_tree() -> Tree:
        _id_map = __ctx_id_map.get() or {}
        _tree_graph = __ctx_tree_graph.get() or {}
        _tree_status = __ctx_tree_status.get() or {}
        try:
            root_actions = _tree_graph[None]
        except KeyError:
            return Tree("root")
        assert len(root_actions) == 1, "Expected one root action"
        root = root_actions[0]
        q = deque[tuple[uuid.UUID, Tree]]()
        tree = Tree(f"{_id_map[root]} - {_tree_status[root].value}")
        q.append((root, tree))
        while len(q) > 0:
            action_id, parent_tree = q.popleft()
            action_name = _id_map[action_id]
            action_status = _tree_status.get(action_id, None)
            if action_status is not None:
                action_status = action_status.value
            else:
                action_status = "Not Run"
            child_tree = parent_tree.add(f"{action_name} - {action_status}")
            for child in _tree_graph.get(action_id, [])[::-1]:
                q.appendleft((child, child_tree))
        return tree
except ImportError:
    pass
