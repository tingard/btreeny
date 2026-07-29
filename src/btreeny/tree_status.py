from enum import Enum


class TreeStatus(str, Enum):
    RUNNING = "RUNNING"
    SUCCESS = "SUCCESS"
    FAILURE = "FAILURE"
