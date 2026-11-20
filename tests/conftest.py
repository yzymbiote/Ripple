import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ripple import db  # noqa: E402
from ripple.seed import seed  # noqa: E402


@pytest.fixture
def conn():
    c = db.connect(":memory:")
    db.init(c)
    seed(c)
    return c
