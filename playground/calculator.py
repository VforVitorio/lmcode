"""Simple calculator — playground file for testing lmcode read/write/run features."""


def add(a: float, b: float) -> float:
    """Return the sum of a and b."""
    return a + b


def subtract(a: float, b: float) -> float:
    """Return the difference of a and b."""
    return a - b


if __name__ == "__main__":
    print(add(3, 5))       # 8
    print(subtract(10, 4)) # 6
