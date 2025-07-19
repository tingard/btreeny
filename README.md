# Welcome to BTreeny!

This package is a minimal(ish) implementation of [Behavior Trees](https://en.wikipedia.org/wiki/Behavior_tree_(artificial_intelligence,_robotics_and_control)) in Python.


```python
import btreeny

# Generic over blackboards - use dataclasses to get nice type hints!
MyBlackboardType = dict[str, str]

# For the most simple case - define your actions as a function which takes a blackbaord
# and returns a tree
@btreeny.simple_action
def my_failing_action(blackboard: MyBlackboardType):
    # You could modify the blackboard, or take actions here
    return btreeny.TreeStatus.FAILURE

# For more complex actions
@btreeny.action
def my_failing_action():
    def _inner(blackboard: MyBlackboardType)


# We support many standard control flow nodes
# - sequential
# - fallback
# - repeat
# - react
root = btreeny.fallback(
    my_failing_action(),
    my_running_action(),
)

# Running the tree can be done manually
blackboard = {}
result = btreeny.TreeStatus.RUNNING
with root as tick_function:
    while result == btreeny.TreeStatus.RUNNING:
        # We expect trees to modify the blackboard in-place
        result = tick_function(blackboard)

# or with a utility
from datetime import timedelta
for result in btreeny.run(root, blackboard, interval=timedelta(seconds=1)):
    print(result)
```