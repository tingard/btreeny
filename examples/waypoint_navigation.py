import contextvars
from btreeny import action, TreeStatus, fallback, sequential, swap, react, repeat
from btreeny.trace import print_trace
import itertools

@action
def example_always_return(name: str, result: TreeStatus = TreeStatus.SUCCESS):
    # We do some setup
    print(f"Setting up example_always_return: {name}")
    # We yield a function which does a "tick"
    def inner(b: None) -> TreeStatus:
        print(f"Running example_always_return: {name} - blackboard {b}")
        return result
    try:
        yield inner
    finally:
        # We do some teardown - note that by putting this in a `finally` block
        # it is (almost) guaranteed to run
        print(f"Tearing down example_always_return: {name}")

@action
def example_iterate_through(name: str, responses: list[TreeStatus] = [TreeStatus.SUCCESS]):
    # We do some setup
    print(f"Setting up example_iterate_through: {name}")
    # We yield a function which does a "tick"
    gen = iter(responses)
    def inner(b: None) -> TreeStatus:
        print(f"Running example_iterate_through: {name} - blackboard {b}")
        return next(gen)
    try:
        yield inner
    finally:
        # We do some teardown - note that by putting this in a `finally` block
        # it is (almost) guaranteed to run
        print(f"Tearing down example_iterate_through: {name}")


def main():
    counter = itertools.count()
    nominal = fallback(
        example_iterate_through("0", [TreeStatus.RUNNING, TreeStatus.RUNNING, TreeStatus.FAILURE]),
        sequential(
            swap(example_always_return("1", TreeStatus.FAILURE), TreeStatus.FAILURE, TreeStatus.SUCCESS),
            example_iterate_through("2", [TreeStatus.RUNNING, TreeStatus.SUCCESS]),
            example_always_return("3", TreeStatus.FAILURE)
        ),
        sequential(
            example_always_return("4"),
            example_iterate_through("5", [TreeStatus.RUNNING, TreeStatus.FAILURE]),
        ),
        example_always_return("6", TreeStatus.FAILURE),
        repeat(lambda: example_iterate_through(f"r-{next(counter)}", [TreeStatus.RUNNING, TreeStatus.SUCCESS]), 3)
    )

    error_mode = example_iterate_through("error_mode", [TreeStatus.RUNNING] * 10 + [TreeStatus.FAILURE])
    
    counter = itertools.count()
    def condition(_):
        val = next(counter)
        return val > 3 and val < 15
    
    # Reactive means run nominal branch if condition is True and error branch if False
    root = react(
        condition,
        nominal,
        error_mode,
    )

    blackboard = None
    with root as tree:
        for i in range(20):
            result = tree(blackboard)
            print()
            print(f"Tick Result {i}: {result}")
            print_trace()
            print()
            if result != TreeStatus.RUNNING:
                break
    # Cool - how do I visualise the status of the tree?
    # How do I debug blackboard access?
    # A - just use py-trees
    
if __name__ == "__main__":
    # Running using contextvars allows thread-safety
    ctx = contextvars.copy_context()
    ctx.run(main)