from flask import (

    Flask, render_template, request, redirect,

    url_for, flash, jsonify, session, send_from_directory 
)

from flask_migrate import Migrate

from werkzeug.security import generate_password_hash, check_password_hash

from werkzeug.utils import secure_filename

from functools import wraps

from datetime import datetime, timedelta

from dotenv import load_dotenv

load_dotenv()
import os

from sqlalchemy import text

from flask_sqlalchemy import SQLAlchemy

import mimetypes
import random
import string
import uuid
import smtplib

from email.mime.text import MIMEText

# ----------------- App Setup --------------
from flask import Flask

app = Flask(__name__)

# THEN initialize socketio AFTER app exists
from flask_socketio import SocketIO

socketio = SocketIO(
    app,
    cors_allowed_origins="*",
    async_mode="threading"  # SAFE for local + Render
)
from flask_socketio import SocketIO, join_room, leave_room, emit

app.secret_key = os.environ.get("SECRET_KEY", "dev-secret")

app.config["APP_NAME"] = "SPACE LIO AI"


# ----------------- Database -----------------

DATABASE_URL = os.environ.get("DATABASE_URL")


if DATABASE_URL:

    # Fix old postgres:// bug

    if DATABASE_URL.startswith("postgres://"):

        DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)


    app.config["SQLALCHEMY_DATABASE_URI"] = DATABASE_URL

else:

    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///local.db"

# Recommended for remote Postgres (Render)

app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {

    "pool_pre_ping": True,       # Checks if connection is alive before using

    "pool_recycle": 280,         # Recycle connections older than 280s

    "pool_size": 5,              # Number of connections in the pool

    "max_overflow": 10            # Extra connections allowed

}


app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False


db = SQLAlchemy(app)

migrate = Migrate(app, db)
LIKE_EARN = 0.001
COMMENT_EARN = 0.0025


#-------------------- File Upload Setup ----------------

ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "mp4", "mov", "pdf", "docx"}

def allowed_file(filename):

    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


UPLOAD_FOLDER = "uploads"

app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

app.config["user_dp_folder"] = os.path.join(UPLOAD_FOLDER, "user_dp_pics")


os.makedirs(UPLOAD_FOLDER, exist_ok=True)

os.makedirs(app.config["user_dp_folder"], exist_ok=True)


#------------------- Routes for Uploaded Files -----------------

@app.route("/uploads/<path:filename>")

def uploaded_file(filename):

    return send_from_directory(app.config["UPLOAD_FOLDER"], filename)


@app.route("/uploads/user_dp/<path:filename>")

def user_dp(filename):

    return send_from_directory(app.config["user_dp_folder"], filename)



# ---------------- MODELS ----------------

class User(db.Model):

    id = db.Column(db.Integer, primary_key=True)

    full_name = db.Column(db.String(150), nullable=False)

    phone = db.Column(db.String(20), unique=True, nullable=False)

    password = db.Column(db.String(255), nullable=False)

    id_number = db.Column(db.String(50), nullable=True)
    

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

    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    user_dp_pic = db.Column(db.String(255), default='default_avatar.png')

    bio = db.Column(db.String(255), default="")


class Wallet(db.Model):

    id = db.Column(db.Integer, primary_key=True)

    user_id = db.Column(db.Integer, unique=True)

    balance = db.Column(db.Float, default=0.0)



class Earning(db.Model):

    id = db.Column(db.Integer, primary_key=True)

    user_id = db.Column(db.Integer)

    amount = db.Column(db.Float)

    status = db.Column(db.String(20), default="pending")

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

    sender_id = db.Column(db.Integer)

    receiver_id = db.Column(db.Integer)

    message = db.Column(db.Text)
    is_read = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
class Comment(db.Model):
    id = db.Column(db.Integer, primary_key=True)

    user_id = db.Column(db.Integer, nullable=False)
    post_id = db.Column(db.Integer, nullable=False)

    comment = db.Column(db.Text, nullable=False)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)

#----------------- HELPERS ----------------

from werkzeug.security import generate_password_hash, check_password_hash

def login_required(f):

    @wraps(f)

    def wrapper(*args, **kwargs):

        if "user_id" not in session:

            flash("Please log in first.", "error")

            return redirect(url_for("login"))

        return f(*args, **kwargs)

    return wrapper


def admin_required(f):

    @wraps(f)

    def wrapper(*args, **kwargs):

        if not session.get("user_id"):

            flash("Please log in first")

            return redirect(url_for("login"))

        if not session.get("is_admin"):

            flash("Admin access only")

            return redirect(url_for("nonimas"))

        return f(*args, **kwargs)

    return wrapper
def add_to_wallet(user_id, amount):
    wallet = Wallet.query.filter_by(user_id=user_id).first()

    if not wallet:
        wallet = Wallet(user_id=user_id, balance=0.0)
        db.session.add(wallet)

    wallet.balance += amount

def generate_otp():

    return ''.join(random.choices(string.digits, k=6))


def send_otp_email(to_email, otp):

    sender_email = os.environ.get("EMAIL_USER")

    sender_password = os.environ.get("EMAIL_PASS")


    subject = "Your OTP Code"

    body = f"Your OTP code is: {otp}. It expires in 5 minutes."


    msg = MIMEText(body)

    msg['Subject'] = subject

    msg['From'] = sender_email

    msg['To'] = to_email


    with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:

        server.login(sender_email, sender_password)

        server.send_message(msg)
def seed_gifts():
    gifts = [
        {"name": "Caros", "value": 0.1, "price": 0.1, "payout": 0.07},
        {"name": "Cons", "value": 1.0, "price": 1.0, "payout": 0.8},
        {"name": "Preshas", "value": 5.0, "price": 5.0, "payout": 4.6},
        {"name": "Stacs", "value": 10.0, "price": 10.0, "payout": 9.5},
        {"name": "Poulets", "value": 25.0, "price": 25.0, "payout": 24},
    ]

    for g in gifts:
        if not Gift.query.filter_by(name=g["name"]).first():
            db.session.add(Gift(**g))

    db.session.commit()

# ---------------- ROUTES ----------------

@app.route("/")

@login_required

def nonimas():

    if not session.get("is_admin") and not session.get("user_id"):

        flash("Please log in first.", "error")

        return redirect(url_for("login"))

    return render_template("nonimas.html")


# -------- PAGES --------
@app.route("/like_post", methods=["POST"])
@login_required
def like_post():

    data = request.json
    user_id = session["user_id"]
    post_id = int(data["post_id"])

    post = Post.query.get(post_id)
    if not post:
        return jsonify({"error": "Post not found"})

    existing = Like.query.filter_by(
        user_id=user_id,
        post_id=post_id
    ).first()

    # ❌ UNLIKE (remove earning logic)
    if existing:
        db.session.delete(existing)
        db.session.commit()

        count = Like.query.filter_by(post_id=post_id).count()

        return jsonify({
            "liked": False,
            "count": count
        })

    # ✅ LIKE (ADD EARNING)
    like = Like(user_id=user_id, post_id=post_id)
    db.session.add(like)

    # 💰 creator earns
    earning = Earning(
        user_id=post.user_id,
        amount=LIKE_EARN
    )
    db.session.add(earning)
     # 💳 ADD TO WALLET (NEW)
    add_to_wallet(post.user_id, LIKE_EARN)
    db.session.commit()

    count = Like.query.filter_by(post_id=post_id).count()

    return jsonify({
        "liked": True,
        "count": count
    })

@app.route("/add_comment", methods=["POST"])
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

@app.route("/comments/<int:post_id>")
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
@app.route("/chat_page")

@login_required

def chat_page():

    return render_template("chat.html")


@app.route('/register', methods=['GET', 'POST'])
def register():

    # ---------- STEP 1: SHOW FORM FIRST ----------
    if request.method == "GET":
        session.pop("pending_user_id", None)  # 🔥 reset old sessions
        return render_template("register.html", otp_stage=False)

    # ---------- STEP 2: OTP VERIFICATION ----------
    if request.form.get("otp"):
        user_id = session.get("pending_user_id")

        if not user_id:
            flash("Session expired. Please register again.")
            return redirect(url_for("register"))

        user = User.query.get(user_id)

        entered_otp = request.form.get("otp")

        if entered_otp != user.otp_code:
            flash("Invalid OTP")
            return render_template("register.html", otp_stage=True)

        if datetime.utcnow() > user.otp_expiry:
            flash("OTP expired")
            return render_template("register.html", otp_stage=True)

        user.is_verified = True
        user.otp_code = None
        user.otp_expiry = None
        db.session.commit()

        session.pop("pending_user_id", None)

        flash("Account verified successfully! You can now login.")
        return redirect(url_for("login"))

    # ---------- STEP 3: REGISTRATION ----------
    full_name = request.form['full_name']
    phone = request.form['phone']
    password = request.form['password']
    confirm_password = request.form['confirm_password']
    email = request.form.get("email")

    if password != confirm_password:
        flash("Passwords do not match")
        return redirect(url_for('register'))

    if User.query.filter_by(phone=phone).first():
        flash("Phone already exists")
        return redirect(url_for('register'))

    if email and User.query.filter_by(email=email).first():
        flash("Email already exists")
        return redirect(url_for('register'))

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

    if email:
        send_otp_email(email, otp)

    flash("OTP sent to your email")

    return render_template("register.html", otp_stage=True)


# ----------- Login -----------

@app.route("/login", methods=["GET", "POST"])

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

            return redirect(url_for("login"))



        session["user_id"] = user.id

        session["is_admin"] = user.is_admin


        if user.is_admin:

            return redirect(url_for("admin_dashboard"))


        return redirect(url_for("nonimas"))


    return render_template("login.html")

@app.route("/admin_dashboard")
@login_required
def admin_dashboard():

    if not session.get("is_admin"):
        return redirect(url_for("nonimas"))

    # 💰 TOTAL REVENUE (money spent buying gifts)
    revenue = db.session.query(
        db.func.sum(GiftTransaction.total_amount)
    ).scalar() or 0

    # 💸 TOTAL PAYOUTS (creator earnings)
    payouts = db.session.query(
        db.func.sum(Earning.amount)
    ).scalar() or 0

    # 📈 PLATFORM PROFIT
    profit = revenue - payouts

    # 🎁 MOST POPULAR GIFTS (by quantity)
    popular_gifts = db.session.query(
        Gift.name,
        db.func.sum(GiftTransaction.quantity)
    ).join(GiftTransaction, Gift.id == GiftTransaction.gift_id)\
     .group_by(Gift.name)\
     .order_by(db.func.sum(GiftTransaction.quantity).desc())\
     .all()

    return render_template(
        "admin_dashboard.html",
        revenue=revenue,
        payouts=payouts,
        profit=profit,
        popular_gifts=popular_gifts
    )
# ----------- Logout -----------

@app.route("/logout")

@login_required

def logout():

    session.pop("user_id", None)

    session.pop("is_admin", None)

    flash("Logged out successfully.")

    return redirect(url_for("login"))


@app.route("/terms")

def terms():

    return render_template("terms.html")


@app.route("/about")

def about():

    return render_template("about.html")


@app.route("/buddies_page")

def buddies_page():

    return render_template("buddies.html")


@app.route("/my_buddies")

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

@app.route("/deposit", methods=["GET", "POST"])
@login_required
def deposit():

    user_id = session["user_id"]

    wallet = Wallet.query.filter_by(user_id=user_id).first()

    # create wallet if missing
    if not wallet:

        wallet = Wallet(
            user_id=user_id,
            balance=0
        )

        db.session.add(wallet)
        db.session.commit()

    # disable deposits for now
    if request.method == "POST":

        flash("Deposits are currently unavailable.")

        return redirect(url_for("deposit"))

    return render_template(
        "deposit.html",
        wallet=wallet
    )
@app.route("/buy_gift_page")
@login_required
def buy_gift_page():

    return render_template("buy_gift.html")

@app.route("/gifts")
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
# -------- BUY GIFT PAGE --------
@app.route("/buy_gift", methods=["POST"])
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

@app.route("/gift_count/<int:post_id>")
def gift_count(post_id):

    total = db.session.query(
        db.func.sum(GiftTransaction.quantity)
    ).filter_by(post_id=post_id).scalar()

    return jsonify({
        "count": total or 0
    })
    
@app.route("/send_gift", methods=["POST"])
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

@app.route("/my_gifts")
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

@app.route("/check_gift_access", methods=["POST"])
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
@app.route("/my_posts")
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
    
@app.route("/users_to_add")

@login_required

def users_to_add():

    user_id = session["user_id"]


    # people I already added

    my_buddies = Buddy.query.filter_by(user_id=user_id).all()

    my_ids = [b.buddy_id for b in my_buddies]


    users = User.query.filter(

        User.id != user_id,

        ~User.id.in_(my_ids),

        User.user_dp_pic != None
    ).all()


    return jsonify({

        "count": len(users),

        "users": [{"id": u.id, "name": u.full_name, "dp": u.user_dp_pic} for u in users]

    })



@app.route("/following")

@login_required

def following():

    user_id = session["user_id"]


    buddies = Buddy.query.filter_by(user_id=user_id).all()

    ids = [b.buddy_id for b in buddies]


    users = User.query.filter(User.id.in_(ids)).all() if ids else []


    return jsonify({

        "count": len(users),

        "users": [{"id": u.id, "name": u.full_name, "dp": u.user_dp_pic, "bio": u.bio} for u in users]

    })


@app.route("/dp", methods=['GET', 'POST'])

@login_required

def dp():

    user = User.query.get(session['user_id'])


    if request.method == 'POST':

        full_name = request.form.get("full_name")

        bio = request.form.get("bio")

        file = request.files.get('user_dp_pic')


        # Update name

        if full_name:
            user.full_name = full_name


        # Update bio

        if bio is not None:
            user.bio = bio


        # Update profile picture

        if file and file.filename != '' and allowed_file(file.filename):


            # delete old pic

            if user.user_dp_pic and user.user_dp_pic != 'default_avatar.png':

                old_path = os.path.join(app.config['user_dp_folder'], user.user_dp_pic)

                if os.path.exists(old_path):

                    os.remove(old_path)


            filename = secure_filename(f"user_{user.id}.{file.filename.rsplit('.',1)[1].lower()}")

            file.save(os.path.join(app.config['user_dp_folder'], filename))


            user.user_dp_pic = filename


        db.session.commit()

        flash("Profile updated successfully!")


        return redirect(url_for('dp'))


    return render_template('my_dp.html', user=user)


@app.route("/followers")

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
# -------- USER FOLLOWERS (BUDDIES WHO ADDED THIS USER) --------
@app.route("/followers/<int:user_id>")
@login_required
def user_followers(user_id):

    followers = Buddy.query.filter_by(buddy_id=user_id).all()
    ids = [b.user_id for b in followers]

    users = User.query.filter(User.id.in_(ids)).all() if ids else []

    return render_template("followers.html", users=users)


# -------- USER FOLLOWING (WHO THIS USER ADDED) --------
@app.route("/following/<int:user_id>")
@login_required
def user_following(user_id):

    buddies = Buddy.query.filter_by(user_id=user_id).all()
    ids = [b.buddy_id for b in buddies]

    users = User.query.filter(User.id.in_(ids)).all() if ids else []

    return render_template("following.html", users=users)

# -------- ADD BUDDY --------

@app.route("/add_buddy", methods=["POST"])

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


    buddy = Buddy(user_id=user_id, buddy_id=buddy_id)

    db.session.add(buddy)

    db.session.commit()


    return jsonify({"success": True})

@app.route("/user_info/<int:user_id>")
@login_required
def user_info(user_id):
    user = User.query.get_or_404(user_id)

    return jsonify({
        "id": user.id,
        "name": user.full_name,
        "dp": user.user_dp_pic
    })

@app.route("/mutual_buddies")
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



# -------- CREATE POST --------

@app.route("/create_post", methods=["POST"])

@login_required

def create_post():

    try:

        content = request.form.get("content")

        user_id = session.get("user_id")


        file = request.files.get("file")

        media_url = None

        media_type = None


        if file:

            filename = str(uuid.uuid4()) + "_" + file.filename

            path = os.path.join(UPLOAD_FOLDER, filename)

            file.save(path)


            media_url = "/" + path


            if filename.lower().endswith((".png", ".jpg", ".jpeg")):

                media_type = "image"

            elif filename.lower().endswith((".mp4", ".mov")):

                media_type = "video"

            else:

                media_type = "file"


        post = Post(

            user_id=user_id,

            content=content,

            media_url=media_url,

            media_type=media_type,

            anon_name="Anonymous"
        )

        db.session.add(post)

        db.session.commit()


        return jsonify({"success": True})


    except Exception as e:

        return jsonify({"error": str(e)}), 500


# -------- GET POSTS --------

@app.route("/posts")
@login_required
def get_posts():

    # GET ALL POSTS (LATEST FIRST)
    posts = Post.query.order_by(Post.created_at.desc()).all()

    result = []

    for p in posts:

        likes_count = Like.query.filter_by(post_id=p.id).count()

        comments_count = Comment.query.filter_by(post_id=p.id).count()

        liked = Like.query.filter_by(
            user_id=session["user_id"],
            post_id=p.id
        ).first() is not None

        result.append({
            "id": p.id,
            "content": p.content,
            "media": p.media_url,
            "type": p.media_type,
            "user": p.user_id,
            "likes": likes_count,
            "comments": comments_count,
            "liked": liked
        })

    return jsonify(result)

# -------- WALLET API --------

@app.route("/wallet/<int:user_id>")

def wallet(user_id):

    wallet = Wallet.query.filter_by(user_id=user_id).first()


    if not wallet:

        wallet = Wallet(user_id=user_id, balance=0)

        db.session.add(wallet)

        db.session.commit()


    return jsonify({"balance": wallet.balance})
@app.route("/wallet_page")
@login_required
def wallet_page():
    return render_template("wallet.html")

@app.route("/earnings")
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


# -------- CHAT --------
@app.route("/send_message", methods=["POST"])
@login_required
def send_message():

    data = request.json

    sender_id = session["user_id"]   # ✅ FORCE REAL USER

    msg = ChatMessage(
        sender_id=sender_id,
        receiver_id=int(data["receiver_id"]),
        message=data["message"]
    )

    db.session.add(msg)
    db.session.commit()

    return jsonify({"success": True})
@app.route("/get_messages/<int:user1>/<int:user2>")
@login_required
def get_messages(user1, user2):

    messages = ChatMessage.query.filter(
        ((ChatMessage.sender_id == user1) & (ChatMessage.receiver_id == user2)) |
        ((ChatMessage.sender_id == user2) & (ChatMessage.receiver_id == user1))
    ).order_by(ChatMessage.created_at.asc()).all()

    # ✅ MARK AS READ
    for m in messages:
        if m.receiver_id == user1:
            m.is_read = True

    db.session.commit()

    return jsonify([{
        "sender": m.sender_id,
        "message": m.message
    } for m in messages])

@app.route("/unread_counts")
@login_required
def unread_counts():

    user_id = session["user_id"]

    messages = ChatMessage.query.filter_by(receiver_id=user_id, is_read=False).all()

    counts = {}

    for m in messages:
        counts[m.sender_id] = counts.get(m.sender_id, 0) + 1

    return jsonify(counts)

@app.route("/user/<int:user_id>")
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
# -------- CLEAR CHAT --------

@app.route("/clear_chat", methods=["POST"])

def clear_chat():

    data = request.json


    ChatMessage.query.filter(

        ((ChatMessage.sender_id == data["user1"]) & (ChatMessage.receiver_id == data["user2"])) |

        ((ChatMessage.sender_id == data["user2"]) & (ChatMessage.receiver_id == data["user1"]))
    ).delete()


    db.session.commit()


    return jsonify({"success": True})

@socketio.on("join")
def handle_join(data):
    user_id = data["user_id"]
    join_room(str(user_id))
# ---------------- RUN ----------------


if __name__ == "__main__":
    with app.app_context():
        seed_gifts()

    port = int(os.environ.get("PORT", 10000))
    socketio.run(app, host="0.0.0.0", port=port, debug=True, use_reloader=False)