from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_socketio import SocketIO
from flask_jwt_extended import JWTManager
from flask_cors import CORS
# ==========================================================
# DATABASE
# ==========================================================

db = SQLAlchemy()

# ==========================================================
# DATABASE MIGRATIONS
# ==========================================================

migrate = Migrate()

# ==========================================================
# JWT AUTHENTICATION (ANDROID API)
# ==========================================================

jwt = JWTManager()

# ==========================================================
# CORS
# ==========================================================

cors = CORS()

# ==========================================================
# SOCKET.IO
# ==========================================================

socketio = SocketIO(
    cors_allowed_origins="*",
    async_mode="threading",
    manage_session=False
)