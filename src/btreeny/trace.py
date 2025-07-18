from collections import deque
from ._ctx import (
    tree_graph as __ctx_tree_graph,
    id_map as __ctx_id_map,
    tree_status as __ctx_tree_status,
)


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
