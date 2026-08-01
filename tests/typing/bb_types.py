import btreeny as bt


@bt.action
def wants_b(node_id: bt.IdType):  # no return annotation (as in the README)
    def tick(blackboard: None) -> bt.TreeStatus: ...

    yield tick


@bt.simple_action
def wants_a(blackboard: int) -> bt.TreeStatus: ...


with wants_a() as tick_a:
    tick_a("nonsense")  # pyrefly: ignore[bad-argument-type]

with wants_b() as tick_b:
    tick_b("nonsense")  # pyrefly: ignore[bad-argument-type]

with bt.sequential(wants_a(), wants_b()) as tick_c:
    tick_c(None)
