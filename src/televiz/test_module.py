import pytest
from televiz.module import my_function, MyClass  # Import from the *installed* package


def test_my_function():
    assert my_function() is None  # Since my_function prints and returns None


def test_my_class():
    instance = MyClass(5)
    assert instance.get_value() == 5
