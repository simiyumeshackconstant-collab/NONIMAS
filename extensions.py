from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_socketio import SocketIO
from flask_jwt_extended import JWTManager
from flask_cors import CORS

# Database
db = SQLAlchemy()

# Database migrations
migrate = Migrate()

# JWT Authentication (Android)
jwt = JWTManager()

# CORS (Android API)
cors = CORS()

# Socket.IO (Website Chat)
socketio = SocketIO(
    cors_allowed_origins="*",
    async_mode="threading",
    manage_session=False
)