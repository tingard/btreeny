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


# We support many standard control flow nodes - see below for options
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


## Writing an action

In `btreeny`, an action is specified as a context which returns a callable function to "tick" the action. This allows you to manage the setup and teardown of resources required by that action.

For example, an action which polls a URL until it gets a 200 status code, and will fail after some number of retries, might look like:

```python
@btreeny.action
def poll_url(url: str, retries: int=10):
    # setup a client to allow connection pooling
    client = httpx.Client()
    retry_count = 0
    def tick(blackboard: Any):
        # Since we're assigning to retry_count, we should declare it as nonlocal
        # to this function's scope
        nonlocal retry_count
        if retry_count > retries:
            return btreeny.TreeStatus.FAILURE
        response = client.get(url)
        retry_count += 1
        if response.status_code == 200:
            return btreeny.TreeStatus.SUCCESS
        return btreeny.TreeStatus.RUNNING
    # Use a try... finally block to ensure cleanup is run
    try:
        # yield the tick function
        yield tick
    finally:
        # We can finish the function with our cleanup
        client.close()
```

Note that in this case it'd have been more ergonomic to use 

```python
with httpx.Client() as client:
    def tick(...):
        ...
    yield tick
```

As the client would have been closed for us!


## Controlling flow


### Sequential
Accepts multiple children to cycle through. When each child succeeds, move to the next action. If any child fails then the node fails.

### Fallback
Accepts multiple children to cycle through. If a child fails, move to the next action. If any child suceeds then the node fails.

### Repeat / Retry / Redo
Accepts a factory function and an optional number of retries. If the resulting action matches the specified `continue_if` value, recreate the action using the factory function and carry on.

- Retry wraps `repeat` with `continue_if=TreeStatus.FAILURE`
- Redo wraps `repeat` with `continue_if=TreeStatus.SUCCESS`

### Remap
Map 

### Swap

### React

### Failsafe

