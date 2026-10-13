import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest  # noqa: E402

from golfapp import create_app  # noqa: E402


def make_app(tmp_path, **config):
    return create_app({"DATABASE": str(tmp_path / "test.sqlite"), "TESTING": True,
                       "FINAL_FOUR_IN_ANNUAL": False, **config})


@pytest.fixture
def client(tmp_path):
    """Angemeldet als Anna (über die Ersteinrichtung); Ben ohne Login."""
    app = make_app(tmp_path)
    with app.test_client() as c:
        c.post("/login", data={"name": "Anna", "password": "geheim1", "password2": "geheim1"})
        c.post("/players", data={"action": "add", "name": "Ben"})
        yield c
