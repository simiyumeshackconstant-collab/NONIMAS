import random
import string
import os
from decimal import Decimal
from functools import wraps

import requests
from flask import jsonify, redirect, session, url_for, flash
from werkzeug.security import generate_password_hash, check_password_hash

from extensions import db
from models import (
    Buddy,
    Notification,
    Wallet,
    Gift,
)

# ==========================================================
# PASSWORD HELPERS
# ==========================================================

hash_password = generate_password_hash
verify_password = check_password_hash


# ==========================================================
# WEBSITE AUTH DECORATORS
# ==========================================================

def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if "user_id" not in session:
            flash("Please log in first.", "error")
            return redirect(url_for("web.login"))
        return f(*args, **kwargs)
    return wrapper


def admin_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if "user_id" not in session:
            flash("Please log in first.")
            return redirect(url_for("web.login"))

        if not session.get("is_admin"):
            flash("Admin access only.")
            return redirect(url_for("web.nonimas"))

        return f(*args, **kwargs)

    return wrapper


# ==========================================================
# WALLET
# ==========================================================

def get_wallet(user_id):
    wallet = Wallet.query.filter_by(user_id=user_id).first()

    if wallet is None:
        wallet = Wallet(
            user_id=user_id,
            balance=Decimal("0.00")
        )
        db.session.add(wallet)
        db.session.commit()

    return wallet


def add_to_wallet(user_id, amount):
    wallet = get_wallet(user_id)

    wallet.balance += Decimal(str(amount))

    db.session.commit()

    return wallet


def deduct_from_wallet(user_id, amount):
    wallet = get_wallet(user_id)

    amount = Decimal(str(amount))

    if wallet.balance < amount:
        return False

    wallet.balance -= amount

    db.session.commit()

    return True


# ==========================================================
# OTP
# ==========================================================

def generate_otp():
    return "".join(
        random.choices(
            string.digits,
            k=6
        )
    )


def send_otp_email(to_email, otp):
    api_key = os.getenv("BREVO_API_KEY")

    if not api_key:
        raise RuntimeError("BREVO_API_KEY missing")

    headers = {
        "accept": "application/json",
        "api-key": api_key,
        "content-type": "application/json"
    }

    payload = {
        "sender": {
            "name": "Nonimas",
            "email": os.getenv("EMAIL_USER")
        },
        "to": [
            {
                "email": to_email
            }
        ],
        "subject": "Your OTP Code",
        "htmlContent": f"""
        <h2>Nonimas Verification</h2>
        <p>Your OTP code is:</p>
        <h1>{otp}</h1>
        <p>This code expires in 5 minutes.</p>
        """
    }

    response = requests.post(
        "https://api.brevo.com/v3/smtp/email",
        headers=headers,
        json=payload,
        timeout=30
    )

    response.raise_for_status()

    return True


# ==========================================================
# NOTIFICATIONS
# ==========================================================

def create_notification(
    user_id,
    title,
    message
):
    notification = Notification(
        user_id=user_id,
        title=title,
        message=message
    )

    db.session.add(notification)

    db.session.commit()

    return notification


# ==========================================================
# BUDDY MILESTONES
# ==========================================================

def create_buddy_milestone(user_id):
    total = Buddy.query.filter_by(
        buddy_id=user_id
    ).count()

    milestones = [
        100,
        500,
        1000,
        5000
    ]

    if total in milestones:
        create_notification(
            user_id=user_id,
            title="Buddy Milestone",
            message=f"Congratulations! You reached {total} buddies."
        )


# ==========================================================
# GIFTS
# ==========================================================

def seed_gifts():
    gifts = [
        {
            "name": "Caros",
            "value": Decimal("0.10"),
            "price": Decimal("0.10"),
            "payout": Decimal("0.07")
        },
        {
            "name": "Cons",
            "value": Decimal("1.00"),
            "price": Decimal("1.00"),
            "payout": Decimal("0.80")
        },
        {
            "name": "Preshas",
            "value": Decimal("5.00"),
            "price": Decimal("5.00"),
            "payout": Decimal("4.60")
        },
        {
            "name": "Stacs",
            "value": Decimal("10.00"),
            "price": Decimal("10.00"),
            "payout": Decimal("9.50")
        },
        {
            "name": "Poulets",
            "value": Decimal("25.00"),
            "price": Decimal("25.00"),
            "payout": Decimal("24.00")
        }
    ]

    for gift in gifts:
        exists = Gift.query.filter_by(
            name=gift["name"]
        ).first()

        if not exists:
            db.session.add(
                Gift(**gift)
            )

    db.session.commit()


# ==========================================================
# JSON RESPONSES
# ==========================================================

def success_response(
    message,
    data=None,
    status=200
):
    return jsonify({
        "success": True,
        "message": message,
        "data": data or {}
    }), status


def error_response(
    message,
    status=400
):
    return jsonify({
        "success": False,
        "message": message
    }), status
ALLOWED_DP_EXTENSIONS = {
    "png",
    "jpg",
    "jpeg",
    "webp",
    "gif",
    "apk",
    "mp4",
    "mov",
    "docx",
    "pdf"

}


def allowed_file(filename):
    return (
        "." in filename and
        filename.rsplit(".", 1)[1].lower()
        in ALLOWED_DP_EXTENSIONS
    )