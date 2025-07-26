# import functools
# import btreeny as bt
# import tests.standard_actions as sa

# def make_action(n_children: int):
#     return bt.sequential(*(sa.always_ok() for _ in range(n_children)))

# def run_single(
#     n_ticks: int = 1000,
# ):
#     with sa.always_ok() as tick:
#         for _ in range(n_ticks):
#             _ = tick(None)

# def run(
#     n_children: int = 1,
#     n_ticks: int = 1000,
# ):
#     action = make_action(n_children)
#     with action as tick:
#         for _ in range(n_ticks):
#             _ = tick(None)

# __benchmarks__ = [
#     (run_single, functools.partial(run, n_children=1), "Short sequential (1 children)"),
#     (run_single, functools.partial(run, n_children=10), "Mid sequential (10 children)"),
#     (run_single, functools.partial(run, n_children=100), "Long sequential (100 children)"),
#     (run_single, functools.partial(run, n_children=1000), "Very long sequential (1000 children)"),
# ]
