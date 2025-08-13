from collections import deque
from dataclasses import dataclass, field
import math
import time
from typing import Callable
import btreeny
import btreeny.viz
import rerun as rr
from rich.live import Live
from rich.columns import Columns


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
    position: Position = LOCATIONS["home"]
    battery: float = 1.0
    discharge_rate: float = 0.02
    charge_rate: float = 0.2
    waypoint: Position | None = None
    speed: float = 0.1
    last_tick: float = field(default_factory=time.time)

    def sense(self):
        new_time = time.time()
        dt = new_time - self.last_tick
        if self.waypoint is not None:
            self.position = move_with_speed(
                self.position, self.waypoint, self.speed, dt
            )
        self.last_tick = new_time
        self.battery = max(0, self.battery - dt * self.discharge_rate)
        if self.position.distance_to(LOCATIONS["home"]) < 0.01:
            self.battery = min(1.0, self.battery + self.charge_rate * dt)

    def tell_waypoint(self, waypoint: Position):
        self.waypoint = waypoint


@dataclass
class Blackboard:
    robot: Robot
    destinations: deque[str]
    current_location: Position
    tell_waypoint: Callable[[Position], None]
    is_charging: bool = False
    waypoint: NamedPosition | None = None


@btreeny.simple_action
def set_next_waypoint(b: Blackboard):
    if b.waypoint is not None:
        return btreeny.SUCCESS
    try:
        location = b.destinations.popleft()
    except IndexError:
        return btreeny.FAILURE
    b.waypoint = LOCATIONS[location]
    return btreeny.SUCCESS


@btreeny.simple_action
def move_to_waypoint(b: Blackboard):
    if b.waypoint is None:
        return btreeny.SUCCESS
    # Set the waypoint on the robot
    if b.robot.waypoint is None or b.robot.waypoint != b.waypoint:
        b.robot.tell_waypoint(b.waypoint)
    if b.robot.position.distance_to(b.waypoint) < 0.01:
        b.waypoint = None
        return btreeny.SUCCESS
    return btreeny.RUNNING


@btreeny.simple_action
def set_home(b: Blackboard):
    b.waypoint = LOCATIONS["home"]
    return btreeny.SUCCESS


@btreeny.simple_action
def charge_at_home(b: Blackboard):
    if b.robot.battery < 1.0:
        b.is_charging = True
        return btreeny.RUNNING
    b.is_charging = False
    return btreeny.SUCCESS


def has_battery(b: Blackboard, threshold=0.2):
    return b.robot.battery > threshold


@btreeny.simple_action
def push_current_waypoint_to_stack(b: Blackboard):
    if b.waypoint is None:
        return btreeny.SUCCESS
    b.destinations.appendleft(b.waypoint.name)
    b.waypoint = None
    return btreeny.SUCCESS


def main(rerun: bool = False, rerun_url: str = "rerun+http://172.26.96.1:9876/proxy"):
    robot = Robot(speed=0.2, discharge_rate=0.05)

    root = btreeny.redo(
        # Using a failsafe means that when we are low on battery we will enter a failsafe mode where
        # we move to our charger. When(/if) the failsafe behvior returns, the action finishes.
        # By wrapping this failsafe in a repeat, we will allow the robot to continue to the next
        # waypoint
        lambda: btreeny.failsafe(
            has_battery,
            btreeny.fallback(
                btreeny.redo(
                    lambda: btreeny.sequential(move_to_waypoint(), set_next_waypoint())
                ),
            ),
            btreeny.sequential(
                # Be sure to save the current waypoint to allow resuming of the interrupted task
                push_current_waypoint_to_stack(),
                set_home(),
                move_to_waypoint(),
                charge_at_home(),
            ),
        )
    )

    blackboard = Blackboard(
        robot=robot,
        destinations=deque(("north", "east", "south", "west", "home")),
        current_location=LOCATIONS["home"],
        tell_waypoint=robot.tell_waypoint,
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

    with Live() as live:
        with root as tree:
            while True:
                robot.sense()
                result = tree(blackboard)
                if rerun:
                    rr.set_time("posix_time", timestamp=time.time())
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
                print(robot.position, robot.battery, blackboard.destinations)
                live.update(columns)
                if result != btreeny.RUNNING:
                    break
                time.sleep(0.1)
    print(f"Ended with result {result}")
    print(blackboard)


if __name__ == "__main__":
    import typer

    typer.run(main)
