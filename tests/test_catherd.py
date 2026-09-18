import pytest

import catherd

pytestmark = pytest.mark.small


def test_dummy():
    assert catherd.__name__ == "catherd"
