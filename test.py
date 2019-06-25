import pytest  # noqa: F401; pylint: disable=unused-variable
from utils import generate_keys


# Test to make sure there isn't a fatal error with Python
def test1():
    assert 1 == 1


def test2():
    res1, res2 = generate_keys()
    assert (res1 is not None) and (res2 is not None)
