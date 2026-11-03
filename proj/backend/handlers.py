"""Task handlers: what a worker actually does for each task type.

To add a new task type, write a function that takes the payload (dict)
and returns a JSON-serializable result, then register it in HANDLERS.
"""
import time

MAX_SLEEP_SECONDS = 10


def echo(payload):
    return {"echo": payload}


def sum_numbers(payload):
    numbers = payload.get("numbers")
    if not isinstance(numbers, list) or not numbers:
        raise ValueError("'numbers' must be a non-empty list")
    if not all(
        isinstance(n, (int, float)) and not isinstance(n, bool)
        for n in numbers
    ):
        raise ValueError("'numbers' must contain only numbers")
    return {"sum": sum(numbers)}


def sleep_task(payload):
    seconds = payload.get("seconds", 1)
    if (
        isinstance(seconds, bool)
        or not isinstance(seconds, (int, float))
        or not 0 <= seconds <= MAX_SLEEP_SECONDS
    ):
        raise ValueError(f"'seconds' must be between 0 and {MAX_SLEEP_SECONDS}")
    time.sleep(seconds)
    return {"slept": seconds}


HANDLERS = {
    "echo": echo,
    "sum": sum_numbers,
    "sleep": sleep_task,
}

DEFAULT_TASK_TYPE = "echo"


def execute_task(payload):
    task_type = payload.get("type", DEFAULT_TASK_TYPE)
    handler = HANDLERS.get(task_type)
    if handler is None:
        raise ValueError(f"Unknown task type: {task_type}")
    return handler(payload)
