from datetime import datetime
from decimal import Decimal

from sqlalchemy import Numeric
from sqlalchemy.orm import validates

from extensions import db

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    full_name = db.Column(db.String(150), nullable=False)
    phone = db.Column(db.String(20), unique=True, nullable=False)
    password = db.Column(db.String(255), nullable=False)
    id_number = db.Column(db.String(50), nullable=True)
    is_online = db.Column(db.Boolean, default=False)
    last_seen = db.Column(db.DateTime)
    balance = db.Column(db.Float, default=0.0)  # USD now
    is_admin = db.Column(db.Boolean, default=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    email = db.Column(db.String(120), unique=True, nullable=True)
    country = db.Column(db.String(100), nullable=True)
    otp_code = db.Column(db.String(6), nullable=True)
    otp_expiry = db.Column(db.DateTime, nullable=True)
    is_verified = db.Column(db.Boolean, default=False)
    user_dp_pic = db.Column(db.String(255), nullable=True)
    bio = db.Column(db.String(255), default="")
class Notification(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer)
    title = db.Column(db.String(255))
    message = db.Column(db.Text)
    is_read = db.Column(
        db.Boolean,
        default=False
    )
    created_at = db.Column(
        db.DateTime,
        default=datetime.utcnow
    )
class Gift(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50))
    value = db.Column(db.Float)  # internal value for payout calculations
    price = db.Column(db.Float)
    payout = db.Column(db.Float)
    icon = db.Column(db.String(255))
class Like(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, nullable=False)
    post_id = db.Column(db.Integer, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    is_active = db.Column(db.Boolean, default=True)
    rewarded = db.Column(db.Boolean, default=False)
class Post(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, nullable=False)
    anon_name = db.Column(db.String(100))
    content = db.Column(db.Text)
    media_url = db.Column(db.String(255))
    media_type = db.Column(db.String(20))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
class Buddy(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer)
    buddy_id = db.Column(db.Integer)
    buddy_name = db.Column(db.String(150))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    seen = db.Column(db.Boolean, default=False)   # NEW
    user_dp_pic = db.Column(
        db.String(255),
        default='default_avatar.png'
    )
    bio = db.Column(
        db.String(255),
        default=""
    )
class Wallet(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, unique=True)
    balance = db.Column(db.Float, default=0.0)
class Earning(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer)
    amount = db.Column(db.Float)
    status = db.Column(db.String(20), default="pending")
    seen = db.Column(db.Boolean, default=False)   # NEW
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
class GiftTransaction(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    sender_id = db.Column(db.Integer)
    receiver_id = db.Column(db.Integer)
    post_id = db.Column(db.Integer)
    gift_id = db.Column(db.Integer)
    quantity = db.Column(db.Integer, default=1)
    total_amount = db.Column(db.Float)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
class UserGiftBalance(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, nullable=False)
    gift_id = db.Column(db.Integer, nullable=False)
    quantity = db.Column(db.Integer, default=0)
class ChatMessage(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    media_url = db.Column(db.String(500))
    sender_id = db.Column(db.Integer, index=True)
    media_type = db.Column(db.String(50))
    receiver_id = db.Column(db.Integer, index=True)
    message = db.Column(db.Text)
    is_read = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
class Comment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, nullable=False)
    post_id = db.Column(db.Integer, nullable=False)
    comment = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
class DepositTransaction(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, nullable=False)
    paypal_order_id = db.Column(
        db.String(100),
        unique=True,
        nullable=False
    )
    amount = db.Column(db.Float, nullable=False)   # USD
    status = db.Column(
        db.String(20),
        default="pending"
    )
    created_at = db.Column(
        db.DateTime,
        default=datetime.utcnow
    )
class WithdrawalRequest(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, nullable=False)
    amount = db.Column(db.Float, nullable=False)
    account_name = db.Column(db.String(150))
    bank_name = db.Column(db.String(150))
    account_number = db.Column(db.String(100))
    status = db.Column(
        db.String(20),
        default="pending"
    )  # pending, approved, rejected
    created_at = db.Column(
        db.DateTime,
        default=datetime.utcnow
    )
    processed_at = db.Column(
        db.DateTime,
        nullable=True
    )
# ============================================================
# MODEL VALIDATORS
# ============================================================

@validates("email")
def validate_email(self, key, value):
    if value:
        value = value.strip().lower()
    return value


@validates("phone")
def validate_phone(self, key, value):
    if value:
        value = value.strip()
    return value


# ============================================================
# APPLICATION CONSTANTS
# ============================================================

LIKE_EARN = Decimal("0.0010")
COMMENT_EARN = Decimal("0.0025")


# ============================================================
# EXPORTS
# ============================================================

__all__ = [
    "User",
    "Notification",
    "Gift",
    "Post",
    "Like",
    "Comment",
    "Buddy",
    "Wallet",
    "Earning",
    "GiftTransaction",
    "UserGiftBalance",
    "ChatMessage",
    "DepositTransaction",
    "WithdrawalRequest",
    "LIKE_EARN",
    "COMMENT_EARN",
]