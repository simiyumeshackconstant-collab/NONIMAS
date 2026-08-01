from flask import (
    Blueprint,
    render_template,
    request,
    redirect,
    current_app,
    url_for,
    flash,
    jsonify,
    session,
    send_from_directory
)

from extensions import (
    db,
    socketio,
    csrf
)

from werkzeug.security import (
    generate_password_hash,
    check_password_hash
)

from werkzeug.utils import secure_filename

from functools import wraps
from datetime import datetime, timedelta

from dotenv import load_dotenv
load_dotenv()

import os
import random
import string
import uuid
import mimetypes
from pathlib import Path

from sqlalchemy import text
from werkzeug.exceptions import RequestEntityTooLarge

import cloudinary
import cloudinary.uploader

from email.mime.text import MIMEText

from flask_wtf.csrf import CSRFProtect

# ==========================================================
# WEBSITE BLUEPRINT
# ==========================================================

web_bp = Blueprint("web", __name__)

# ==========================================================
# STATIC PATHS
# ==========================================================

BASE_DIR = Path(__file__).resolve().parent

STATIC_FOLDER = os.path.join(BASE_DIR, "static")

APP_ICON_FOLDER = os.path.join(STATIC_FOLDER, "icons")

# ==========================================================
# MODELS
# ==========================================================

from models import (
    User,
    Notification,
    Gift,
    Like,
    Post,
    Buddy,
    Wallet,
    Earning,
    GiftTransaction,
    UserGiftBalance,
    ChatMessage,
    Comment,
    DepositTransaction,
    WithdrawalRequest,
    LIKE_EARN,
    COMMENT_EARN,
)

from helpers import (
    login_required,
    admin_required,
    add_to_wallet,
    generate_otp,
    send_otp_email,
    create_buddy_milestone,
    seed_gifts,
    hash_password,
    verify_password,
    success_response,
    error_response,
    allowed_file
)
# ---------------- ROUTES ----------------
@web_bp.route("/")
@csrf.exempt
@login_required
def nonimas():
    if not session.get("is_admin") and not session.get("user_id"):
        flash("Please log in first.", "error")
        return redirect(url_for("web.login"))
    return render_template("nonimas.html")
# -------- ACTIONS --------
@web_bp.route("/search")
@csrf.exempt
@login_required
def search():

    q = request.args.get("q", "").strip()

    if not q:
        return jsonify({
            "users": [],
            "posts": [],
            "messages": [],
            "transactions": []
        })

    user_id = session["user_id"]

    users = User.query.filter(
        User.full_name.ilike(f"%{q}%")
    ).limit(10).all()

    posts = Post.query.filter(
        Post.content.ilike(f"%{q}%")
    ).limit(10).all()

    messages = ChatMessage.query.filter(
        (
            (ChatMessage.sender_id == user_id) |
            (ChatMessage.receiver_id == user_id)
        ) &
        ChatMessage.message.ilike(f"%{q}%")
    ).limit(10).all()

    transactions = DepositTransaction.query.filter(
        DepositTransaction.paystack_reference.ilike(f"%{q}%")
    ).limit(10).all()

    return jsonify({

        "users": [
            {
                "id": u.id,
                "name": u.full_name,
                "dp": u.user_dp_pic
            }
            for u in users
        ],

        "posts": [
            {
                "id": p.id,
                "content": p.content[:100]
            }
            for p in posts
        ],

        "messages": [
            {
                "id": m.id,
                "message": m.message[:100],
                "sender": m.sender_id,
                "receiver": m.receiver_id
            }
            for m in messages
        ],

        "transactions": [
            {
                "id": t.id,
                "reference": t.paystack_reference,
                "amount": t.amount
            }
            for t in transactions
        ]
    })
@web_bp.route("/search_page")
@login_required
def search_page():
    return render_template("search.html")
from flask import send_file

@web_bp.route("/download_apk")
def download_apk():
    return send_file(
        "static/downloads/Nonimas.apk",
        as_attachment=True
    )
@web_bp.route("/notification_count")
@login_required
def notification_count():

    count = Notification.query.filter_by(
        user_id=session["user_id"],
        is_read=False
    ).count()

    return jsonify({
        "count": count
    })
@web_bp.route("/notifications")
@csrf.exempt
@login_required
def notifications():

    Notification.query.filter_by(
        user_id=session["user_id"],
        is_read=False
    ).update({
        "is_read": True
    })

    db.session.commit()

    notifications = Notification.query.filter_by(
        user_id=session["user_id"]
    ).order_by(
        Notification.created_at.desc()
    ).all()

    return render_template(
        "notifications.html",
        notifications=notifications
    )
@web_bp.route("/like_post", methods=["POST"])
@csrf.exempt
@login_required
def like_post():

    data = request.json

    user_id = session["user_id"]
    post_id = int(data["post_id"])

    post = Post.query.get(post_id)

    if not post:
        return jsonify({"error": "Post not found"})

    like = Like.query.filter_by(
        user_id=user_id,
        post_id=post_id
    ).first()

    # FIRST TIME EVER
    if not like:

        like = Like(
            user_id=user_id,
            post_id=post_id,
            is_active=True,
            rewarded=True
        )

        db.session.add(like)

        # 💰 reward ONLY ONCE
        earning = Earning(
            user_id=post.user_id,
            amount=LIKE_EARN
        )

        db.session.add(earning)

        add_to_wallet(post.user_id, LIKE_EARN)

    else:

        # toggle active state
        like.is_active = not like.is_active

        # reward ONLY FIRST TIME
        if like.is_active and not like.rewarded:

            earning = Earning(
                user_id=post.user_id,
                amount=LIKE_EARN
            )

            db.session.add(earning)

            add_to_wallet(post.user_id, LIKE_EARN)

            like.rewarded = True

    db.session.commit()

    count = Like.query.filter_by(
        post_id=post_id,
        is_active=True
    ).count()

    return jsonify({
        "liked": like.is_active,
        "count": count
    })

@web_bp.route("/add_comment", methods=["POST"])
@csrf.exempt
@login_required
def add_comment():

    data = request.json

    user_id = session["user_id"]
    post_id = int(data["post_id"])
    text = data.get("comment", "").strip()

    if not text:
        return jsonify({"error": "Comment cannot be empty"})

    post = Post.query.get(post_id)
    if not post:
        return jsonify({"error": "Post not found"})

    comment = Comment(
        user_id=user_id,
        post_id=post_id,
        comment=text
    )

    db.session.add(comment)

    # 💰 creator earns per comment
    earning = Earning(
        user_id=post.user_id,
        amount=COMMENT_EARN
    )
    db.session.add(earning)

    # 💳 ADD TO WALLET (NEW)
    add_to_wallet(post.user_id, COMMENT_EARN)

    db.session.commit()

    total = Comment.query.filter_by(post_id=post_id).count()

    return jsonify({
        "success": True,
        "count": total
    })

@web_bp.route("/comments/<int:post_id>")
@csrf.exempt
@login_required
def get_comments(post_id):

    comments = Comment.query.filter_by(post_id=post_id) \
        .order_by(Comment.created_at.asc()).all()

    result = []

    for c in comments:

        user = User.query.get(c.user_id)

        result.append({
            "id": c.id,
            "name": user.full_name if user else "Unknown",
            "comment": c.comment,
            "created_at": c.created_at.strftime("%Y-%m-%d %H:%M")
        })

    return jsonify(result) 
@web_bp.route("/chat_page")
@csrf.exempt
@login_required
def chat_page():

    return render_template("chat.html")


@web_bp.route('/register', methods=['GET', 'POST'])
@csrf.exempt
def register():

    # ---------- STEP 1: SHOW FORM FIRST ----------
    if request.method == "GET":
        return render_template("register.html")
    # ---------- STEP 3: REGISTRATION ----------
    full_name = request.form['full_name']
    phone = request.form['phone']
    password = request.form['password']
    confirm_password = request.form['confirm_password']
    email = request.form.get("email")

    if password != confirm_password:
        flash("Passwords do not match")
        return redirect(url_for('web.register'))

    if User.query.filter_by(phone=phone).first():
        flash("Phone already exists")
        return redirect(url_for('web.register'))

    if email and User.query.filter_by(email=email).first():
        flash("Email already exists")
        return redirect(url_for('web.register'))

    otp = generate_otp()

    new_user = User(
        full_name=full_name,
        phone=phone,
        password=generate_password_hash(password),
        email=email,
        country=request.form.get("country"),
        otp_code=otp,
        otp_expiry=datetime.utcnow() + timedelta(minutes=5),
        is_verified=False
    )

    db.session.add(new_user)
    db.session.commit()

    session["pending_user_id"] = new_user.id
    try:
        if email:
            send_otp_email(email, otp)
        flash("OTP sent to your email, Check your spam folder if you don't see it.")
    except Exception as e:
        print("OTP error:", e)
        flash("Failed to send OTP email. Please try again.")

    return redirect(url_for("web.verify_account"))

# ----------- Login -----------

@web_bp.route("/login", methods=["GET", "POST"])
@csrf.exempt
def login():

    if request.method == "POST":

        identifier = request.form.get("identifier")  # one field

        password = request.form.get("password")


        identifier = identifier.strip().lower()


        # Detect email vs phone

        if "@" in identifier:

            user = User.query.filter_by(email=identifier).first()

        else:

            user = User.query.filter_by(phone=identifier).first()


        if not user or not check_password_hash(user.password, password):

            flash("Invalid login details", "danger")

            return redirect(url_for("web.login"))
        if not user.is_verified:
            session["pending_user_id"] = user.id

            flash("Account not verified. Please check your email for OTP.", "warning")

            return redirect(url_for("web.verify_account"))



        session["user_id"] = user.id

        session["is_admin"] = user.is_admin


        if user.is_admin:

            return redirect(url_for("web.admin_dashboard"))


        return redirect(url_for("web.nonimas"))


    return render_template("login.html")
@web_bp.route("/verify_account", methods=["GET", "POST"])
@csrf.exempt
def verify_account():

    user_id = session.get("pending_user_id")

    if not user_id:
        return redirect(url_for("web.login"))

    user = User.query.get(user_id)

    if request.method == "POST":

        otp = request.form.get("otp")

        if otp != user.otp_code:
            flash("Invalid OTP")
            return render_template("verify_account.html")

        if datetime.utcnow() > user.otp_expiry:
            flash("OTP expired")
            return render_template("verify_account.html")

        user.is_verified = True
        user.otp_code = None
        user.otp_expiry = None

        db.session.commit()

        session.pop("pending_user_id", None)

        flash("Account verified successfully")

        return redirect(url_for("web.nonimas"))

    return render_template("verify_account.html")
@web_bp.route("/resend_otp")
@csrf.exempt
def resend_otp():

    user_id = session.get("pending_user_id")

    if not user_id:
        return redirect(url_for("web.login"))

    user = User.query.get(user_id)

    otp = generate_otp()

    user.otp_code = otp
    user.otp_expiry = datetime.utcnow() + timedelta(minutes=5)

    db.session.commit()

    send_otp_email(user.email, otp)

    flash("New OTP sent, check your spam folder if you don't see it.")

    return redirect(url_for("web.verify_account"))

# ----------- Admin Dashboard -----------
@web_bp.route("/admin_dashboard")
@login_required
@admin_required
def admin_dashboard():

    if not session.get("is_admin"):
        return redirect(url_for("web.nonimas"))

    # 💰 TOTAL REVENUE
    revenue = db.session.query(
        db.func.sum(GiftTransaction.total_amount)
    ).scalar() or 0

    # 💸 TOTAL PAYOUTS
    payouts = db.session.query(
        db.func.sum(Earning.amount)
    ).scalar() or 0

    # 📈 PROFIT
    profit = revenue - payouts

    # 👥 TOTAL USERS
    total_users = User.query.count()

    # 📝 TOTAL POSTS
    total_posts = Post.query.count()

    # 💬 TOTAL COMMENTS
    total_comments = Comment.query.count()

    # ❤️ TOTAL LIKES
    total_likes = Like.query.count()

    # 🎁 TOTAL GIFTS SENT
    total_gifts = db.session.query(
        db.func.sum(GiftTransaction.quantity)
    ).scalar() or 0

    # 🎁 MOST POPULAR GIFTS
    popular_gifts = db.session.query(
        Gift.name,
        db.func.sum(GiftTransaction.quantity)
    ).join(
        GiftTransaction,
        Gift.id == GiftTransaction.gift_id
    ).group_by(
        Gift.name
    ).order_by(
        db.func.sum(GiftTransaction.quantity).desc()
    ).limit(10).all()

    # 🏆 TOP CREATORS
    top_creators = db.session.query(
        User.full_name,
        db.func.sum(Earning.amount)
    ).join(
        Earning,
        User.id == Earning.user_id
    ).group_by(
        User.full_name
    ).order_by(
        db.func.sum(Earning.amount).desc()
    ).limit(10).all()

    # 🕒 RECENT USERS
    recent_users = User.query.order_by(
        User.timestamp.desc()
    ).all()

    # 🕒 RECENT POSTS
    recent_posts = Post.query.order_by(
        Post.created_at.desc()
    ).limit(10).all()

    return render_template(
        "admin_dashboard.html",
        revenue=revenue,
        payouts=payouts,
        profit=profit,
        total_users=total_users,
        total_posts=total_posts,
    )
@web_bp.route("/admin_users")
@csrf.exempt
@login_required
@admin_required
def admin_users():

    users = User.query.order_by(
        User.timestamp.desc()
    ).all()

    return render_template(
        "admin_users.html",
        users=users
    )
@web_bp.route(
    "/delete_selected_users",
    methods=["POST"]
)
@login_required
@csrf.exempt
@admin_required
def delete_selected_users():

    user_ids = request.form.getlist(
        "user_ids"
    )

    if not user_ids:
        flash("No users selected")
        return redirect(
            url_for("web.admin_users")
        )

    for uid in user_ids:

        user = User.query.get(uid)

        if not user:
            continue

        # Never delete admins
        if user.is_admin:
            continue

        # Delete related records

        Notification.query.filter_by(
            user_id=user.id
        ).delete()

        Post.query.filter_by(
            user_id=user.id
        ).delete()

        Comment.query.filter_by(
            user_id=user.id
        ).delete()

        Like.query.filter_by(
            user_id=user.id
        ).delete()

        Buddy.query.filter(
            (Buddy.user_id == user.id) |
            (Buddy.buddy_id == user.id)
        ).delete()

        Wallet.query.filter_by(
            user_id=user.id
        ).delete()

        Earning.query.filter_by(
            user_id=user.id
        ).delete()

        UserGiftBalance.query.filter_by(
            user_id=user.id
        ).delete()

        ChatMessage.query.filter(
            (ChatMessage.sender_id == user.id) |
            (ChatMessage.receiver_id == user.id)
        ).delete()

        WithdrawalRequest.query.filter_by(
            user_id=user.id
        ).delete()

        DepositTransaction.query.filter_by(
            user_id=user.id
        ).delete()

        db.session.delete(user)

    db.session.commit()

    flash("Selected users deleted")

    return redirect(
        url_for("web.admin_users")
    )
@web_bp.route("/delete_post_admin/<int:post_id>", methods=["POST"])
@csrf.exempt
@admin_required
def delete_post_admin(post_id):

    post = Post.query.get_or_404(post_id)

    # delete media file
    if post.media_url:

        try:

            filename = os.path.basename(post.media_url)

            path = os.path.join(
                app.config["POST_UPLOAD_FOLDER"],
                filename
            )

            if os.path.exists(path):
                os.remove(path)

        except Exception as e:
            print("Media delete error:", e)

    # delete likes
    Like.query.filter_by(post_id=post.id).delete()

    # delete comments
    Comment.query.filter_by(post_id=post.id).delete()

    # delete gift transactions
    GiftTransaction.query.filter_by(post_id=post.id).delete()

    # finally delete post
    db.session.delete(post)

    db.session.commit()

    flash("Post deleted successfully")

    return redirect(url_for("web.admin_posts"))
# -------- ADMIN POSTS PAGE --------

@web_bp.route("/admin_posts")
@csrf.exempt
@login_required
@admin_required
def admin_posts():

    posts = Post.query.order_by(Post.created_at.desc()).all()

    result = []

    for p in posts:

        user = User.query.get(p.user_id)

        likes = Like.query.filter_by(
            post_id=p.id,
            is_active=True
        ).count()

        comments = Comment.query.filter_by(
            post_id=p.id
        ).count()

        gifts = db.session.query(
            db.func.sum(GiftTransaction.quantity)
        ).filter_by(post_id=p.id).scalar() or 0

        result.append({
            "id": p.id,
            "user_name": user.full_name if user else "Unknown",
            "content": p.content,
            "media": p.media_url,
            "type": p.media_type,
            "created_at": p.created_at,
            "likes": likes,
            "comments": comments,
            "gifts": gifts
        })

    return render_template(
        "admin_posts.html",
        posts=result
    )


# -------- DELETE SELECTED POSTS --------

@web_bp.route("/delete_selected_posts", methods=["POST"])
@csrf.exempt
@login_required
@admin_required
def delete_selected_posts():

    post_ids = request.form.getlist("post_ids")

    if not post_ids:
        flash("No posts selected")
        return redirect(url_for("web.admin_posts"))

    for pid in post_ids:

        post = Post.query.get(pid)

        if not post:
            continue

        # delete media
        if post.media_url:

            try:

                filename = os.path.basename(post.media_url)

                path = os.path.join(
                    app.config["POST_UPLOAD_FOLDER"],
                    filename
                )

                if os.path.exists(path):
                    os.remove(path)

            except Exception as e:
                print("Delete error:", e)

        Like.query.filter_by(post_id=post.id).delete()
        Comment.query.filter_by(post_id=post.id).delete()
        GiftTransaction.query.filter_by(post_id=post.id).delete()

        db.session.delete(post)

    db.session.commit()

    flash("Selected posts deleted successfully")

    return redirect(url_for("web.admin_posts"))


# -------- CLEAR ALL POSTS --------

@web_bp.route("/clear_all_posts", methods=["POST"])
@csrf.exempt
@login_required
@admin_required
def clear_all_posts():

    posts = Post.query.all()

    for post in posts:

        # delete media
        if post.media_url:

            try:

                filename = os.path.basename(post.media_url)

                path = os.path.join(
                    app.config["POST_UPLOAD_FOLDER"],
                    filename
                )

                if os.path.exists(path):
                    os.remove(path)

            except Exception as e:
                print("Delete error:", e)

        Like.query.filter_by(post_id=post.id).delete()
        Comment.query.filter_by(post_id=post.id).delete()
        GiftTransaction.query.filter_by(post_id=post.id).delete()

        db.session.delete(post)

    db.session.commit()

    flash("All posts cleared successfully")

    return redirect(url_for("web.admin_posts"))

@web_bp.route("/admin_withdrawals")
@admin_required
def admin_withdrawals():

    requests = WithdrawalRequest.query.order_by(
        WithdrawalRequest.created_at.desc()
    ).all()

    return render_template(
        "admin_withdrawals.html",
        requests=requests
    )
@web_bp.route("/approve_withdrawal/<int:id>", methods=["POST"])
@admin_required
def approve_withdrawal(id):

    req = WithdrawalRequest.query.get_or_404(id)

    if req.status != "pending":
        return redirect(url_for("web.admin_withdrawals"))

    wallet = Wallet.query.filter_by(
        user_id=req.user_id
    ).first()

    if wallet.balance < req.amount:
        req.status = "rejected"
        db.session.commit()
        return redirect(url_for("web.admin_withdrawals"))

    wallet.balance -= req.amount

    req.status = "approved"
    req.processed_at = datetime.utcnow()

    db.session.commit()

    return redirect(url_for("web.admin_withdrawals"))

@web_bp.route("/reject_withdrawal/<int:id>", methods=["POST"])
@admin_required
def reject_withdrawal(id):

    req = WithdrawalRequest.query.get_or_404(id)

    req.status = "rejected"
    req.processed_at = datetime.utcnow()

    db.session.commit()

    return redirect(url_for("web.admin_withdrawals"))
# ----------- Logout -----------

@web_bp.route("/logout")
@login_required

def logout():

    session.pop("user_id", None)

    session.pop("is_admin", None)

    flash("Logged out successfully.")

    return redirect(url_for("web.login"))


@web_bp.route("/terms")

def terms():

    return render_template("terms.html")


@web_bp.route("/about")

def about():

    return render_template("about.html")

# -------- TRANSACTIONS --------
@web_bp.route("/wallet/<int:user_id>")
@csrf.exempt
@login_required
def wallet(user_id):

    current_user = session["user_id"]
    is_admin = session.get("is_admin", False)

    # SECURITY CHECK
    if current_user != user_id and not is_admin:
        return jsonify({"error": "Unauthorized"}), 403

    wallet = Wallet.query.filter_by(user_id=user_id).first()

    # create wallet only for valid authenticated owner
    if not wallet:

        wallet = Wallet(
            user_id=user_id,
            balance=0
        )

        db.session.add(wallet)
        db.session.commit()

    return jsonify({
        "balance": wallet.balance
    })
@web_bp.route("/wallet_page")
@csrf.exempt
@login_required
def wallet_page():

    Earning.query.filter_by(
        user_id=session["user_id"],
        seen=False
    ).update({
        "seen": True
    })

    db.session.commit()

    return render_template("wallet.html")
@web_bp.route("/wallet_count")
@csrf.exempt
@login_required
def wallet_count():

    user_id = session["user_id"]

    count = Earning.query.filter_by(
        user_id=user_id,
        seen=False
    ).count()

    return jsonify({
        "count": count
    })

@web_bp.route("/earnings")
@csrf.exempt
@login_required
def earnings():

    user_id = session["user_id"]

    rows = Earning.query.filter_by(user_id=user_id)\
        .order_by(Earning.created_at.desc())\
        .limit(20).all()

    return jsonify([
        {
            "amount": e.amount,
            "date": e.created_at.strftime("%Y-%m-%d %H:%M")
        }
        for e in rows
    ])


# ==========================================================
# PAYPAL HELPERS
# ==========================================================

import base64
import requests

def paypal_base_url():
    if current_app.config["PAYPAL_MODE"] == "sandbox":
        return "https://api-m.sandbox.paypal.com"
    return "https://api-m.paypal.com"

def paypal_access_token():

    credentials = (
        f'{current_app.config["PAYPAL_CLIENT_ID"]}:'
        f'{current_app.config["PAYPAL_CLIENT_SECRET"]}'
    )

    encoded = base64.b64encode(
        credentials.encode()
    ).decode()

    response = requests.post(
        f"{paypal_base_url}/v1/oauth2/token",
        headers={
            "Authorization": f"Basic {encoded}",
            "Accept": "application/json",
            "Accept-Language": "en_US"
        },
        data={
            "grant_type": "client_credentials"
        },
        timeout=30
    )

    response.raise_for_status()

    return response.json()["access_token"]


# ==========================================================
# DEPOSIT
# ==========================================================

@web_bp.route("/deposit", methods=["GET", "POST"])
@csrf.exempt
@login_required
def deposit():

    user_id = int(
        get_jwt_identity()
    )

    data = request.get_json(
        silent=True
    )

    if not data:
        return error_response(
            "Invalid request"
        )

    try:

        amount = float(
            data.get("amount", 0)
        )

    except Exception:

        return error_response(
            "Invalid amount"
        )

    if amount <= 0:
        return error_response(
            "Amount must be greater than zero."
        )

    user = User.query.get(user_id)

    if not user:
        return error_response(
            "User not found",
            404
        )

    token = paypal_access_token()

    payload = {

        "intent": "CAPTURE",

        "purchase_units": [
            {
                "amount": {
                    "currency_code": "USD",
                    "value": f"{amount:.2f}"
                }
            }
        ]

    }

    response = requests.post(

        f"{paypal_base_url}/v2/checkout/orders",

        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        },

        json=payload,

        timeout=30

    )

    if response.status_code not in (
        200,
        201
    ):

        return error_response(
            "Unable to create PayPal order",
            500
        )

    order = response.json()

    approval_url = None

    for link in order.get(
        "links",
        []
    ):

        if link["rel"] == "approve":

            approval_url = link["href"]

            break

    transaction = DepositTransaction(

        user_id=user_id,

        amount=amount,

        paypal_order_id=order["id"],

        status="pending"

    )

    db.session.add(
        transaction
    )

    db.session.commit()

    return render_template(
        "deposit.html",
        wallet=wallet
    )
# ==========================================================
# VERIFY PAYPAL DEPOSIT
# ==========================================================

@web_bp.route("/verify_deposit")
@csrf.exempt
@login_required
def verify_deposit():
    user_id = int(
        get_jwt_identity()
    )

    data = request.get_json(
        silent=True
    )

    if not data:
        return error_response(
            "Invalid request"
        )

    order_id = data.get(
        "order_id"
    )

    if not order_id:
        return error_response(
            "Order ID is required"
        )

    transaction = DepositTransaction.query.filter_by(
        paypal_order_id=order_id
    ).first()

    if not transaction:

        return error_response(
            "Transaction not found",
            404
        )

    if transaction.user_id != user_id:

        return error_response(
            "Unauthorized",
            403
        )

    if transaction.status == "success":

        wallet = Wallet.query.filter_by(
            user_id=user_id
        ).first()

        return success_response(
            "Deposit already processed",
            {
                "balance": (
                    wallet.balance
                    if wallet
                    else 0.0
                )
            }
        )

    token = paypal_access_token()

    response = requests.post(

        f"{PAYPAL_BASE_URL}/v2/checkout/orders/{order_id}/capture",

        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        },

        timeout=30

    )

    if response.status_code not in (
        200,
        201
    ):

        try:
            message = response.json()
        except Exception:
            message = response.text

        return error_response(
            f"PayPal capture failed: {message}",
            400
        )

    capture = response.json()

    if capture.get("status") != "COMPLETED":

        return error_response(
            "Payment not completed."
        )

    wallet = Wallet.query.filter_by(
        user_id=user_id
    ).first()

    if not wallet:

        wallet = Wallet(
            user_id=user_id,
            balance=0.0
        )

        db.session.add(wallet)

    wallet.balance += transaction.amount

    transaction.status = "success"

    db.session.commit()

    return redirect(url_for("web.wallet_page"))
@web_bp.route("/withdraw")
@csrf.exempt
@login_required
def withdraw_page():

    user_id = session["user_id"]

    wallet = Wallet.query.filter_by(
        user_id=user_id
    ).first()

    withdrawals = WithdrawalRequest.query.filter_by(
        user_id=user_id
    ).order_by(
        WithdrawalRequest.created_at.desc()
    ).all()

    return render_template(
        "withdraw.html",
        wallet=wallet,
        withdrawals=withdrawals
    )
@web_bp.route("/request_withdrawal", methods=["POST"])
@login_required
def request_withdrawal():

    user_id = session["user_id"]

    amount = float(request.form["amount"])

    wallet = Wallet.query.filter_by(
        user_id=user_id
    ).first()

    if not wallet:
        flash("Wallet not found")
        return redirect(url_for("withdraw_page"))

    if amount <= 0:
        flash("Invalid amount")
        return redirect(url_for("withdraw_page"))

    if wallet.balance < amount:
        flash("Insufficient balance")
        return redirect(url_for("withdraw_page"))

    request_obj = WithdrawalRequest(
        user_id=user_id,
        amount=amount,
        bank_name=request.form["bank_name"],
        account_name=request.form["account_name"],
        account_number=request.form["account_number"]
    )

    db.session.add(request_obj)
    db.session.commit()

    flash("Withdrawal request submitted")

    return redirect(url_for("web.withdraw_page"))
@web_bp.route("/buy_gift_page")
@login_required
def buy_gift_page():

    return render_template("buy_gift.html")
@web_bp.route("/gifts")
@login_required
def get_gifts():

    gifts = Gift.query.all()

    def clean_name(name):
        # removes leading numbers like "50 Preshas" → "Preshas"
        parts = name.split(" ")
        if parts[0].isdigit():
            return " ".join(parts[1:])
        return name

    return jsonify([
        {
            "id": g.id,
            "name": clean_name(g.name),
            "price": g.price,
            "value": g.value
        } for g in gifts
    ])
@web_bp.route("/buy_gift", methods=["POST"])
@csrf.exempt
@login_required
def buy_gift():
    data = request.json
    user_id = session["user_id"]

    gift_id = int(data["gift_id"])
    quantity = int(data.get("quantity", 1))

    gift = Gift.query.get(gift_id)
    if not gift:
        return jsonify({"success": False, "error": "Gift not found"}), 404

    wallet = Wallet.query.filter_by(user_id=user_id).first()
    if not wallet:
        wallet = Wallet(user_id=user_id, balance=0)
        db.session.add(wallet)
        db.session.commit()

    total_cost = gift.price * quantity

    if wallet.balance < total_cost:
        return jsonify({
            "success": False,
            "redirect": "/deposit",
            "error": "Insufficient balance"
        })

    # 💰 deduct USD (buying cost)
    wallet.balance -= total_cost

    # 🎁 ADD TO GIFT INVENTORY
    gift_balance = UserGiftBalance.query.filter_by(
        user_id=user_id,
        gift_id=gift_id
    ).first()

    if not gift_balance:
        gift_balance = UserGiftBalance(
            user_id=user_id,
            gift_id=gift_id,
            quantity=0
        )
        db.session.add(gift_balance)

    gift_balance.quantity += quantity

    # record transaction (optional history)
    tx = GiftTransaction(
        sender_id=user_id,
        receiver_id=user_id,
        post_id=None,
        gift_id=gift_id,
        quantity=quantity,
        total_amount=total_cost
    )

    db.session.add(tx)
    db.session.commit()

    return jsonify({
        "success": True,
        "message": f"{gift.name} added to inventory",
        "new_balance": wallet.balance
    })
@web_bp.route("/gift_count/<int:post_id>")
def gift_count(post_id):

    total = db.session.query(
        db.func.sum(GiftTransaction.quantity)
    ).filter_by(post_id=post_id).scalar()

    return jsonify({
        "count": total or 0
    })
@web_bp.route("/send_gift", methods=["POST"])
@csrf.exempt
@login_required
def send_gift():

    data = request.json

    sender_id = session["user_id"]
    post_id = int(data["post_id"])
    gift_id = int(data["gift_id"])
    quantity = int(data.get("quantity", 1))

    if quantity <= 0:
        return jsonify({"error": "Invalid quantity"})

    gift = Gift.query.get(gift_id)
    post = Post.query.get(post_id)

    if not gift or not post:
        return jsonify({"error": "Invalid gift or post"})

    # 🔒 LOCK row to avoid race condition
    gift_balance = UserGiftBalance.query.filter_by(
        user_id=sender_id,
        gift_id=gift_id
    ).with_for_update().first()

    if not gift_balance:
        return jsonify({
            "error": "You don't own this gift",
            "redirect": "/buy_gift_page"
        })

    if gift_balance.quantity < quantity:
        return jsonify({
            "error": f"Only {gift_balance.quantity} left",
            "redirect": "/buy_gift_page"
        })

    # ✅ DEDUCT
    gift_balance.quantity -= quantity
    if gift_balance.quantity <= 0:
        db.session.delete(gift_balance)


    # 🚫 Prevent negative values
    if gift_balance.quantity < 0:
        gift_balance.quantity = 0

    # 💰 PAYOUT (use fixed model version if you implemented it)
    creator_earn = gift.payout * quantity if hasattr(gift, "payout") else 0

    earning = Earning(
        user_id=post.user_id,
        amount=creator_earn
    )
    sender = User.query.get(sender_id)

    notification = Notification(
        user_id=post.user_id,
        title="Gift Received",
        message=f"{sender.full_name} sent you {quantity} {gift.name}"
    )

    db.session.add(notification)
    db.session.add(earning)
        # 💳 ADD TO WALLET (NEW)
    add_to_wallet(post.user_id, creator_earn)

    # 📦 RECORD TRANSACTION
    tx = GiftTransaction(
        sender_id=sender_id,
        receiver_id=post.user_id,
        post_id=post_id,
        gift_id=gift_id,
        quantity=quantity,
        total_amount=0
    )
    db.session.add(tx)

    db.session.commit()

    return jsonify({
        "success": True,
        "remaining": gift_balance.quantity,  # ✅ send back updated value
        "message": "Gift sent successfully"
    })
@web_bp.route("/my_gifts")
@login_required
def my_gifts():
    user_id = session["user_id"]

    balances = db.session.query(
        Gift.id,
        Gift.name,
        UserGiftBalance.quantity
    ).join(
        UserGiftBalance, Gift.id == UserGiftBalance.gift_id
    ).filter(
        UserGiftBalance.user_id == user_id,
        UserGiftBalance.quantity > 0
    ).all()

    return jsonify([
        {
            "id": g[0],
            "name": g[1],
            "quantity": g[2]
        }
        for g in balances
    ])
@web_bp.route("/check_gift_access", methods=["POST"])
@csrf.exempt
@login_required
def check_gift_access():

    user_id = session["user_id"]
    gift_id = request.json.get("gift_id")

    gift = Gift.query.get(gift_id)
    if not gift:
        return jsonify({"allowed": False})

    wallet = Wallet.query.filter_by(user_id=user_id).first()
    if not wallet:
        return jsonify({"allowed": False})

    # check if user has ever bought this gift
    owned = GiftTransaction.query.filter_by(
        sender_id=user_id,
        gift_id=gift_id
    ).first()

    # RULE:
    # must either OWN gift OR HAVE MONEY
    if not owned and wallet.balance < gift.price:
        return jsonify({"allowed": False})

    return jsonify({"allowed": True})

# -------- CONTENT --------
@web_bp.route("/my_posts")
@csrf.exempt
@login_required
def my_posts():
    user_id = session["user_id"]

    posts = Post.query.filter_by(user_id=user_id)\
        .order_by(Post.created_at.desc()).all()

    result = []
    for p in posts:
        result.append({
            "id": p.id,
            "content": p.content,
            "media": p.media_url,
            "type": p.media_type,
            "created_at": p.created_at.strftime("%Y-%m-%d %H:%M")
        })

    return jsonify(result)
# -------- PROFILE --------
@web_bp.route("/dp", methods=["GET", "POST"])
@csrf.exempt
@login_required
def dp():

    user = User.query.get(session["user_id"])

    if request.method == "POST":

        full_name = request.form.get("full_name", "").strip()
        bio = request.form.get("bio", "")
        file = request.files.get("user_dp_pic")

        # Update name
        if full_name:
            user.full_name = full_name

        # Update bio
        user.bio = bio

        # Upload profile picture to Cloudinary
        if file:

            if not allowed_file(file.filename):

                flash(
                    "Only PNG, JPG, JPEG and WEBP files are allowed.",
                    "error"
                )
                return redirect(url_for("dp"))

            try:

                upload_result = cloudinary.uploader.upload(
                    file,
                    folder="user_dp_pics",
                    public_id=f"user_{user.id}",
                    overwrite=True,
                    resource_type="image"
                )

                user.user_dp_pic = upload_result["secure_url"]

            except Exception as e:

                print("DP Upload Error:", e)

                flash(
                    "Failed to upload profile picture.",
                    "error"
                )
                return redirect(url_for("dp"))

        db.session.commit()

        flash(
            "Profile updated successfully!",
            "success"
        )

        return redirect(url_for("dp"))

    return render_template(
        "my_dp.html",
        user=user
    )

# -------- BUDDIES PAGE --------
@web_bp.route("/buddies_page")
@csrf.exempt
@login_required
def buddies_page():

    Buddy.query.filter_by(
        buddy_id=session["user_id"],
        seen=False
    ).update({
        "seen": True
    })

    db.session.commit()

    return render_template("buddies.html")
@web_bp.route("/followers")
@login_required
def followers():

    user_id = session["user_id"]


    followers = Buddy.query.filter_by(buddy_id=user_id).all()

    ids = [b.user_id for b in followers]


    users = User.query.filter(User.id.in_(ids)).all() if ids else []


    return jsonify({

        "count": len(users),

        "users": [{"id": u.id, "name": u.full_name, "dp": u.user_dp_pic, "bio": u.bio} for u in users]

    })
@web_bp.route("/followers/<int:user_id>")
@csrf.exempt
@login_required
def user_followers(user_id):

    followers = Buddy.query.filter_by(buddy_id=user_id).all()
    ids = [b.user_id for b in followers]

    users = User.query.filter(User.id.in_(ids)).all() if ids else []

    return render_template("followers.html", users=users)
@web_bp.route("/following/<int:user_id>")
@login_required
def user_following(user_id):

    buddies = Buddy.query.filter_by(user_id=user_id).all()
    ids = [b.buddy_id for b in buddies]

    users = User.query.filter(User.id.in_(ids)).all() if ids else []

    return render_template("following.html", users=users)
@web_bp.route("/add_buddy", methods=["POST"])
@csrf.exempt
@login_required

def add_buddy():

    data = request.json

    user_id = session["user_id"]

    buddy_id = int(data["buddy_id"])


    # prevent adding self

    if user_id == buddy_id:

        return jsonify({"error": "Cannot add yourself"})


    # prevent duplicates

    existing = Buddy.query.filter_by(user_id=user_id, buddy_id=buddy_id).first()

    if existing:

        return jsonify({"error": "Already buddies"})


    buddy = Buddy(user_id=user_id, buddy_id=buddy_id, seen=False)

    db.session.add(buddy)
    create_buddy_milestone(user_id)

    db.session.commit()
    return jsonify({"success": True})
@web_bp.route("/users_to_add")
@csrf.exempt
@login_required
def users_to_add():

    user_id = session["user_id"]
    # people I already added
    my_buddies = Buddy.query.filter_by(user_id=user_id).all()
    my_ids = [b.buddy_id for b in my_buddies]
    users = User.query.filter(

        User.id != user_id,
        ~User.id.in_(my_ids),
    ).all()


    return jsonify({

        "count": len(users),

        "users": [{"id": u.id, "name": u.full_name, "dp": u.user_dp_pic or "default_avatar.png", "is_online": u.is_online, "last_seen": u.last_seen} for u in users]

    })
@web_bp.route("/following")
@login_required
def following():

    user_id = session["user_id"]
    buddies = Buddy.query.filter_by(user_id=user_id).all()
    ids = [b.buddy_id for b in buddies]
    users = User.query.filter(User.id.in_(ids)).all() if ids else []


    return jsonify({

        "count": len(users),

        "users": [{"id": u.id, "bio": u.bio, "name": u.full_name, "dp": u.user_dp_pic or "default_avatar.png", "is_online": u.is_online, "last_seen": u.last_seen} for u in users]

    })
@web_bp.route("/user_stats/<int:user_id>")
@login_required
def user_stats(user_id):

    followers = Buddy.query.filter_by(buddy_id=user_id).count()
    following = Buddy.query.filter_by(user_id=user_id).count()

    posts = Post.query.filter_by(user_id=user_id).count()

    return jsonify({
        "followers": followers,
        "following": following,
        "posts": posts
    })
@web_bp.route("/user_info/<int:user_id>")
@login_required
def user_info(user_id):
    user = User.query.get_or_404(user_id)

    return jsonify({
        "id": user.id,
        "name": user.full_name,
        "dp": user.user_dp_pic or "default_avatar.png",
        "is_online": user.is_online,
        "last_seen": user.last_seen
    })
@web_bp.route("/mutual_buddies")
@login_required
def mutual_buddies():
    user_id = session["user_id"]

    my = Buddy.query.filter_by(user_id=user_id).all()
    my_ids = {b.buddy_id for b in my}

    added_me = Buddy.query.filter_by(buddy_id=user_id).all()
    added_me_ids = {b.user_id for b in added_me}

    mutual_ids = my_ids.intersection(added_me_ids)

    users = User.query.filter(User.id.in_(mutual_ids)).all() if mutual_ids else []

    return jsonify({
        "users":[
            {"id":u.id, "name":u.full_name, "dp":u.user_dp_pic}
            for u in users
        ]
    })
@web_bp.route("/buddy_count")
@csrf.exempt
@login_required
def buddy_count():

    user_id = session["user_id"]

    count = Buddy.query.filter_by(
        buddy_id=user_id,
        seen=False
    ).count()

    return jsonify({
        "count": count
    })
@web_bp.route("/search_buddies", methods=["POST"])
@login_required
def search_buddies():
    data = request.get_json()
    buddy_id = data.get("buddy_id")
    buddy_name = data.get("buddy_name", "").strip()

    if not buddy_id and not buddy_name:
        return jsonify({"error": "Buddy ID or name is required"}), 400

    if buddy_id:
        user = User.query.get(buddy_id)
    else:
        user = User.query.filter(User.full_name.contains(buddy_name)).first()
    if not user:
        return jsonify({"error": "User not found"}), 404

    return jsonify({
        "users": [{
            "id": user.id,
            "name": user.full_name,
            "dp": user.user_dp_pic or "default_avatar.png"
        }]
    })

@web_bp.route("/my_buddies")
@login_required
def my_buddies():

    user_id = session["user_id"]
    # I added
    my_buddies = Buddy.query.filter_by(user_id=user_id).all()
    my_ids = {b.buddy_id for b in my_buddies}
    # Added me
    added_me = Buddy.query.filter_by(buddy_id=user_id).all()
    added_me_ids = {b.user_id for b in added_me}
    # Combine both sides
    all_ids = my_ids.union(added_me_ids)
    users = User.query.filter(User.id.in_(all_ids)).all() if all_ids else []
    result = []
    for u in users:
        result.append({
            "dp": u.user_dp_pic if u.user_dp_pic else 'default_avatar.png',
            "name": u.full_name,
            "is_mutual": u.id in my_ids and u.id in added_me_ids
        })
    return render_template("my_buddies.html", buddies=result)
@web_bp.route("/create_post", methods=["POST"])
@csrf.exempt
@login_required
def create_post():
    try:
        content = request.form.get("content", "").strip()
        user_id = session.get("user_id")
        file = request.files.get("file")
        media_url = None
        media_type = None
        # ---------------- FILE UPLOAD ----------------
        if file and file.filename != "":
            # ensure extension exists
            if "." not in file.filename:
                return jsonify({
                    "error": "Invalid file"
                }), 400
            filename = secure_filename(f"{uuid.uuid4().hex}{os.path.splitext(file.filename)[1].lower()}")
            ext = filename.rsplit(".", 1)[-1].lower()
            IMAGE_EXTENSIONS = {"png", "jpg", "jpeg", "webp", "gif"}
            VIDEO_EXTENSIONS = {"mp4", "webm", "mov"}
            FILE_EXTENSIONS = {"pdf", "docx"}
            if ext in IMAGE_EXTENSIONS:
                media_type = "image"
            elif ext in VIDEO_EXTENSIONS:
                media_type = "video"
            elif ext in FILE_EXTENSIONS:
                media_type = "file"
            else:
                return jsonify({"error": "Unsupported file type"}), 400
            mime = file.mimetype or ""
            if not mime.startswith(("image/", "video/", "application/", "text/", "audio/")):
                return jsonify({
                    "error": "Invalid media file"
                }), 400
            # allowed file types
            ALLOWED_EXTENSIONS = {
                "png",
                "jpg",
                "jpeg",
                "webp",
                "gif",
                "mp4",
                "webm",
                "mov",
                "pdf",
                "docx"
            }
            # reject unsupported files
            if ext not in ALLOWED_EXTENSIONS:
                return jsonify({
                    "error": "Unsupported file type"
                }), 400

            # unique safe filename
            filename = secure_filename(
                f"{uuid.uuid4().hex}.{ext}"
            )

            # full save path
            upload_result = cloudinary.uploader.upload(
                file,
                resource_type="auto"
            )
            media_url = upload_result.get("secure_url")
            # detect media type
            IMAGE_EXTENSIONS = {
                "png",
                "jpg",
                "jpeg",
                "webp",
                "gif"
            }

            VIDEO_EXTENSIONS = {
                "mp4",
                "webm",
                "mov"
            }

            if ext in IMAGE_EXTENSIONS:

                media_type = "image"

            elif ext in VIDEO_EXTENSIONS:

                media_type = "video"

            else:

                return jsonify({"error": "Unsupported file type"}), 400

        # ---------------- CREATE POST ----------------

        post = Post(
            user_id=user_id,
            content=content,
            media_url=media_url,
            media_type=media_type,
            anon_name="Anonymous"
        )

        db.session.add(post)

        db.session.commit()

        return jsonify({
            "success": True
        })

    except Exception as e:

        db.session.rollback()

        print("CREATE POST ERROR:", e)

        return jsonify({
            "error": str(e)
        }), 500

@web_bp.route("/posts")
@login_required
def get_posts():

    posts = Post.query.order_by(Post.created_at.desc()).all()
    post_ids = [p.id for p in posts]

    # batch likes
    likes_data = db.session.query(
        Like.post_id,
        db.func.count(Like.id)
    ).filter(
        Like.post_id.in_(post_ids),
        Like.is_active == True
    ).group_by(Like.post_id).all()

    likes_map = {p_id: count for p_id, count in likes_data}

    # batch comments
    comments_data = db.session.query(
        Comment.post_id,
        db.func.count(Comment.id)
    ).filter(
        Comment.post_id.in_(post_ids)
    ).group_by(Comment.post_id).all()

    comments_map = {p_id: count for p_id, count in comments_data}

    # user likes (for current user only)
    user_likes = Like.query.filter(
        Like.user_id == session["user_id"],
        Like.post_id.in_(post_ids),
        Like.is_active == True
    ).all()

    liked_set = {l.post_id for l in user_likes}

    result = []

    for p in posts:

        result.append({
            "id": p.id,
            "content": p.content,
            "media": p.media_url,
            "type": p.media_type,
            "user": p.user_id,
            "likes": likes_map.get(p.id, 0),
            "comments": comments_map.get(p.id, 0),
            "liked": p.id in liked_set
        })

    return jsonify(result)

@web_bp.route("/videos_page")
def videos_page():
    return render_template("videos.html")

# -------- CHAT --------
@web_bp.route("/chat/<int:user_id>")
@login_required
def conversation_page(user_id):

    user = User.query.get_or_404(user_id)

    return render_template(
        "conversation.html",
        other_user=user
    )
@web_bp.route("/send_message", methods=["POST"])
@csrf.exempt
@login_required
def send_message():

    try:

        sender_id = session["user_id"]

        receiver_id = int(
            request.form.get("receiver_id")
        )

        text = request.form.get(
            "message",
            ""
        ).strip()

        file = request.files.get("file")

        media_url = None
        media_type = None

        if file and file.filename:

            upload = cloudinary.uploader.upload(
                file,
                resource_type="auto"
            )

            media_url = upload["secure_url"]

            mime = file.mimetype or ""

            if mime.startswith("image/"):
                media_type = "image"

            elif mime.startswith("video/"):
                media_type = "video"

            elif mime == "application/pdf":
                media_type = "pdf"

            else:
                media_type = "doc"

        if not text and not media_url:
            return jsonify({
                "success": False,
                "error": "Empty message"
            })

        msg = ChatMessage(
            sender_id=sender_id,
            receiver_id=receiver_id,
            message=text,
            media_url=media_url,
            media_type=media_type
        )

        db.session.add(msg)
        db.session.commit()

        socketio.emit(
            "new_message",
            {
                "sender": sender_id,
                "receiver": receiver_id
            },
            room=str(receiver_id)
        )

        return jsonify({
            "success": True
        })

    except Exception as e:

        print("SEND MESSAGE ERROR:", e)

        return jsonify({
            "success": False,
            "error": str(e)
        }), 500
@web_bp.route("/user_status/<int:user_id>")
@login_required
def user_status(user_id):

    user = User.query.get_or_404(user_id)

    return jsonify({
        "online": user.is_online,
        "last_seen": user.last_seen.strftime("%H:%M")
        if user.last_seen else "recently"
    })
@web_bp.route("/delete_message", methods=["POST"])
@csrf.exempt
@login_required
def delete_message():
    data = request.get_json()

    msg = ChatMessage.query.get(
        data.get("message_id")
    )

    if not msg:
        return jsonify({
            "error":"Message not found"
        }),404

    if msg.sender_id != session["user_id"]:
        return jsonify({
            "error":"Unauthorized"
        }),403

    db.session.delete(msg)
    db.session.commit()

    return jsonify({
        "success":True
    })
@web_bp.route("/get_messages/<int:other_user>")
@csrf.exempt
@login_required
def get_messages(other_user):
    current_user = session["user_id"]
    # SECURITY CHECK
    messages = ChatMessage.query.filter(
        (
            (ChatMessage.sender_id == current_user) &
            (ChatMessage.receiver_id == other_user)
        ) |
        (
            (ChatMessage.sender_id == other_user) &
            (ChatMessage.receiver_id == current_user)
        )
    ).order_by(ChatMessage.created_at.asc()).all()

    # mark messages as read ONLY for current user
    unread_messages = []
    for m in messages:
        if (
            m.receiver_id == current_user and
            not m.is_read
        ):
            m.is_read = True
            unread_messages.append(m.id)
    db.session.commit()
    if unread_messages:
        socketio.emit(
            "messages_read",
            {
                "message_ids": unread_messages,
                "reader": current_user
            },
            room=str(current_user)
        )

    return jsonify([
        {
            "sender": m.sender_id,
            "media_url": m.media_url,
            "media_type": m.media_type,
            "message": m.message,
            "created_at": m.created_at.strftime("%Y-%m-%d %H:%M"),
            "is_read": m.is_read,
            "id": m.id,
        }
        for m in messages
    ])
@web_bp.route("/user/<int:user_id>")
@login_required
def user_profile(user_id):
    current_id = session["user_id"]
    user = User.query.get_or_404(user_id)
    # relationship
    i_added = Buddy.query.filter_by(user_id=current_id, buddy_id=user_id).first()
    added_me = Buddy.query.filter_by(user_id=user_id, buddy_id=current_id).first()
    # ✅ COUNTS
    followers_count = Buddy.query.filter_by(buddy_id=user_id).count()
    following_count = Buddy.query.filter_by(user_id=user_id).count()
    return render_template(
        "user_profile.html",
        user=user,
        is_mutual=bool(i_added and added_me),
        added_me=bool(added_me),
        i_added=bool(i_added),
        followers_count=followers_count,
        following_count=following_count
    )
@web_bp.route("/user_posts/<int:user_id>")
@login_required
def user_posts(user_id):

    posts = Post.query.filter_by(
        user_id=user_id
    ).order_by(
        Post.created_at.desc()
    ).all()

    return jsonify([
        {
            "id": p.id,
            "content": p.content,
            "media": p.media_url,
            "type": p.media_type,
            "created_at": p.created_at.strftime("%Y-%m-%d %H:%M")
        }
        for p in posts
    ])
# -------- CLEAR CHAT --------
@web_bp.route("/clear_chat_both", methods=["POST"])
@csrf.exempt
@login_required
def clear_chat_both():
    current_user = session["user_id"]
    other_user = int(request.json["other_user"])
    ChatMessage.query.filter(
        (
            (ChatMessage.sender_id == current_user) &
            (ChatMessage.receiver_id == other_user)
        )
        |
        (
            (ChatMessage.sender_id == other_user) &
            (ChatMessage.receiver_id == current_user)
        )
    ).delete(synchronize_session=False)
    db.session.commit()
    socketio.emit(
        "chat_cleared",
        {
            "user1": current_user,
            "user2": other_user
        },
        room=str(other_user)
    )
    return jsonify({"success": True})
@web_bp.route("/unread_counts")
@csrf.exempt
@login_required
def unread_counts():

    user_id = session["user_id"]

    unread = db.session.query(
        ChatMessage.sender_id,
        db.func.count(ChatMessage.id)
    ).filter_by(
        receiver_id=user_id,
        is_read=False
    ).group_by(
        ChatMessage.sender_id
    ).all()

    counts = {}

    total = 0

    for sender_id, count in unread:

        counts[str(sender_id)] = count

        total += count

    return jsonify({
        "total": total,
        "users": counts
    })

from flask_socketio import join_room

@socketio.on("join")
def handle_join():

    user_id = session.get("user_id")

    if user_id:
        join_room(str(user_id))
@socketio.on("connect")
def handle_connect():

    user_id = session.get("user_id")

    if user_id:
        user = User.query.get(user_id)

        if user:
            user.is_online = True
            user.last_seen = datetime.utcnow()
            db.session.commit()

        join_room(str(user_id))
@socketio.on("disconnect")
def handle_disconnect():

    user_id = session.get("user_id")

    if user_id:

        user = User.query.get(user_id)

        if user:
            user.is_online = False
            user.last_seen = datetime.utcnow()
            db.session.commit()
@socketio.on("typing")
def typing(data):

    receiver = data["receiver"]

    socketio.emit(
        "typing",
        {
            "user": session["user_id"]
        },
        room=str(receiver)
    )
@socketio.on("stop_typing")
def stop_typing(data):

    receiver = data["receiver"]

    socketio.emit(
        "stop_typing",
        {
            "user": session["user_id"]
        },
        room=str(receiver)
    )
# ---------------- RUN ----------------


if __name__ == "__main__":

    with app.app_context():
        seed_gifts()

    port = int(os.environ.get("PORT", 10000))

    socketio.run(
        app,
        host="0.0.0.0",
        port=port,
        debug=False,
        allow_unsafe_werkzeug=True
    )