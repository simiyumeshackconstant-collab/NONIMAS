import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent


class Config:
    # -----------------------------
    # Application
    # -----------------------------
    APP_NAME = "Nonimas"
    SECRET_KEY = os.getenv("SECRET_KEY", "change-this-secret")
    MAX_CONTENT_LENGTH = 50 * 1024 * 1024

    # -----------------------------
    # Database
    # -----------------------------
    DATABASE_URL = os.getenv("DATABASE_URL")

    if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
        DATABASE_URL = DATABASE_URL.replace(
            "postgres://",
            "postgresql://",
            1
        )

    SQLALCHEMY_DATABASE_URI = (
        DATABASE_URL
        if DATABASE_URL
        else "sqlite:///local.db"
    )

    SQLALCHEMY_TRACK_MODIFICATIONS = False

    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_pre_ping": True,
        "pool_recycle": 280,
        "pool_size": 5,
        "max_overflow": 10,
    }

    # -----------------------------
    # Upload Folders
    # -----------------------------
    UPLOAD_FOLDER = BASE_DIR / "uploads"
    POST_UPLOAD_FOLDER = UPLOAD_FOLDER / "posts"
    DP_UPLOAD_FOLDER = UPLOAD_FOLDER / "user_dp_pics"
    CHAT_UPLOAD_FOLDER = UPLOAD_FOLDER / "chat"
    VIDEO_UPLOAD_FOLDER = UPLOAD_FOLDER / "videos"

    STATIC_FOLDER = BASE_DIR / "static"
    APP_ICON_FOLDER = STATIC_FOLDER / "icons"

    # -----------------------------
    # Cloudinary
    # -----------------------------
    CLOUDINARY_NAME = os.getenv("CLOUDINARY_NAME")
    CLOUDINARY_KEY = os.getenv("CLOUDINARY_KEY")
    CLOUDINARY_SECRET = os.getenv("CLOUDINARY_SECRET")

    # -----------------------------
    # Email
    # -----------------------------
    EMAIL_USER = os.getenv("EMAIL_USER")
    EMAIL_PASS = os.getenv("EMAIL_PASS")

    BREVO_API_KEY = os.getenv("BREVO_API_KEY")
    RESEND_API_KEY = os.getenv("RESEND_API_KEY")

    # -----------------------------
    # PayPal
    # -----------------------------
    PAYPAL_CLIENT_ID = os.getenv("PAYPAL_CLIENT_ID")
    PAYPAL_CLIENT_SECRET = os.getenv("PAYPAL_CLIENT_SECRET")
    PAYPAL_WEBHOOK_ID = os.getenv("PAYPAL_WEBHOOK_ID")
    PAYPAL_MODE = os.getenv("PAYPAL_MODE", "sandbox")

    # -----------------------------
    # Android API
    # -----------------------------
    JWT_SECRET_KEY = os.getenv(
        "JWT_SECRET_KEY",
        SECRET_KEY
    )

    JWT_ACCESS_TOKEN_EXPIRES = 60 * 60 * 24 * 7

    # -----------------------------
    # Allowed Upload Types
    # -----------------------------
    ALLOWED_IMAGE_EXTENSIONS = {
        "png",
        "jpg",
        "jpeg",
        "gif",
        "webp",
    }

    ALLOWED_VIDEO_EXTENSIONS = {
        "mp4",
        "mov",
        "avi",
        "mkv",
        "webm",
    }

    ALLOWED_DOCUMENT_EXTENSIONS = {
        "pdf",
        "doc",
        "docx",
        "txt",
    }


class DevelopmentConfig(Config):
    DEBUG = True


class TestingConfig(Config):
    TESTING = True


class ProductionConfig(Config):
    DEBUG = False


config = {
    "development": DevelopmentConfig,
    "testing": TestingConfig,
    "production": ProductionConfig,
    "default": ProductionConfig,
}