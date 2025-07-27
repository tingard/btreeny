# Welcome to BTreeny!

This package is a minimal(ish) implementation of [Behavior Trees](https://en.wikipedia.org/wiki/Behavior_tree_(artificial_intelligence,_robotics_and_control)) in Python. It mainly exists to explore a different way of building and running behavior trees in Python (using a more function-based approach).

For production uses, we strongly recommend using a more battle-tested library such as [PyTrees](https://py-trees.readthedocs.io/en/devel/)! Not only is `btreeny` far more likely to cause bugs but the core implementation is meaningfully slower than `PyTrees` - we really do recommend putting in the effort to use it for production use-cases.

For general tinkering, keep reading 👀

```python
import btreeny

# Generic over blackboards - use dataclasses to get nice type hints!
MyBlackboardType = dict[str, str]

# For the most simple case - define your actions as a function which takes a blackbaord
# and returns a tree
@btreeny.simple_action
def my_failing_action(blackboard: MyBlackboardType):
    # You could modify the blackboard, or take actions here
    return btreeny.FAILURE

# For more complex actions
@btreeny.action
def my_running_action():
    # Setup
    # ...

    # Yield a tick function
    def _inner(blackboard: MyBlackboardType):
        return btreeny.RUNNING
    try:
        yield inner
    finally:
        # Teardown
        # ...

# We support many standard control flow nodes - see below for options
root = btreeny.fallback(
    my_failing_action(),
    my_running_action(),
)

# Running the tree can be done manually
blackboard = {}
result = btreeny.RUNNING
with root as tick_function:
    while result == btreeny.RUNNING:
        # We expect trees to modify the blackboard in-place
        result = tick_function(blackboard)
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
            return btreeny.FAILURE
        response = client.get(url)
        retry_count += 1
        if response.status_code == 200:
            return btreeny.SUCCESS
        return btreeny.RUNNING
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


## Blackboards

In the above example, we committed a cardinal sin of behavior trees! The `client.get(url)` call is **blocking**, meaning the tree will fail to tick to completion.

A better pattern is to run the call in a background thread and return `RUNNING`. For example, if we have some blocking function `long_running_job` which we need to monitor, we can initialize a thread pool and make it available in our blackboard. Actions can then submit jobs to this thread pool and monitor for completion.

```python
import concurrent.futures
from dataclasses import dataclass
import time

@dataclass
class Blackboard:
    pool: concurrent.futures.ThreadPoolExecutor

def long_running_job():
    time.sleep(3)
    return True

@btreeny.action
def long_running_action():
    _fut: concurrent.futures[bool] | None = None
    def _inner(b: Blackboard):
        nonlocal _fut
        if _fut is None:
            _fut = b.pool.submit(long_running_job)
        try:
            result = _current_response.result(timeout=0)
            if result:
                return btreeny.SUCCESS
            else:
                return btreeny.FAILURE
        except concurrent.futures.TimeoutError:
            return btreeny.RUNNING
```

While we _could_ provide a utility that gives actions access to a pool by default, that wouldn't be very minimal of us would it 😛

An example of this pattern can be found in the `examples/non_blocking_tree.py` script.

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
Map output states to different values - e.g. convert all `SUCCESS` outputs into `FAILURE`. Note that this is not reciprocal! You could, for example, use this to convert all outputs to `RUNNING`.

`remap` has some utilities
- `swap`: Reciprocally map between two states (e.g. Failure <-> Success)
- `remap_to_always`: Convert the output of the action to always be this value.

### Failsafe
Given some condition check which runs on each tick with the current blackboard, if the check ever fails move to a failure tree.

Useful when combined with `redo` to allow failsafe behaviour which can recover to continue normal operations.

This action allows fallback to a charging state on low battery in the `waypoint_navigation` example script.

### Parallel

Another useful control - this allows running multiple actions on each tick, without requiring them to complete. Ticks will still happen sequentially but we do not require an action to have completed in order to run the next child. This node is especially powerful when combined with the "non blocking actions" section above, as you can trigger and wait on multiple background tasks concurrently.

The return value of a tick is determined by a callable `result_evaluation_function` you can provide as a keyword argument, with a fairly conservative default.

## Logging and Visualization

Understanding what's going on in your behavior tree is crucial for debugging and triaging issues - btreeny has an (opinionated) set of logging utilities, but lets you access the underlying data to write your own.

The simplest way to log the current tree state is simply to use the 

### Rich 

Rich is a great library for pretty printing in the terminal, to get the current tree state as a [rich.Tree](https://rich.readthedocs.io/en/stable/tree.html) renderable, use `btree.viz.get_rich_tree()`.

```python
from rich.print import print
tree = btree.viz.get_rich_tree()
print(tree)
```

### Rerun

Rerun is a great tool for visualizing robotics applications - and we want to make it easy for you to add your `btreeny` state to each timestep.

```python
import rerun as rr
# fetch the current tree state as a dataclass with Rerun `rr.GraphNodes` and `rr.GraphEdges`
graph = btreeny.viz.rerun_tree_graph()
# Log to Rerun
rr.log("tree", graph.nodes, graph.edges)
```