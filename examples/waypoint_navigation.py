from collections import deque
import contextvars
from dataclasses import dataclass
import time
from typing import Callable
import btreeny
from btreeny._tree_status import TreeStatus
from btreeny.trace import print_trace
import itertools

LOCATIONS = {
    "home": (0, 0),
    "north": (1, 0),
    "east": (0, 1),
    "west": (0, -1),
    "south": (-1, 0),
}

@dataclass
class Blackboard:
    destinations: deque[str]
    current_location: tuple[float, float]
    tell_waypoint: Callable[[tuple[float, float]], None]
    current_battery: float = 1.0

    waypoint: tuple[float, float] | None = None
    

@btreeny.simple_action
def set_next_waypoint(b: Blackboard):
    location = b.destinations.popleft()
    location_x, location_y = LOCATIONS[location]
    b.waypoint = (location_x, location_y)
    return btreeny.TreeStatus.SUCCESS


@btreeny.simple_action
def move_to_waypoint(b: Blackboard):
    if b.waypoint is None:
        return btreeny.TreeStatus.FAILURE
    
    return btreeny.TreeStatus.SUCCESS

@btreeny.simple_action
def set_home(b: Blackboard):
    b.waypoint = LOCATIONS["home"]
    return btreeny.TreeStatus.SUCCESS

def has_battery(b: Blackboard):
    return b.current_battery > 0.1


def move_with_speed(a: tuple[float, float], b: tuple[float, float], speed: float, time: float) -> tuple[float, float]:
    """Move from a to b with a given speed for a given time, stopping when b is reached"""
    assert time >= 0
    if time == 0:
        return a
    
    raise NotImplementedError()

class Robot:
    def __init__(self):
        self.position = LOCATIONS["home"]
        self.waypoint: tuple[float, float] | None = None
        self.speed = 0.1
        self.last_tick = time.time()
    
    def sense(self):
        new_time = time.time()
        dt = new_time - self.last_tick
        if self.waypoint is not None:
            self.position = move_with_speed(self.position, self.waypoint, self.speed, dt)
        self.last_tick = new_time

    def tell_waypoint(self, waypoint: tuple[float, float]):
        self.waypoint = waypoint
        

def main():
    robot = Robot()
    # Reactive means run nominal branch if condition is True and error branch if False
    root = btreeny.react(
        has_battery,
        btreeny.sequential(set_next_waypoint(), move_to_waypoint()),
        btreeny.sequential(set_home(), move_to_waypoint()),
    )

    blackboard = Blackboard(
        destinations=deque(("north", "east", "south", "west", "home")),
        current_location=LOCATIONS["home"],
        tell_waypoint=robot.tell_waypoint
    )
    with root as tree:
        while True:
            result = tree(blackboard)
            print()
            print_trace()
            print()
            if result != TreeStatus.RUNNING:
                break
    print(f"Ended with result {result}")
    print(blackboard)
    
if __name__ == "__main__":
    ctx = contextvars.copy_context()
    ctx.run(main)