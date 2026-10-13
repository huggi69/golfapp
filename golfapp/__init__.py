import os
import secrets
from datetime import timedelta
from pathlib import Path

from flask import Flask
from werkzeug.middleware.proxy_fix import ProxyFix

from . import db


def _env_flag(name, default=False):
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in ("1", "true", "yes", "ja", "on")


def _secret_key(database_path):
    """SECRET_KEY aus der Umgebung oder dauerhaft neben der Datenbank gespeichert.

    Ein fester Schlüssel ist nötig, damit Logins einen Neustart überleben.
    """
    key = os.environ.get("SECRET_KEY")
    if key:
        return key
    path = Path(database_path).with_name("secret_key")
    try:
        return path.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        path.parent.mkdir(parents=True, exist_ok=True)
        key = secrets.token_hex(32)
        path.write_text(key, encoding="utf-8")
        path.chmod(0o600)
        return key


def create_app(test_config=None):
    app = Flask(__name__)
    app.config.update(
        DATABASE=os.environ.get("DATABASE_PATH", os.path.join(app.instance_path, "golf.sqlite")),
        # Zählen Final-Four-Runden zusätzlich zur Jahreswertung? (Standard je Saison)
        FINAL_FOUR_IN_ANNUAL=_env_flag("FINAL_FOUR_IN_ANNUAL", False),
        PERMANENT_SESSION_LIFETIME=timedelta(days=180),
        SESSION_COOKIE_SAMESITE="Lax",  # schützt Formulare vor Aufrufen von fremden Seiten
        SESSION_COOKIE_SECURE=_env_flag("SESSION_COOKIE_SECURE", False),
        # Läuft die App hinter einem Reverse Proxy (Traefik)? Dann X-Forwarded-* auswerten.
        TRUST_PROXY=_env_flag("TRUST_PROXY", False),
    )
    if test_config:
        app.config.update(test_config)
    if not app.config.get("SECRET_KEY"):
        app.config["SECRET_KEY"] = _secret_key(app.config["DATABASE"])

    if app.config["TRUST_PROXY"]:
        # Genau ein Proxy davor: Protokoll (https), Host und Client-IP von dort übernehmen
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

    db.init_db(app)

    from . import auth
    from .views import bp

    app.register_blueprint(auth.bp)
    app.register_blueprint(bp)
    app.before_request(auth.require_login)
    return app
