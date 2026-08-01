from collections import deque
from dataclasses import dataclass, field
import math
import time
from typing import Protocol
import btreeny
import btreeny.viz
import rerun as rr
from rich.console import Console
from rich.live import Live
from rich.columns import Columns

console = Console()


@dataclass
class Position:
    x: float
    y: float

    def distance_to(self, other: "Position") -> float:
        return math.sqrt((self.x - other.x) ** 2 + (self.y - other.y) ** 2)


@dataclass
class NamedPosition(Position):
    name: str


@dataclass
class Direction:
    x: float
    y: float

    def magnitude(self):
        return math.sqrt(self.x**2 + self.y**2)

    def normalize(self) -> "Direction":
        norm = self.magnitude()
        return Direction(self.x / norm, self.y / norm)

    def scale(self, factor: float) -> "Direction":
        return Direction(self.x * factor, self.y * factor)


LOCATIONS = {
    "home": NamedPosition(0, 0, name="home"),
    "north": NamedPosition(1, 0, name="north"),
    "east": NamedPosition(0, 1, name="east"),
    "west": NamedPosition(0, -1, name="west"),
    "south": NamedPosition(-1, 0, name="south"),
}


def move_with_speed(a: Position, b: Position, speed: float, time: float) -> Position:
    """Move from a to b with a given speed for a given time, stopping when b is reached"""
    assert time >= 0
    if time == 0:
        return a
    direction = Direction(b.x - a.x, b.y - a.y)
    distance_to_destination = direction.magnitude()
    max_distance_travelled = speed * time
    if distance_to_destination > max_distance_travelled:
        distance_moved = direction.scale(
            max_distance_travelled / distance_to_destination
        )
        return Position(a.x + distance_moved.x, a.y + distance_moved.y)
    return b


@dataclass
class Robot:
    position: Position = field(default_factory=lambda: LOCATIONS["home"])
    battery: float = 1.0
    discharge_rate: float = 0.02
    charge_rate: float = 0.2
    waypoint: Position | None = None
    speed: float = 0.1
    last_tick: float = field(default_factory=time.monotonic)

    def sense(self):
        new_time = time.monotonic()
        dt = new_time - self.last_tick
        if dt <= 0:
            return
        if self.waypoint is not None:
            self.position = move_with_speed(
                self.position, self.waypoint, self.speed, dt
            )
        self.last_tick = new_time
        self.battery = max(0, self.battery - dt * self.discharge_rate)
        if self.position.distance_to(LOCATIONS["home"]) < 0.01:
            self.battery = min(1.0, self.battery + self.charge_rate * dt)

    def tell_waypoint(self, waypoint: Position):
        console.print(f":robot: Setting new waypoint to {waypoint}")
        self.waypoint = waypoint

    def tell_start_charging(self):
        console.print(":robot: :electric_plug: Started charging")

    def tell_stop_charging(self):
        console.print(":robot: :electric_plug: Stopped charging")


@dataclass(kw_only=True)
class Blackboard:
    destinations: deque[str]
    current_location: Position
    is_charging: bool = False
    desired_waypoint: NamedPosition | None = None
    robot: Robot

    def tell_robot_waypoint(self, position: Position):
        self.robot.tell_waypoint(position)

    def ask_robot_position(self) -> Position:
        return self.robot.position

    def ask_robot_battery(self) -> float:
        return self.robot.battery

    def ask_robot_waypoint(self) -> Position | None:
        return self.robot.waypoint

    def get_next_destination(self) -> str | None:
        if len(self.destinations) == 0:
            return None
        return self.destinations.popleft()

    def set_desired_waypoint(self, location: NamedPosition | None):
        self.desired_waypoint = location

    def get_desired_waypoint(self) -> NamedPosition | None:
        return self.desired_waypoint

    def has_desired_waypoint(self) -> bool:
        return self.desired_waypoint is not None

    def add_priority_destination(self, position: NamedPosition):
        self.destinations.appendleft(position.name)

    def tell_robot_stop_charging(self):
        self.is_charging = False
        self.robot.tell_stop_charging()

    def tell_robot_start_charging(self):
        self.is_charging = True
        self.robot.tell_start_charging()

    def ask_count_remaining_destinations(self):
        return len(self.destinations)


# set_next_waypoint requires the ability to query whether a waypoint is set,
# what the next destination is, and the ability to set a waypoint
class SupportsSetNextWaypointAction(Protocol):
    def has_desired_waypoint(self) -> bool: ...
    def get_next_destination(self) -> str | None: ...
    def set_desired_waypoint(self, location: NamedPosition | None): ...


@btreeny.simple_action
def set_next_waypoint(b: SupportsSetNextWaypointAction):
    location = b.get_next_destination()
    if location is None:
        print("No locations left...")
        return btreeny.FAILURE

    b.set_desired_waypoint(LOCATIONS[location])

    return btreeny.SUCCESS


# move_to_waypoint needs to fetch both the desired waypoint and the current robot
# state, and be able to command a new waypoint (this long list of responsibilities
# by itself indicates the action should probably be decomposed into a series of
# smaller actions!)
class SupportsMoveToWaypointAction(Protocol):
    def get_desired_waypoint(self) -> NamedPosition | None: ...
    def ask_robot_waypoint(self) -> Position | None: ...
    def tell_robot_waypoint(self, position: Position): ...
    def ask_robot_position(self) -> Position: ...


@btreeny.simple_action
def move_to_waypoint(b: SupportsMoveToWaypointAction):
    desired_waypoint = b.get_desired_waypoint()
    if desired_waypoint is None:
        return btreeny.FAILURE

    # Set the waypoint on the robot
    robot_waypoint = b.ask_robot_waypoint()
    if robot_waypoint != desired_waypoint:
        b.tell_robot_waypoint(desired_waypoint)
    # TODO: Waiting for navigation should be a new node.
    if b.ask_robot_position().distance_to(desired_waypoint) < 0.01:
        return btreeny.SUCCESS
    return btreeny.RUNNING


# ...
class SupportsSetHome(Protocol):
    def set_desired_waypoint(self, location: NamedPosition | None): ...


@btreeny.simple_action
def set_home(b: SupportsSetHome):
    b.set_desired_waypoint(LOCATIONS["home"])
    return btreeny.SUCCESS


# Starting to charge simply needs the appropriate `tell` command
class SupportsStartChargingAction(Protocol):
    def tell_robot_start_charging(self): ...


@btreeny.simple_action
def start_charging(b: SupportsStartChargingAction):
    b.tell_robot_start_charging()
    return btreeny.SUCCESS


# Waiting to be fully charged only needs to know the current
# battery
class SupportsWaitForChargeCompleteAction(Protocol):
    def ask_robot_battery(self) -> float: ...


@btreeny.simple_action
def wait_for_charge_complete(b: SupportsWaitForChargeCompleteAction):
    if b.ask_robot_battery() < 0.99:
        return btreeny.RUNNING
    return btreeny.SUCCESS


# Stopping charging simply needs the appropriate `tell` command
class SupportsStopChargingAction(Protocol):
    def tell_robot_stop_charging(self): ...


@btreeny.simple_action
def stop_charging(b: SupportsStopChargingAction):
    b.tell_robot_stop_charging()
    return btreeny.SUCCESS


# The has battery check only needs to ask for the battery level
class SupportsHasBattery(Protocol):
    def ask_robot_battery(self) -> float: ...


# Note this is just a check use for a `failsafe` - not an action
def has_battery(b: SupportsHasBattery, threshold=0.2):
    return b.ask_robot_battery() > threshold


# Pushing the current waypoint back into the stack needs to get the
# current waypoint, and add a priority waypoint to be driven to next
class SupportsPushCurrentWaypointToStackAction(Protocol):
    def get_desired_waypoint(self) -> NamedPosition | None: ...
    def add_priority_destination(self, position: NamedPosition): ...


@btreeny.simple_action
def push_current_waypoint_to_stack(b: SupportsPushCurrentWaypointToStackAction):
    if (desired_waypoint := b.get_desired_waypoint()) is not None:
        b.add_priority_destination(desired_waypoint)
    return btreeny.SUCCESS


class SupportsClearCurrentWaypointAction(Protocol):
    def set_desired_waypoint(self, location: NamedPosition | None): ...


@btreeny.simple_action
def clear_current_waypoint(b: SupportsClearCurrentWaypointAction):
    b.set_desired_waypoint(None)
    return btreeny.SUCCESS


class SupportsEnsureAllWaypointsCompleteAction(Protocol):
    def ask_count_remaining_destinations(self) -> int: ...


@btreeny.simple_action
def ensure_all_waypoints_completed(b: SupportsEnsureAllWaypointsCompleteAction):
    if b.ask_count_remaining_destinations() == 0:
        return btreeny.SUCCESS
    return btreeny.FAILURE


def make_navigate() -> btreeny.TreeNode[Blackboard]:
    return btreeny.redo(
        lambda: btreeny.sequential(set_next_waypoint(), move_to_waypoint())
    )


def make_recharge() -> btreeny.TreeNode[Blackboard]:
    return btreeny.sequential(
        # Be sure to save the current waypoint to allow resuming of the interrupted task
        push_current_waypoint_to_stack(),
        clear_current_waypoint(),
        set_home(),
        move_to_waypoint(),
        start_charging(),
        wait_for_charge_complete(),
        stop_charging(),
    )


def main(rerun: bool = False, rerun_url: str = "rerun+http://172.26.96.1:9876/proxy"):
    robot = Robot(speed=0.3, discharge_rate=0.1)

    # Using a switch means that when we are low on battery we will enter a failsafe mode where
    # we move to our charger. When(/if) the failsafe behvior returns, the action finishes.
    # By wrapping this switch in a redo (which retries on success, and exits on failure),
    # we will allow the robot to continue to the next waypoint.
    loop = btreeny.redo(
        lambda: btreeny.switch(
            has_battery,
            make_navigate(),
            make_recharge(),
        )
    )

    root = btreeny.fallback(
        loop,
        ensure_all_waypoints_completed(),
    )

    blackboard = Blackboard(
        robot=robot,
        destinations=deque(("north", "east", "south", "west", "home")),
        current_location=LOCATIONS["home"],
    )
    if rerun:
        rr.init("btreeny-waypoint-navigation", spawn=False)
        rr.connect_grpc(rerun_url)
        rr.log("world", rr.ViewCoordinates.RIGHT_HAND_Z_UP, static=True)
        rr.log(
            "world/xyz",
            rr.Arrows3D(
                vectors=[[1, 0, 0], [0, 1, 0], [0, 0, 1]],
                colors=[[255, 0, 0], [0, 255, 0], [0, 0, 255]],
            ),
            static=True,
        )
    result: None | btreeny.TreeStatus = None
    try:
        with Live(auto_refresh=False, console=console) as live:
            with root as tree:
                while True:
                    robot.sense()
                    result = tree(blackboard)
                    if rerun:
                        rr.set_time("posix_time", timestamp=time.monotonic())
                        rr.log(
                            "world/robot",
                            rr.Points3D(
                                [(robot.position.x, robot.position.y, 0)], radii=[0.2]
                            ),
                        )
                        graph = btreeny.viz.rerun_tree_graph()
                        rr.log("behavior-tree", graph.nodes, graph.edges)

                    columns = Columns(
                        [btreeny.viz.get_rich_tree()], equal=True, expand=True
                    )
                    live.update(columns, refresh=True)
                    if result != btreeny.RUNNING:
                        break
                    time.sleep(0.1)
    finally:
        console.print(f"Ended with result {result}")
        console.print(blackboard)


if __name__ == "__main__":
    import typer

    typer.run(main)
