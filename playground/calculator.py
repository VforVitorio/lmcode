"""Simple calculator — playground file for testing lmcode read/write/run features."""


def add(a: float, b: float) -> float:
    """Return the sum of a and b."""
    return a + b


def subtract(a: float, b: float) -> float:
    """Return the difference of a and b."""
    return a - b


def divide(a: float, b: float) -> float:
    """Return the result of dividing a by b, handling division by zero."""
    if b == 0:
        return "error: Division by zero"
    else:
        return a / b


if __name__ == '__main__':
    print(divide(10, 2))  # Should print 5.0
    print(divide(5, 0))   # Should print error: Division by zero
