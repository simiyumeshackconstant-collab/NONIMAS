import os

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

    port = int(os.environ.get("PORT", 10000))

    socketio.run(
        app,
        host="0.0.0.0",
        port=port,
        debug=True,
        allow_unsafe_werkzeug=True
    )