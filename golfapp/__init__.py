import os
import secrets

from flask import Flask

from . import db


def _env_flag(name, default=False):
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in ("1", "true", "yes", "ja", "on")


def create_app(test_config=None):
    app = Flask(__name__)
    app.config.update(
        DATABASE=os.environ.get("DATABASE_PATH", os.path.join(app.instance_path, "golf.sqlite")),
        SECRET_KEY=os.environ.get("SECRET_KEY") or secrets.token_hex(32),
        # Optionales Passwort für alle ändernden Aktionen (HTTP Basic Auth)
        APP_PASSWORD=os.environ.get("APP_PASSWORD", ""),
        # Zählen Final-Four-Runden zusätzlich zur Jahreswertung?
        FINAL_FOUR_IN_ANNUAL=_env_flag("FINAL_FOUR_IN_ANNUAL", False),
    )
    if test_config:
        app.config.update(test_config)

    db.init_db(app)

    from .views import bp

    app.register_blueprint(bp)
    return app
