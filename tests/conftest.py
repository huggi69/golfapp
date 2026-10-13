import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest  # noqa: E402

from golfapp import create_app  # noqa: E402


@pytest.fixture
def client(tmp_path):
    app = create_app({"DATABASE": str(tmp_path / "test.sqlite"), "TESTING": True,
                      "APP_PASSWORD": "", "FINAL_FOUR_IN_ANNUAL": False})
    with app.test_client() as c:
        c.post("/players", data={"action": "add", "name": "Anna"})
        c.post("/players", data={"action": "add", "name": "Ben"})
        yield c
