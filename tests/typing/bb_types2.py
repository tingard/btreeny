"""Static-typing regression tests.

These are not executed by pytest - they are checked by `pyrefly check`. The
bodies live under `if TYPE_CHECKING` so nothing runs at import time.

Two kinds of assertion:

* ``assert_type(...)`` pins the type that survives the decorators. This is the
  important one: the failure mode being guarded against is the blackboard type
  silently decaying to ``Any``, and ``assert_type`` rejects ``Any``.
* ``# pyrefly: ignore[bad-argument-type]`` asserts that misuse IS rejected, with
  that exact error kind. ``unused-ignore = true`` in this directory's
  pyrefly.toml makes it bidirectional - if the library stops catching the error,
  the suppression becomes unused and pyrefly fails.
"""

from dataclasses import dataclass
from typing import TYPE_CHECKING, Iterator, Protocol, assert_type

import btreeny as bt


@dataclass
class BBa:
    a: int = 0


@dataclass
class BBb:
    b: int = 0


class SupportsPut(Protocol):
    def put(self, value: int) -> None: ...


@bt.simple_action
def wants_a(blackboard: BBa) -> bt.TreeStatus:
    return bt.SUCCESS


@bt.action
def wants_b_unannotated(node_id: bt.IdType):
    """README style - no return annotation on the generator."""

    def tick(blackboard: BBb) -> bt.TreeStatus:
        return bt.SUCCESS

    yield tick


@bt.action
def wants_b_annotated(
    node_id: bt.IdType,
) -> Iterator[bt.TreeTickFunction[BBb]]:
    def tick(blackboard: BBb) -> bt.TreeStatus:
        return bt.SUCCESS

    yield tick


@bt.simple_action
def wants_protocol(blackboard: SupportsPut) -> bt.TreeStatus:
    blackboard.put(1)
    return bt.SUCCESS


if TYPE_CHECKING:

    def _simple_action_preserves_blackboard() -> None:
        with wants_a() as tick:
            assert_type(tick, bt.TreeTickFunction[BBa])
            tick("nonsense")  # pyrefly: ignore[bad-argument-type]

    def _action_preserves_blackboard_without_annotation() -> None:
        with wants_b_unannotated() as tick:
            assert_type(tick, bt.TreeTickFunction[BBb])
            tick("nonsense")  # pyrefly: ignore[bad-argument-type]

    def _action_preserves_blackboard_with_annotation() -> None:
        with wants_b_annotated() as tick:
            assert_type(tick, bt.TreeTickFunction[BBb])
            tick("nonsense")  # pyrefly: ignore[bad-argument-type]

    def _sequential_preserves_blackboard() -> None:
        with bt.sequential(wants_a(), wants_a()) as tick:
            assert_type(tick, bt.TreeTickFunction[BBa])
            tick("nonsense")  # pyrefly: ignore[bad-argument-type]

    def _fallback_preserves_blackboard() -> None:
        with bt.fallback(wants_a(), wants_a()) as tick:
            assert_type(tick, bt.TreeTickFunction[BBa])

    def _protocol_restricts_access() -> None:
        """The README's headline claim: an action cannot touch undeclared state."""

        @bt.simple_action
        def naughty(blackboard: SupportsPut) -> bt.TreeStatus:
            blackboard.poll()  # pyrefly: ignore[missing-attribute]
            return bt.SUCCESS

    def _structural_subtyping_accepts_wider_blackboard() -> None:
        @dataclass
        class Wide:
            def put(self, value: int) -> None: ...
            def other(self) -> None: ...

        with wants_protocol() as tick:
            assert_type(tick, bt.TreeTickFunction[SupportsPut])
            tick(Wide())  # a wider blackboard satisfies the Protocol
