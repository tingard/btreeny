# Welcome to BTreeny!

This package is a minimal(ish) implementation of [Behavior Trees](https://en.wikipedia.org/wiki/Behavior_tree_(artificial_intelligence,_robotics_and_control)) in Python. It provides a type-safe, friendly interface to build complex behaviours.

A note on _when_ to use this library: I think it's pretty neat, and leverages the type system for a better developer experience (and correctness) than other Python libraries I've seen, but alternatives like [PyTrees](https://py-trees.readthedocs.io/en/devel/) are much more battle-hardened.

I'd very much encourage you to consider and play with `btreeny` (and give feedback!), but rough edges are to be expected (for now).

For general tinkering, keep reading 👀

## Writing an action

In `btreeny`, an action is specified as a context manager which yields a callable function to "tick" the action. This allows you to manage the setup and teardown of resources required by that action.

For example, an action which polls a URL until it gets a 200 status code, and will fail after some number of retries, might look like:

```python
from itertools import count
from typing import Any

import httpx

import btreeny


@btreeny.action
def poll_url(node_id: btreeny.IdType, url: str, retries: int = 10):
    # setup a client to allow connection pooling
    retry_count = count()
    with httpx.Client() as client:
        def tick(blackboard: Any):
            if next(retry_count) >= retries:
                return btreeny.FAILURE
            # There's something fishy about this line
            # read on to find out what.
            response = client.get(url)
            if response.status_code == 200:
                return btreeny.SUCCESS
            return btreeny.RUNNING

        yield tick
```

You can (and should) also make use of `try: ... except: ...` blocks to gracefully shut down an action, and utilities like `contextlib.ExitStack` for more advanced chaining!

### Simple Actions

`btreeny` lets you simplify some of the above using the `simple_action` decorator, which is more appropriate if you have a pure function:

```python
@btreeny.simple_action
def print_hello_world(blackboard: Any):
    print("Hello, world!")
    return btreeny.SUCCESS
```

## Using Blackboards

In the above example, we committed a cardinal sin of behaviour trees! The `client.get(url)` call is **blocking**, meaning the tree tick will not return until the response has. This prevents reactive behaviours and other checks from running, and must be avoided.

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
def long_running_action(node_id: btreeny.IdType):
    _fut: concurrent.futures.Future[bool] | None = None

    def _inner(b: Blackboard):
        nonlocal _fut
        # If we haven't yet created the task, set it up
        if _fut is None:
            _fut = b.pool.submit(long_running_job)
            return btreeny.RUNNING
        # Attempt to fetch the future's result
        try:
            result = _fut.result(timeout=0)
        except concurrent.futures.TimeoutError:
            # A timeout implies the task is still running
            return btreeny.RUNNING
        # We got a result! Return appropriately.
        if result:
            return btreeny.SUCCESS
        else:
            return btreeny.FAILURE

    yield _inner
```

While we _could_ provide a utility that gives actions access to a pool by default, that wouldn't be very minimal of us, would it? 😛 Letting you set it up on your blackboard means different pools could be used, or even larger scale compute like Dask or _the cloud_! ☁️

An example of this pattern can be found in the [examples/non_blocking_tree.py](examples/non_blocking_tree.py) script.

### The type system as access control

One of the great perks of a typed blackboard and generic actions is that we can express what actions can/can't do _via Python's type system_! For example, consider two actions, one of which can place tickets into a backlog, and the other can read from it. Our full blackboard might look like:

```python
@dataclass
class TicketingBlackboard:
    tickets: queue.Queue[Ticket]
    def put(self, ticket: Ticket):
        self.tickets.put(ticket)

    def poll(self) -> Ticket | None:
        try:
            return self.tickets.get_nowait()
        except queue.Empty:
            return None
```

We can then use the magic of ✨structural subtyping✨ to restrict what each action can do, using `Protocol`s. First, the insertion action

```python
class SupportsPutTicket(Protocol):
    def put(self, ticket: Ticket): ...

@btreeny.simple_action
def put_ticket_action(blackboard: SupportsPutTicket):
    # Mint and insert a new Ticket
    blackboard.put(Ticket())
    return btreeny.SUCCESS
```

And then the read action

```python
class SupportsPollTicket(Protocol):
    def poll(self) -> Ticket | None: ...

@btreeny.simple_action
def poll_tickets_action(blackboard: SupportsPollTicket):
    # Take the next Ticket off the backlog, if there is one
    ticket = blackboard.poll()
    # Do something with the ticket - maybe trigger a
    # long-running task as above
    return btreeny.SUCCESS
```

If `put_ticket_action` tried to `poll`, or `poll_tickets_action` tried to `put`, any type checker (mypy, pyright, pyrefly, ty, ...) would complain _before any code even runs_! This is (in my opinion) much better than PyTrees' blackboard permissions model, but I'm biased.

## Running a tree

Behind the scenes, we rely on the use of the `contextvars` module. For this reason it's recommended that you make use of the `btreeny.runner` decorator when running your trees:

```python
@btreeny.runner
def main():
    tree = btreeny.fallback(
        btreeny.redo(
            # `redo` takes a factory, not a node: it tears down and rebuilds
            # its child on every repetition, so the children have to be
            # constructed fresh each time.
            lambda: btreeny.sequential(do_action_a(), do_action_b())
        ),
        do_fallback_action()
    )
    blackboard = Blackboard()
    tick_freq = 10
    with tree as tick:
        while True:
            # We can make use of the rate_limit utility to ensure that
            # ticks are no faster than the desired period
            with btreeny.rate_limit(int(1e9 / tick_freq)):
                tick(blackboard)
```

## Controlling flow

### Sequential
Accepts multiple children to iterate through. When each child succeeds, move to the next action. If any child fails then the node fails.

### Fallback
Accepts multiple children to iterate through. If a child fails, move to the next action. If any child succeeds then the node succeeds.

### Repeat / Retry / Redo
`repeat(action_factory, continue_if=..., count=None)` accepts a factory function, the status to continue on, and an optional number of repetitions (`count=None` repeats indefinitely). If the resulting action returns the specified `continue_if` value, recreate the action using the factory function and carry on.

The factory has to build a fresh node on each call, because `repeat` runs setup and teardown on every repetition.

- `retry` wraps `repeat` with `continue_if=TreeStatus.FAILURE`
- `redo` wraps `repeat` with `continue_if=TreeStatus.SUCCESS`

### Remap
Map output states to different values - e.g. convert all `SUCCESS` outputs into `FAILURE`. The mapping is applied as a plain lookup, so it is not reciprocal! You could, for example, use this to convert all outputs to `RUNNING`.

`remap` has two related helpers
- `swap(child, from_=..., to=...)`: Reciprocally map between two states (e.g. `FAILURE` <-> `SUCCESS`)
- `always_return(child, always_return=...)`: Discard the child's result and always return this value.

### Switch
Given some condition check which runs on each tick with the current blackboard, if the check ever returns `False` move from the primary mode to the secondary. Note that
in order to move _back_ to the primary mode, a `redo` must be used.

Useful when combined with `redo` to allow failsafe behaviour which can recover to continue normal operations.

Any node that was still running when the check fails is marked `TreeStatus.CANCELLED`, so interrupted branches are distinguishable from failed ones in the visualizations.

This node allows fallback to a charging state on low battery in the [examples/waypoint_navigation.py](examples/waypoint_navigation.py) script.

### Parallel

Another useful control node - this allows running multiple actions on each tick, without requiring them to complete. Ticks will still happen sequentially but we do not require an action to have completed in order to run the next child. This node is especially powerful when combined with the non-blocking pattern described in [Using Blackboards](#using-blackboards), as you can trigger and wait on multiple background tasks concurrently.

The return value of a tick is determined by a callable `result_evaluation_function` you can provide as a keyword argument, with a fairly conservative default (`any_running_is_running_allow_max_failures_failures`: `RUNNING` if any child is running, `FAILURE` if more than `max_failures` children failed, otherwise `SUCCESS`).

## Logging and Visualization

Understanding what's going on in your behaviour tree is crucial for debugging and triaging issues - `btreeny` has an (opinionated) set of logging utilities, but lets you access the underlying data to write your own.

The simplest way to log the current tree state is to use the `btreeny.viz.get_tree_status` helper function, which returns a `TreeStatusGraph` - a nested dataclass of `node`, `status` and `children` that you can print, walk, or pretty-print with `graph.pprint()`. There's also `btreeny.viz.print_trace()`, which prints a flat, indented trace of every node and its current status.

### Rich

[Rich](https://rich.readthedocs.io/en/stable/) is a great library for pretty printing in the terminal. If Rich is installed, you can fetch the current tree state as a [rich.Tree](https://rich.readthedocs.io/en/stable/tree.html) renderable using `btreeny.viz.get_rich_tree()`.

```python
from rich import print

tree = btreeny.viz.get_rich_tree()
print(tree)
```

### Rerun

[Rerun](https://rerun.io/) is a great tool for visualizing robotics applications, and we want to make it easy for you to add your `btreeny` state to each timestep. If Rerun is installed, you can run the below to log the current tree status to the active recording:

```python
import rerun as rr
# fetch the current tree state as a dataclass with Rerun `rr.GraphNodes` and `rr.GraphEdges`
graph = btreeny.viz.rerun_tree_graph()
# Log to Rerun
rr.log("tree", graph.nodes, graph.edges)
```

## `btreeny` or PyTrees?

Both libraries do fundamentally the same thing, so choosing between them comes down to what
you want to optimise for. PyTrees is a mature platform with a lot of tooling built up around
it; `btreeny` is small and leans hard on the type system.

### Use PyTrees if...

**You're on ROS 2.**

`py_trees_ros` and the tutorials that come with it are a proper ecosystem, and `btreeny` has nothing to offer you here.

**You want batteries included.**

Stock behaviours, decorators, idioms like `oneshot` and `either_or`, visitors, pre/post-tick handlers, graphviz rendering, CLI tooling - it's all there, and it all works.

**You want to watch your data flow at runtime.**

Registering keys against clients means PyTrees can tell you which behaviour touched what, and hand you an activity stream and a dot graph with the variables drawn right in. That's genuinely lovely for debugging.

**You've got a team, or people rotating through the codebase.**

PyTrees was designed so that scenario development could be handed off to people who aren't control engineers, and the docs and demos reflect that.

**You need something that won't move under you.**

PyTrees is on 2.x and has years of use behind it. This library is... not that 😅

### Use `btreeny` if...

**You'd like the type checker to do some work for you.**

Your blackboard is a dataclass *you* own rather than a global string-keyed store, and actions ask for exactly what they need via `Protocol`s - so an action grabbing at state it has no business touching is an error *before you run anything*. 

Worth being fair to PyTrees here: its key registration isn't really trying to be an enforcement mechanism, and the docs are upfront that it's there to help you debug (which I'd argue typing does even better). So it's static guarantees versus runtime visibility. I know which one I'd rather have, but I'm biased 😛

**Your actions own resources.**

Actions are context managers, so your connection pool, file handle or subprocess gets set up and torn down along with the node itself, and `ExitStack` composes exactly like it does everywhere else in Python.

**You'd rather write a function than a subclass.** 

No base class to inherit from and no lifecycle methods to memorise - a decorator and a closure and you're done.

**You want to read the whole library.**

`btreeny` is minimal on purpose, and I'm likely to say no to things that would change that. That's a straight-up cost if you need something it hasn't got, and a win if you'd like to actually understand what you're depending on.

**You're not doing robotics.**

Nothing in here assumes you are - trees are just as happy orchestrating jobs, retries or agent workflows. (And if you *are*, the Rerun logging is already sitting there waiting for you 👀)

### tl;dr

If it's going into production and something important depends on it, use PyTrees. If you're starting something fresh, like your types, and want a library small enough to hold in your head, give `btreeny` a go - and then come and tell me what broke! The only way to make this library more production-friendly is to have people try.
