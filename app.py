import os
import json

import firebase_admin
from firebase_admin import credentials

import cloudinary

from flask import Flask
from mqtt_service import mqtt_service

from config import config
from extensions import (
    db,
    migrate,
    jwt,
    cors
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

firebase_config_value = os.environ.get(
    "FIREBASE_SERVICE_ACCOUNT_JSON", ""
).strip()

if not firebase_config_value:
    raise RuntimeError(
        "FIREBASE_SERVICE_ACCOUNT_JSON is missing or empty. "
        "Set it to valid Firebase service-account JSON "
        "or a path to a service-account JSON file."
    )

if not firebase_admin._apps:
    try:
        # Option 1: The environment variable contains a file path.
        if os.path.isfile(firebase_config_value):
            cred = credentials.Certificate(firebase_config_value)

        # Option 2: The environment variable contains JSON text.
        else:
            firebase_config = json.loads(firebase_config_value)
            cred = credentials.Certificate(firebase_config)

        firebase_admin.initialize_app(cred)

    except json.JSONDecodeError as exc:
        raise RuntimeError(
            "FIREBASE_SERVICE_ACCOUNT_JSON is not valid JSON "
            "and does not point to an existing credentials file. "
            "Check the environment variable configuration."
        ) from exc

    except (ValueError, OSError) as exc:
        raise RuntimeError(
            "Firebase service-account credentials could not "
            "be loaded. Check the credentials and file path."
        ) from exc

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
mqtt_service.flask_app = app
mqtt_service.connect()

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

    app.run(
        host="0.0.0.0",
        port=port,
        debug=False
    )