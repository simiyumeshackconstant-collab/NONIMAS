import os
import json

import firebase_admin
from firebase_admin import credentials

import cloudinary

from flask import Flask

from config import config
from extensions import (
    db,
    migrate,
    jwt,
    cors,
    socketio
)

from helpers import seed_gifts

from web import web_bp
from main import api_bp


# ==========================================================
# CREATE APPLICATION
# ==========================================================

app = Flask(__name__)
app.config.from_object(config["production"])


# ==========================================================
# FIREBASE ADMIN
# ==========================================================

firebase_json = os.environ.get(
    "FIREBASE_SERVICE_ACCOUNT_JSON"
)

if not firebase_json:
    raise RuntimeError(
        "FIREBASE_SERVICE_ACCOUNT_JSON is not configured"
    )

if not firebase_admin._apps:

    cred = credentials.Certificate(
        json.loads(firebase_json)
    )

    firebase_admin.initialize_app(cred)


# ==========================================================
# INITIALIZE EXTENSIONS
# ==========================================================

db.init_app(app)

migrate.init_app(app, db)

jwt.init_app(app)

cors.init_app(
    app,
    resources={
        r"/api/*": {
            "origins": "*"
        }
    }
)

socketio.init_app(
    app,
    cors_allowed_origins="*",
    async_mode="threading",
    manage_session=False
)


# ==========================================================
# CLOUDINARY
# ==========================================================

cloudinary.config(
    cloud_name=app.config["CLOUDINARY_NAME"],
    api_key=app.config["CLOUDINARY_KEY"],
    api_secret=app.config["CLOUDINARY_SECRET"],
    secure=True
)


# ==========================================================
# REGISTER BLUEPRINTS
# ==========================================================

app.register_blueprint(web_bp)

app.register_blueprint(
    api_bp,
    url_prefix="/api"
)


# ==========================================================
# START APPLICATION
# ==========================================================

if __name__ == "__main__":

    with app.app_context():
        seed_gifts()

    port = int(
        os.environ.get(
            "PORT",
            10000
        )
    )

    socketio.run(
        app,
        host="0.0.0.0",
        port=port,
        debug=True,
        allow_unsafe_werkzeug=True
    )