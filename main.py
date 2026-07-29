from datetime import datetime, timedelta
from flask import Flask, request
from flask_jwt_extended import (
    JWTManager,
    create_access_token,
    create_refresh_token,
    jwt_required,
    get_jwt_identity
)
import cloudinary
import cloudinary.uploader
from werkzeug.utils import secure_filename
from config import Config
from extensions import (
    db,
    migrate,
    jwt,
    cors,
    socketio
)

from models import (
    User,
    Buddy,
    Post,
    Like,
    Comment,
    Earning,
    LIKE_EARN,
    COMMENT_EARN,
    MILESTONE_EARN,
    Wallet,
    Milestone,
    DepositTransaction,
    WithdrawalRequest,
    WithdrawalTransaction,
    BuddyMilestone,
    ChatMessage,
    ChatRoom,
    Gift,
    GiftTransaction,
    GiftTransactionItem,
    Notification,
    UserGiftBalance

)
from helpers import (
    generate_otp,
    send_otp_email,
    success_response,
    error_response,
    verify_password,
    allowed_file,
    add_to_wallet,
    create_buddy_milestone
)
from flask_socketio import (
    join_room,
    disconnect
)
from decimal import Decimal
import uuid
import os
from werkzeug.security import generate_password_hash


app = Flask(__name__)

app.config.from_object(Config)

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
socketio.init_app(app)
cloudinary.config(
    cloud_name=app.config["CLOUDINARY_NAME"],
    api_key=app.config["CLOUDINARY_KEY"],
    api_secret=app.config["CLOUDINARY_SECRET"],
    secure=True
)

@app.route("/")
def index():
    return {
        "success": True,
        "application": "Nonimas Android Backend",
        "status": "Running"
    }


# ==========================================================
# AUTH
# ==========================================================

@app.post("/api/auth/register")
def register():

    data = request.get_json(silent=True)

    if not data:
        return error_response("Invalid request")

    full_name = data.get("full_name", "").strip()
    phone = data.get("phone", "").strip()
    email = data.get("email")
    country = data.get("country")
    password = data.get("password")
    confirm_password = data.get("confirm_password")

    if not full_name:
        return error_response("Full name is required")

    if not phone:
        return error_response("Phone number is required")

    if not password:
        return error_response("Password is required")

    if password != confirm_password:
        return error_response("Passwords do not match")

    existing_phone = User.query.filter_by(
        phone=phone
    ).first()

    if existing_phone:
        return error_response(
            "Phone already exists"
        )

    if email:

        email = email.strip().lower()

        existing_email = User.query.filter_by(
            email=email
        ).first()

        if existing_email:
            return error_response(
                "Email already exists"
            )

    otp = generate_otp()

    user = User(
        full_name=full_name,
        phone=phone,
        password=generate_password_hash(password),
        email=email,
        country=country,
        otp_code=otp,
        otp_expiry=datetime.utcnow() + timedelta(minutes=5),
        is_verified=False
    )

    db.session.add(user)
    db.session.commit()

    if email:

        try:
            send_otp_email(
                email,
                otp
            )

        except Exception as e:
            print(e)

    return success_response(
        "Registration successful. Verify your account using the OTP sent to your email.",
        {
            "user_id": user.id,
            "email": user.email,
            "phone": user.phone,
            "requires_verification": True
        },
        201
    )


@app.post("/api/auth/login")
def login():

    data = request.get_json(silent=True)

    if not data:
        return error_response(
            "Invalid request"
        )

    identifier = data.get(
        "identifier",
        ""
    ).strip().lower()

    password = data.get(
        "password",
        ""
    )

    if not identifier:
        return error_response(
            "Phone or email is required"
        )

    if not password:
        return error_response(
            "Password is required"
        )

    if "@" in identifier:

        user = User.query.filter_by(
            email=identifier
        ).first()

    else:

        user = User.query.filter_by(
            phone=identifier
        ).first()

    if not user:
        return error_response(
            "Invalid login details",
            401
        )

    if not verify_password(
        user.password,
        password
    ):
        return error_response(
            "Invalid login details",
            401
        )

    if not user.is_verified:

        return error_response(
            "Account not verified",
            403
        )

    access_token = create_access_token(
        identity=str(user.id)
    )

    refresh_token = create_refresh_token(
        identity=str(user.id)
    )

    return success_response(
        "Login successful",
        {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "user": {
                "id": user.id,
                "full_name": user.full_name,
                "phone": user.phone,
                "email": user.email,
                "country": user.country,
                "bio": user.bio,
                "user_dp_pic": user.user_dp_pic,
                "is_verified": user.is_verified,
                "is_admin": user.is_admin
            }
        }
    )


@app.post("/api/auth/verify-account")
def verify_account():

    data = request.get_json(silent=True)

    if not data:
        return error_response("Invalid request")

    user_id = data.get("user_id")
    otp = data.get("otp", "").strip()

    if not user_id:
        return error_response("User ID is required")

    if not otp:
        return error_response("OTP is required")

    user = User.query.get(user_id)

    if not user:
        return error_response(
            "User not found",
            404
        )

    if otp != user.otp_code:
        return error_response(
            "Invalid OTP"
        )

    if datetime.utcnow() > user.otp_expiry:
        return error_response(
            "OTP expired"
        )

    user.is_verified = True
    user.otp_code = None
    user.otp_expiry = None

    db.session.commit()

    access_token = create_access_token(
        identity=str(user.id)
    )

    refresh_token = create_refresh_token(
        identity=str(user.id)
    )

    return success_response(
        "Account verified successfully",
        {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "user": {
                "id": user.id,
                "full_name": user.full_name,
                "phone": user.phone,
                "email": user.email,
                "country": user.country,
                "bio": user.bio,
                "user_dp_pic": user.user_dp_pic,
                "is_verified": user.is_verified,
                "is_admin": user.is_admin
            }
        }
    )


@app.post("/api/auth/resend-otp")
def resend_otp():

    data = request.get_json(silent=True)

    if not data:
        return error_response(
            "Invalid request"
        )

    user_id = data.get("user_id")

    if not user_id:
        return error_response(
            "User ID is required"
        )

    user = User.query.get(user_id)

    if not user:
        return error_response(
            "User not found",
            404
        )

    otp = generate_otp()

    user.otp_code = otp
    user.otp_expiry = datetime.utcnow() + timedelta(
        minutes=5
    )

    db.session.commit()

    try:
        if user.email:
            send_otp_email(
                user.email,
                otp
            )

    except Exception as e:
        print(e)

    return success_response(
        "OTP sent successfully"
    )


@app.get("/api/auth/me")
@jwt_required()
def me():

    user_id = get_jwt_identity()

    user = User.query.get(user_id)

    if not user:
        return error_response(
            "User not found",
            404
        )

    return success_response(
        "Profile loaded",
        {
            "id": user.id,
            "full_name": user.full_name,
            "phone": user.phone,
            "email": user.email,
            "country": user.country,
            "bio": user.bio,
            "user_dp_pic": user.user_dp_pic,
            "is_verified": user.is_verified,
            "is_admin": user.is_admin
        }
    )


@app.post("/api/auth/logout")
@jwt_required()
def logout():

    return success_response(
        "Logged out successfully"
    )
# ==========================================================
# JWT ERROR HANDLERS
# ==========================================================

@jwt.expired_token_loader
def expired_token_callback(jwt_header, jwt_payload):
    return error_response(
        "Access token has expired",
        401
    )


@jwt.invalid_token_loader
def invalid_token_callback(error):
    return error_response(
        "Invalid access token",
        401
    )


@jwt.unauthorized_loader
def missing_token_callback(error):
    return error_response(
        "Authorization token is required",
        401
    )


@jwt.needs_fresh_token_loader
def fresh_token_required(jwt_header, jwt_payload):
    return error_response(
        "Fresh token required",
        401
    )


@jwt.revoked_token_loader
def revoked_token_callback(jwt_header, jwt_payload):
    return error_response(
        "Token has been revoked",
        401
    )


# ==========================================================
# API ERROR HANDLERS
# ==========================================================

@app.errorhandler(400)
def bad_request(error):
    return error_response(
        "Bad request",
        400
    )


@app.errorhandler(401)
def unauthorized(error):
    return error_response(
        "Unauthorized",
        401
    )


@app.errorhandler(403)
def forbidden(error):
    return error_response(
        "Forbidden",
        403
    )


@app.errorhandler(404)
def not_found(error):
    return error_response(
        "Resource not found",
        404
    )


@app.errorhandler(405)
def method_not_allowed(error):
    return error_response(
        "Method not allowed",
        405
    )


@app.errorhandler(500)
def internal_server_error(error):
    db.session.rollback()

    return error_response(
        "Internal server error",
        500
    )
# ==========================================================
# MY PROFILE / UPDATE DP
# ==========================================================

@app.route("/api/profile/me", methods=["GET", "PUT"])
@jwt_required()
def my_profile():

    user_id = get_jwt_identity()

    user = User.query.get(user_id)

    if not user:
        return error_response(
            "User not found",
            404
        )

    if request.method == "PUT":

        data = request.get_json(silent=True)

        if not data:
            return error_response(
                "Invalid request"
            )

        full_name = data.get("full_name")
        bio = data.get("bio")

        if full_name:
            user.full_name = full_name.strip()

        if bio is not None:
            user.bio = bio

        db.session.commit()

    return success_response(
        "Profile loaded",
        {
            "id": user.id,
            "full_name": user.full_name,
            "phone": user.phone,
            "email": user.email,
            "country": user.country,
            "bio": user.bio,
            "user_dp_pic": user.user_dp_pic or "default_avatar.png",
            "is_online": user.is_online,
            "last_seen": user.last_seen,
            "is_verified": user.is_verified
        }
    )


# ==========================================================
# USER PROFILE
# ==========================================================

@app.get("/api/profile/<int:user_id>")
@jwt_required()
def user_profile_api(user_id):

    current_id = int(
        get_jwt_identity()
    )

    user = User.query.get(user_id)

    if not user:
        return error_response(
            "User not found",
            404
        )

    i_added = Buddy.query.filter_by(
        user_id=current_id,
        buddy_id=user_id
    ).first()

    added_me = Buddy.query.filter_by(
        user_id=user_id,
        buddy_id=current_id
    ).first()


    followers_count = Buddy.query.filter_by(
        buddy_id=user_id
    ).count()


    following_count = Buddy.query.filter_by(
        user_id=user_id
    ).count()


    return success_response(
        "Profile loaded",
        {
            "id": user.id,
            "full_name": user.full_name,
            "dp": user.user_dp_pic or "default_avatar.png",
            "bio": user.bio,
            "is_online": user.is_online,
            "last_seen": user.last_seen,
            "followers_count": followers_count,
            "following_count": following_count,
            "i_added": bool(i_added),
            "added_me": bool(added_me),
            "is_mutual": bool(
                i_added and added_me
            )
        }
    )


# ==========================================================
# USER POSTS
# ==========================================================

@app.get("/api/profile/<int:user_id>/posts")
@jwt_required()
def user_posts_api(user_id):

    posts = Post.query.filter_by(
        user_id=user_id
    ).order_by(
        Post.created_at.desc()
    ).all()


    return success_response(
        "Posts loaded",
        [
            {
                "id": p.id,
                "content": p.content,
                "media": p.media_url,
                "type": p.media_type,
                "created_at": (
                    p.created_at.strftime(
                        "%Y-%m-%d %H:%M"
                    )
                    if p.created_at else None
                )
            }
            for p in posts
        ]
    )


# ==========================================================
# USER INFO
# ==========================================================

@app.get("/api/profile/<int:user_id>/info")
@jwt_required()
def user_info_api(user_id):

    user = User.query.get(user_id)

    if not user:
        return error_response(
            "User not found",
            404
        )

    return success_response(
        "User information loaded",
        {
            "id": user.id,
            "name": user.full_name,
            "dp": user.user_dp_pic or "default_avatar.png",
            "is_online": user.is_online,
            "last_seen": user.last_seen
        }
    )


# ==========================================================
# FOLLOWERS
# ==========================================================

@app.get("/api/profile/<int:user_id>/followers")
@jwt_required()
def followers_api(user_id):

    followers = Buddy.query.filter_by(
        buddy_id=user_id
    ).all()

    ids = [
        follower.user_id
        for follower in followers
    ]

    users = User.query.filter(
        User.id.in_(ids)
    ).all() if ids else []


    return success_response(
        "Followers loaded",
        [
            {
                "id": u.id,
                "name": u.full_name,
                "dp": u.user_dp_pic or "default_avatar.png"
            }
            for u in users
        ]
    )


# ==========================================================
# FOLLOWING
# ==========================================================

@app.get("/api/profile/<int:user_id>/following")
@jwt_required()
def following_api(user_id):

    following = Buddy.query.filter_by(
        user_id=user_id
    ).all()


    ids = [
        f.buddy_id
        for f in following
    ]


    users = User.query.filter(
        User.id.in_(ids)
    ).all() if ids else []


    return success_response(
        "Following loaded",
        [
            {
                "id": u.id,
                "name": u.full_name,
                "dp": u.user_dp_pic or "default_avatar.png"
            }
            for u in users
        ]
    )
@app.put("/api/profile/me/dp")
@jwt_required()
def update_profile_picture():

    user_id = int(get_jwt_identity())

    user = User.query.get(user_id)

    if not user:
        return error_response(
            "User not found",
            404
        )

    if "user_dp_pic" not in request.files:
        return error_response(
            "Profile picture is required"
        )

    file = request.files["user_dp_pic"]

    if file.filename == "":
        return error_response(
            "No file selected"
        )

    if not allowed_file(file.filename):
        return error_response(
            "Only PNG, JPG, JPEG and WEBP files are allowed."
        )

    try:

        upload_result = cloudinary.uploader.upload(
            file,
            folder="user_dp_pics",
            public_id=f"user_{user.id}",
            overwrite=True,
            resource_type="image"
        )

        user.user_dp_pic = upload_result["secure_url"]

        db.session.commit()

        return success_response(
            "Profile picture updated successfully",
            {
                "user_dp_pic": user.user_dp_pic
            }
        )

    except Exception as e:

        db.session.rollback()

        return error_response(
            str(e),
            500
        )
# ==========================================================
# MY POSTS
# ==========================================================

@app.get("/api/profile/me/posts")
@jwt_required()
def my_posts_api():

    user_id = int(
        get_jwt_identity()
    )

    posts = Post.query.filter_by(
        user_id=user_id
    ).order_by(
        Post.created_at.desc()
    ).all()

    data = []

    for post in posts:

        data.append({

            "id": post.id,

            "content": post.content,

            "media": post.media_url,

            "type": post.media_type,

            "created_at": (
                post.created_at.strftime(
                    "%Y-%m-%d %H:%M"
                )
                if post.created_at
                else None
            )

        })

    return success_response(
        "My posts loaded",
        data
    )

# ==========================================================
# FEED
# ==========================================================

@app.get("/api/posts")
@jwt_required()
def get_posts_api():

    user_id = int(get_jwt_identity())

    posts = Post.query.order_by(
        Post.created_at.desc()
    ).all()

    post_ids = [p.id for p in posts]

    likes_data = db.session.query(
        Like.post_id,
        db.func.count(Like.id)
    ).filter(
        Like.post_id.in_(post_ids),
        Like.is_active == True
    ).group_by(
        Like.post_id
    ).all()

    likes_map = {
        post_id: count
        for post_id, count in likes_data
    }

    comments_data = db.session.query(
        Comment.post_id,
        db.func.count(Comment.id)
    ).filter(
        Comment.post_id.in_(post_ids)
    ).group_by(
        Comment.post_id
    ).all()

    comments_map = {
        post_id: count
        for post_id, count in comments_data
    }

    user_likes = Like.query.filter(
        Like.user_id == user_id,
        Like.post_id.in_(post_ids),
        Like.is_active == True
    ).all()

    liked_posts = {
        like.post_id
        for like in user_likes
    }

    data = []

    for post in posts:

        owner = User.query.get(post.user_id)

        data.append({

            "id": post.id,

            "content": post.content,

            "media": post.media_url,

            "type": post.media_type,

            "user": {
                "id": post.user_id,
                "name": owner.full_name if owner else "Unknown",
                "dp": (
                    owner.user_dp_pic
                    if owner and owner.user_dp_pic
                    else "default_avatar.png"
                )
            },

            "likes": likes_map.get(
                post.id,
                0
            ),

            "comments": comments_map.get(
                post.id,
                0
            ),

            "liked": post.id in liked_posts,

            "created_at": (
                post.created_at.strftime(
                    "%Y-%m-%d %H:%M"
                )
                if post.created_at
                else None
            )
        })

    return success_response(
        "Posts loaded",
        data
    )


# ==========================================================
# CREATE POST
# ==========================================================

@app.post("/api/posts")
@jwt_required()
def create_post_api():

    try:

        user_id = int(
            get_jwt_identity()
        )

        content = request.form.get(
            "content",
            ""
        ).strip()

        file = request.files.get("file")

        media_url = None
        media_type = None

        if file and file.filename:

            if "." not in file.filename:
                return error_response(
                    "Invalid file"
                )

            extension = os.path.splitext(
                file.filename
            )[1].lower()

            filename = secure_filename(
                f"{uuid.uuid4().hex}{extension}"
            )

            ext = extension.replace(".", "")

            image_extensions = {
                "png",
                "jpg",
                "jpeg",
                "gif",
                "webp"
            }

            video_extensions = {
                "mp4",
                "webm",
                "mov"
            }

            document_extensions = {
                "pdf",
                "docx"
            }

            if ext in image_extensions:
                media_type = "image"

            elif ext in video_extensions:
                media_type = "video"

            elif ext in document_extensions:
                media_type = "file"

            else:
                return error_response(
                    "Unsupported file type"
                )

            upload = cloudinary.uploader.upload(
                file,
                resource_type="auto"
            )

            media_url = upload.get(
                "secure_url"
            )

        post = Post(

            user_id=user_id,

            anon_name="Anonymous",

            content=content,

            media_url=media_url,

            media_type=media_type

        )

        db.session.add(post)

        db.session.commit()

        return success_response(
            "Post created successfully",
            {
                "post_id": post.id
            },
            201
        )

    except Exception as e:

        db.session.rollback()

        return error_response(
            str(e),
            500
        )


# ==========================================================
# LIKE / UNLIKE
# ==========================================================

@app.post("/api/posts/<int:post_id>/like")
@jwt_required()
def like_post_api(post_id):

    user_id = int(
        get_jwt_identity()
    )

    post = Post.query.get(post_id)

    if not post:

        return error_response(
            "Post not found",
            404
        )

    like = Like.query.filter_by(
        user_id=user_id,
        post_id=post_id
    ).first()

    if not like:

        like = Like(
            user_id=user_id,
            post_id=post_id,
            is_active=True,
            rewarded=True
        )

        db.session.add(like)

        earning = Earning(
            user_id=post.user_id,
            amount=LIKE_EARN
        )

        db.session.add(earning)

        add_to_wallet(
            post.user_id,
            LIKE_EARN
        )

    else:

        like.is_active = not like.is_active

        if (
            like.is_active
            and not like.rewarded
        ):

            earning = Earning(
                user_id=post.user_id,
                amount=LIKE_EARN
            )

            db.session.add(earning)

            add_to_wallet(
                post.user_id,
                LIKE_EARN
            )

            like.rewarded = True

        db.session.commit()

    total_likes = Like.query.filter_by(
        post_id=post_id,
        is_active=True
    ).count()

    return success_response(
        "Like updated",
        {
            "liked": like.is_active,
            "likes": total_likes
        }
    )


# ==========================================================
# ADD COMMENT
# ==========================================================

@app.post("/api/posts/<int:post_id>/comments")
@jwt_required()
def add_comment_api(post_id):

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

    text = data.get(
        "comment",
        ""
    ).strip()

    if not text:
        return error_response(
            "Comment cannot be empty"
        )

    post = Post.query.get(post_id)

    if not post:
        return error_response(
            "Post not found",
            404
        )

    comment = Comment(
        user_id=user_id,
        post_id=post_id,
        comment=text
    )

    db.session.add(comment)

    earning = Earning(
        user_id=post.user_id,
        amount=COMMENT_EARN
    )

    db.session.add(earning)

    add_to_wallet(
        post.user_id,
        COMMENT_EARN
    )

    db.session.commit()

    total_comments = Comment.query.filter_by(
        post_id=post_id
    ).count()

    return success_response(
        "Comment added successfully",
        {
            "comment_id": comment.id,
            "comments": total_comments
        },
        201
    )


# ==========================================================
# GET COMMENTS
# ==========================================================

@app.get("/api/posts/<int:post_id>/comments")
@jwt_required()
def get_comments_api(post_id):

    comments = Comment.query.filter_by(
        post_id=post_id
    ).order_by(
        Comment.created_at.asc()
    ).all()

    results = []

    for comment in comments:

        user = User.query.get(
            comment.user_id
        )

        results.append({

            "id": comment.id,

            "user": {
                "id": comment.user_id,
                "name": (
                    user.full_name
                    if user
                    else "Unknown"
                ),
                "dp": (
                    user.user_dp_pic
                    if user and user.user_dp_pic
                    else "default_avatar.png"
                )
            },

            "comment": comment.comment,

            "created_at": (
                comment.created_at.strftime(
                    "%Y-%m-%d %H:%M"
                )
                if comment.created_at
                else None
            )

        })

    return success_response(
        "Comments loaded",
        results
    )
# ==========================================================
# BUDDY PAGE
# ==========================================================

@app.get("/api/buddies")
@jwt_required()
def buddies_page_api():

    user_id = int(
        get_jwt_identity()
    )

    Buddy.query.filter_by(
        buddy_id=user_id,
        seen=False
    ).update({
        "seen": True
    })

    db.session.commit()

    return success_response(
        "Buddy page loaded"
    )


# ==========================================================
# MY FOLLOWERS
# ==========================================================

@app.get("/api/buddies/followers")
@jwt_required()
def followers_api():

    user_id = int(
        get_jwt_identity()
    )

    followers = Buddy.query.filter_by(
        buddy_id=user_id
    ).all()

    ids = [
        buddy.user_id
        for buddy in followers
    ]

    users = User.query.filter(
        User.id.in_(ids)
    ).all() if ids else []

    return success_response(
        "Followers loaded",
        {
            "count": len(users),
            "users": [
                {
                    "id": user.id,
                    "name": user.full_name,
                    "dp": user.user_dp_pic,
                    "bio": user.bio
                }
                for user in users
            ]
        }
    )


# ==========================================================
# USER FOLLOWERS
# ==========================================================

@app.get("/api/buddies/<int:user_id>/followers")
@jwt_required()
def user_followers_api(user_id):

    followers = Buddy.query.filter_by(
        buddy_id=user_id
    ).all()

    ids = [
        buddy.user_id
        for buddy in followers
    ]

    users = User.query.filter(
        User.id.in_(ids)
    ).all() if ids else []

    return success_response(
        "Followers loaded",
        [
            {
                "id": user.id,
                "name": user.full_name,
                "dp": user.user_dp_pic,
                "bio": user.bio
            }
            for user in users
        ]
    )


# ==========================================================
# USER FOLLOWING
# ==========================================================

@app.get("/api/buddies/<int:user_id>/following")
@jwt_required()
def user_following_api(user_id):

    buddies = Buddy.query.filter_by(
        user_id=user_id
    ).all()

    ids = [
        buddy.buddy_id
        for buddy in buddies
    ]

    users = User.query.filter(
        User.id.in_(ids)
    ).all() if ids else []

    return success_response(
        "Following loaded",
        [
            {
                "id": user.id,
                "name": user.full_name,
                "dp": user.user_dp_pic,
                "bio": user.bio
            }
            for user in users
        ]
    )


# ==========================================================
# ADD BUDDY
# ==========================================================

@app.post("/api/buddies")
@jwt_required()
def add_buddy_api():

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

    buddy_id = data.get(
        "buddy_id"
    )

    if not buddy_id:
        return error_response(
            "Buddy ID is required"
        )

    buddy_id = int(buddy_id)

    if buddy_id == user_id:
        return error_response(
            "Cannot add yourself"
        )

    existing = Buddy.query.filter_by(
        user_id=user_id,
        buddy_id=buddy_id
    ).first()

    if existing:
        return error_response(
            "Already buddies"
        )

    buddy = Buddy(
        user_id=user_id,
        buddy_id=buddy_id,
        seen=False
    )

    db.session.add(buddy)

    create_buddy_milestone(
        user_id
    )

    db.session.commit()

    return success_response(
        "Buddy added successfully"
    )


# ==========================================================
# USERS TO ADD
# ==========================================================

@app.get("/api/buddies/suggestions")
@jwt_required()
def users_to_add_api():

    user_id = int(
        get_jwt_identity()
    )

    my_buddies = Buddy.query.filter_by(
        user_id=user_id
    ).all()

    my_ids = [
        buddy.buddy_id
        for buddy in my_buddies
    ]

    users = User.query.filter(
        User.id != user_id,
        ~User.id.in_(my_ids)
    ).all()

    return success_response(
        "Users loaded",
        {
            "count": len(users),
            "users": [
                {
                    "id": user.id,
                    "name": user.full_name,
                    "dp": user.user_dp_pic or "default_avatar.png",
                    "is_online": user.is_online,
                    "last_seen": user.last_seen
                }
                for user in users
            ]
        }
    )
# ==========================================================
# MY FOLLOWING
# ==========================================================

@app.get("/api/buddies/following")
@jwt_required()
def following_api():

    user_id = int(
        get_jwt_identity()
    )

    buddies = Buddy.query.filter_by(
        user_id=user_id
    ).all()

    ids = [
        buddy.buddy_id
        for buddy in buddies
    ]

    users = User.query.filter(
        User.id.in_(ids)
    ).all() if ids else []

    return success_response(
        "Following loaded",
        {
            "count": len(users),
            "users": [
                {
                    "id": user.id,
                    "name": user.full_name,
                    "bio": user.bio,
                    "dp": user.user_dp_pic or "default_avatar.png",
                    "is_online": user.is_online,
                    "last_seen": user.last_seen
                }
                for user in users
            ]
        }
    )


# ==========================================================
# USER STATS
# ==========================================================

@app.get("/api/buddies/<int:user_id>/stats")
@jwt_required()
def user_stats_api(user_id):

    followers = Buddy.query.filter_by(
        buddy_id=user_id
    ).count()

    following = Buddy.query.filter_by(
        user_id=user_id
    ).count()

    posts = Post.query.filter_by(
        user_id=user_id
    ).count()

    return success_response(
        "User statistics loaded",
        {
            "followers": followers,
            "following": following,
            "posts": posts
        }
    )


# ==========================================================
# USER INFO
# ==========================================================

@app.get("/api/buddies/<int:user_id>/info")
@jwt_required()
def user_info_api(user_id):

    user = User.query.get(user_id)

    if not user:
        return error_response(
            "User not found",
            404
        )

    return success_response(
        "User information loaded",
        {
            "id": user.id,
            "name": user.full_name,
            "dp": user.user_dp_pic or "default_avatar.png",
            "is_online": user.is_online,
            "last_seen": user.last_seen
        }
    )


# ==========================================================
# MUTUAL BUDDIES
# ==========================================================

@app.get("/api/buddies/mutual")
@jwt_required()
def mutual_buddies_api():

    user_id = int(
        get_jwt_identity()
    )

    my = Buddy.query.filter_by(
        user_id=user_id
    ).all()

    my_ids = {
        buddy.buddy_id
        for buddy in my
    }

    added_me = Buddy.query.filter_by(
        buddy_id=user_id
    ).all()

    added_me_ids = {
        buddy.user_id
        for buddy in added_me
    }

    mutual_ids = my_ids.intersection(
        added_me_ids
    )

    users = User.query.filter(
        User.id.in_(mutual_ids)
    ).all() if mutual_ids else []

    return success_response(
        "Mutual buddies loaded",
        [
            {
                "id": user.id,
                "name": user.full_name,
                "dp": user.user_dp_pic
            }
            for user in users
        ]
    )


# ==========================================================
# BUDDY NOTIFICATION COUNT
# ==========================================================

@app.get("/api/buddies/count")
@jwt_required()
def buddy_count_api():

    user_id = int(
        get_jwt_identity()
    )

    count = Buddy.query.filter_by(
        buddy_id=user_id,
        seen=False
    ).count()

    return success_response(
        "Buddy count loaded",
        {
            "count": count
        }
    )

# ==========================================================
# SEARCH BUDDIES
# ==========================================================

@app.post("/api/buddies/search")
@jwt_required()
def search_buddies_api():

    data = request.get_json(
        silent=True
    )

    if not data:
        return error_response(
            "Invalid request"
        )

    buddy_id = data.get("buddy_id")
    buddy_name = data.get(
        "buddy_name",
        ""
    ).strip()

    if not buddy_id and not buddy_name:
        return error_response(
            "Buddy ID or name is required"
        )

    if buddy_id:
        user = User.query.get(
            buddy_id
        )
    else:
        user = User.query.filter(
            User.full_name.contains(
                buddy_name
            )
        ).first()

    if not user:
        return error_response(
            "User not found",
            404
        )

    return success_response(
        "Search completed",
        [
            {
                "id": user.id,
                "name": user.full_name,
                "dp": user.user_dp_pic or "default_avatar.png"
            }
        ]
    )


# ==========================================================
# MY BUDDIES
# ==========================================================

@app.get("/api/buddies/my")
@jwt_required()
def my_buddies_api():

    user_id = int(
        get_jwt_identity()
    )

    my_buddies = Buddy.query.filter_by(
        user_id=user_id
    ).all()

    my_ids = {
        buddy.buddy_id
        for buddy in my_buddies
    }

    added_me = Buddy.query.filter_by(
        buddy_id=user_id
    ).all()

    added_me_ids = {
        buddy.user_id
        for buddy in added_me
    }

    all_ids = my_ids.union(
        added_me_ids
    )

    users = User.query.filter(
        User.id.in_(all_ids)
    ).all() if all_ids else []

    result = []

    for user in users:

        result.append(
            {
                "id": user.id,
                "name": user.full_name,
                "dp": user.user_dp_pic or "default_avatar.png",
                "is_mutual": (
                    user.id in my_ids
                    and user.id in added_me_ids
                )
            }
        )

    return success_response(
        "My buddies loaded",
        result
    )
# ==========================================================
# MY WALLET
# ==========================================================

@app.get("/api/wallet")
@jwt_required()
def wallet_api():

    user_id = int(
        get_jwt_identity()
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
        db.session.commit()

    return success_response(
        "Wallet loaded",
        {
            "balance": wallet.balance
        }
    )


# ==========================================================
# WALLET PAGE
# ==========================================================

@app.get("/api/wallet/home")
@jwt_required()
def wallet_page_api():

    user_id = int(
        get_jwt_identity()
    )

    Earning.query.filter_by(
        user_id=user_id,
        seen=False
    ).update({
        "seen": True
    })

    db.session.commit()

    return success_response(
        "Wallet page loaded"
    )


# ==========================================================
# WALLET NOTIFICATION COUNT
# ==========================================================

@app.get("/api/wallet/count")
@jwt_required()
def wallet_count_api():

    user_id = int(
        get_jwt_identity()
    )

    count = Earning.query.filter_by(
        user_id=user_id,
        seen=False
    ).count()

    return success_response(
        "Wallet count loaded",
        {
            "count": count
        }
    )


# ==========================================================
# EARNINGS
# ==========================================================

@app.get("/api/wallet/earnings")
@jwt_required()
def earnings_api():

    user_id = int(
        get_jwt_identity()
    )

    rows = Earning.query.filter_by(
        user_id=user_id
    ).order_by(
        Earning.created_at.desc()
    ).limit(
        20
    ).all()

    return success_response(
        "Earnings loaded",
        [
            {
                "amount": row.amount,
                "date": (
                    row.created_at.strftime(
                        "%Y-%m-%d %H:%M"
                    )
                    if row.created_at else None
                )
            }
            for row in rows
        ]
    )

# ==========================================================
# PAYPAL HELPERS
# ==========================================================

import base64
import requests

PAYPAL_BASE_URL = (
    "https://api-m.sandbox.paypal.com"
    if app.config["PAYPAL_MODE"] == "sandbox"
    else "https://api-m.paypal.com"
)


def paypal_access_token():

    credentials = (
        f'{app.config["PAYPAL_CLIENT_ID"]}:'
        f'{app.config["PAYPAL_CLIENT_SECRET"]}'
    )

    encoded = base64.b64encode(
        credentials.encode()
    ).decode()

    response = requests.post(
        f"{PAYPAL_BASE_URL}/v1/oauth2/token",
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

@app.post("/api/wallet/deposit")
@jwt_required()
def deposit_api():

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

        f"{PAYPAL_BASE_URL}/v2/checkout/orders",

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

    return success_response(

        "PayPal order created",

        {

            "order_id": order["id"],

            "approval_url": approval_url

        }

    )
# ==========================================================
# VERIFY PAYPAL DEPOSIT
# ==========================================================

@app.post("/api/wallet/deposit/verify")
@jwt_required()
def verify_deposit_api():

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

    return success_response(

        "Deposit completed successfully",

        {
            "order_id": order_id,
            "amount": transaction.amount,
            "balance": wallet.balance
        }

    )
# ==========================================================
# WITHDRAW PAGE
# ==========================================================

@app.get("/api/wallet/withdraw")
@jwt_required()
def withdraw_page_api():

    user_id = int(
        get_jwt_identity()
    )

    wallet = Wallet.query.filter_by(
        user_id=user_id
    ).first()

    withdrawals = WithdrawalRequest.query.filter_by(
        user_id=user_id
    ).order_by(
        WithdrawalRequest.created_at.desc()
    ).all()

    return success_response(
        "Withdrawal information loaded",
        {
            "wallet": {
                "balance": (
                    wallet.balance
                    if wallet
                    else 0.0
                )
            },
            "withdrawals": [
                {
                    "id": withdrawal.id,
                    "amount": withdrawal.amount,
                    "account_name": withdrawal.account_name,
                    "bank_name": withdrawal.bank_name,
                    "account_number": withdrawal.account_number,
                    "status": withdrawal.status,
                    "created_at": (
                        withdrawal.created_at.strftime(
                            "%Y-%m-%d %H:%M"
                        )
                        if withdrawal.created_at
                        else None
                    ),
                    "processed_at": (
                        withdrawal.processed_at.strftime(
                            "%Y-%m-%d %H:%M"
                        )
                        if withdrawal.processed_at
                        else None
                    )
                }
                for withdrawal in withdrawals
            ]
        }
    )


# ==========================================================
# REQUEST WITHDRAWAL
# ==========================================================

@app.post("/api/wallet/withdraw")
@jwt_required()
def request_withdrawal_api():

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
            data.get(
                "amount",
                0
            )
        )

    except Exception:

        return error_response(
            "Invalid amount"
        )

    wallet = Wallet.query.filter_by(
        user_id=user_id
    ).first()

    if not wallet:
        return error_response(
            "Wallet not found",
            404
        )

    if amount <= 0:
        return error_response(
            "Invalid amount"
        )

    if wallet.balance < amount:
        return error_response(
            "Insufficient balance"
        )

    withdrawal = WithdrawalRequest(
        user_id=user_id,
        amount=amount,
        bank_name=data.get("bank_name"),
        account_name=data.get("account_name"),
        account_number=data.get("account_number")
    )

    db.session.add(
        withdrawal
    )

    db.session.commit()

    return success_response(
        "Withdrawal request submitted successfully",
        {
            "withdrawal_id": withdrawal.id,
            "status": withdrawal.status
        },
        201
    )
# ==========================================================
# CHAT
# ==========================================================

@app.post("/api/chat/send")
@jwt_required()
def send_message():

    try:

        user_id = int(get_jwt_identity())

        receiver_id = request.form.get("receiver_id")

        if not receiver_id:
            return error_response("Receiver ID is required")

        try:
            receiver_id = int(receiver_id)
        except ValueError:
            return error_response("Invalid receiver ID")

        receiver = User.query.get(receiver_id)

        if not receiver:
            return error_response(
                "Receiver not found",
                404
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
            return error_response("Empty message")

        message = ChatMessage(
            sender_id=user_id,
            receiver_id=receiver_id,
            message=text,
            media_url=media_url,
            media_type=media_type
        )

        db.session.add(message)
        db.session.commit()

        socketio.emit(
            "new_message",
            {
                "sender": user_id,
                "receiver": receiver_id
            },
            room=str(receiver_id)
        )

        return success_response(
            "Message sent successfully",
            {
                "message_id": message.id,
                "sender_id": message.sender_id,
                "receiver_id": message.receiver_id,
                "message": message.message,
                "media_url": message.media_url,
                "media_type": message.media_type,
                "created_at": message.created_at.strftime(
                    "%Y-%m-%d %H:%M"
                )
            }
        )

    except Exception as e:

        print("SEND MESSAGE ERROR:", e)

        return error_response(
            str(e),
            500
        )


@app.get("/api/chat/status/<int:user_id>")
@jwt_required()
def user_status(user_id):

    user = User.query.get(user_id)

    if not user:
        return error_response(
            "User not found",
            404
        )

    return success_response(
        "User status retrieved",
        {
            "online": user.is_online,
            "last_seen": (
                user.last_seen.strftime("%H:%M")
                if user.last_seen
                else "recently"
            )
        }
    )
@app.delete("/api/chat/message")
@jwt_required()
def delete_message():

    data = request.get_json(silent=True)

    if not data:
        return error_response("Invalid request")

    message_id = data.get("message_id")

    if not message_id:
        return error_response("Message ID is required")

    user_id = int(get_jwt_identity())

    message = ChatMessage.query.get(message_id)

    if not message:
        return error_response(
            "Message not found",
            404
        )

    if message.sender_id != user_id:
        return error_response(
            "Unauthorized",
            403
        )

    db.session.delete(message)
    db.session.commit()

    return success_response(
        "Message deleted successfully"
    )


@app.get("/api/chat/messages/<int:other_user>")
@jwt_required()
def get_messages(other_user):

    user_id = int(get_jwt_identity())

    other = User.query.get(other_user)

    if not other:
        return error_response(
            "User not found",
            404
        )

    messages = ChatMessage.query.filter(
        (
            (ChatMessage.sender_id == user_id) &
            (ChatMessage.receiver_id == other_user)
        ) |
        (
            (ChatMessage.sender_id == other_user) &
            (ChatMessage.receiver_id == user_id)
        )
    ).order_by(
        ChatMessage.created_at.asc()
    ).all()

    unread_messages = []

    for message in messages:

        if (
            message.receiver_id == user_id and
            not message.is_read
        ):
            message.is_read = True
            unread_messages.append(message.id)

    db.session.commit()

    if unread_messages:

        socketio.emit(
            "messages_read",
            {
                "message_ids": unread_messages,
                "reader": user_id
            },
            room=str(user_id)
        )

    return success_response(
        "Messages retrieved successfully",
        {
            "messages": [
                {
                    "id": message.id,
                    "sender": message.sender_id,
                    "receiver": message.receiver_id,
                    "message": message.message,
                    "media_url": message.media_url,
                    "media_type": message.media_type,
                    "created_at": message.created_at.strftime(
                        "%Y-%m-%d %H:%M"
                    ),
                    "is_read": message.is_read
                }
                for message in messages
            ]
        }
    )
@app.delete("/api/chat/clear")
@jwt_required()
def clear_chat():

    data = request.get_json(silent=True)

    if not data:
        return error_response("Invalid request")

    other_user = data.get("other_user")

    if not other_user:
        return error_response("Other user is required")

    try:
        other_user = int(other_user)
    except ValueError:
        return error_response("Invalid user")

    user_id = int(get_jwt_identity())

    other = User.query.get(other_user)

    if not other:
        return error_response(
            "User not found",
            404
        )

    ChatMessage.query.filter(
        (
            (ChatMessage.sender_id == user_id) &
            (ChatMessage.receiver_id == other_user)
        )
        |
        (
            (ChatMessage.sender_id == other_user) &
            (ChatMessage.receiver_id == user_id)
        )
    ).delete(synchronize_session=False)

    db.session.commit()

    socketio.emit(
        "chat_cleared",
        {
            "user1": user_id,
            "user2": other_user
        },
        room=str(other_user)
    )

    return success_response(
        "Chat cleared successfully"
    )


@app.get("/api/chat/unread")
@jwt_required()
def unread_counts():

    user_id = int(get_jwt_identity())

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

    return success_response(
        "Unread counts retrieved",
        {
            "total": total,
            "users": counts
        }
    )

@socketio.on("connect")
def handle_connect(auth):

    try:

        if not auth or "token" not in auth:
            disconnect()
            return

        token = auth["token"]

        decoded = decode_token(token)

        user_id = int(decoded["sub"])

        user = User.query.get(user_id)

        if not user:
            disconnect()
            return

        user.is_online = True
        user.last_seen = datetime.utcnow()

        db.session.commit()

        join_room(str(user_id))

    except Exception:
        disconnect()


@socketio.on("disconnect")
def handle_disconnect():

    pass


@socketio.on("join")
def handle_join(auth):

    try:

        if not auth or "token" not in auth:
            return

        token = auth["token"]

        decoded = decode_token(token)

        user_id = int(decoded["sub"])

        join_room(str(user_id))

    except Exception:
        return


@socketio.on("typing")
def typing(data):

    try:

        token = data.get("token")

        receiver = int(data["receiver"])

        decoded = decode_token(token)

        user_id = int(decoded["sub"])

        socketio.emit(
            "typing",
            {
                "user": user_id
            },
            room=str(receiver)
        )

    except Exception:
        return


@socketio.on("stop_typing")
def stop_typing(data):

    try:

        token = data.get("token")

        receiver = int(data["receiver"])

        decoded = decode_token(token)

        user_id = int(decoded["sub"])

        socketio.emit(
            "stop_typing",
            {
                "user": user_id
            },
            room=str(receiver)
        )

    except Exception:
        return
# ==========================================================
# GIFTS
# ==========================================================
@app.get("/api/gifts")
@jwt_required()
def get_gifts():

    gifts = Gift.query.all()

    def clean_name(name):
        parts = name.split(" ")
        if parts and parts[0].isdigit():
            return " ".join(parts[1:])
        return name

    return success_response(
        "Gifts retrieved successfully",
        {
            "gifts": [
                {
                    "id": gift.id,
                    "name": clean_name(gift.name),
                    "price": gift.price,
                    "value": gift.value
                }
                for gift in gifts
            ]
        }
    )


@app.post("/api/gifts/buy")
@jwt_required()
def buy_gift():

    data = request.get_json(silent=True)

    if not data:
        return error_response("Invalid request")

    user_id = int(get_jwt_identity())

    gift_id = data.get("gift_id")
    quantity = int(data.get("quantity", 1))

    if not gift_id:
        return error_response("Gift ID is required")

    gift = Gift.query.get(gift_id)

    if not gift:
        return error_response(
            "Gift not found",
            404
        )

    wallet = Wallet.query.filter_by(
        user_id=user_id
    ).first()

    if not wallet:

        wallet = Wallet(
            user_id=user_id,
            balance=0
        )

        db.session.add(wallet)
        db.session.commit()

    total_cost = gift.price * quantity

    if wallet.balance < total_cost:

        return error_response(
            "Insufficient balance"
        )

    wallet.balance -= total_cost

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

    transaction = GiftTransaction(
        sender_id=user_id,
        receiver_id=user_id,
        post_id=None,
        gift_id=gift_id,
        quantity=quantity,
        total_amount=total_cost
    )

    db.session.add(transaction)
    db.session.commit()

    return success_response(
        "Gift added to inventory",
        {
            "gift_id": gift.id,
            "gift_name": gift.name,
            "quantity": gift_balance.quantity,
            "wallet_balance": wallet.balance
        }
    )


@app.get("/api/gifts/count/<int:post_id>")
def gift_count(post_id):

    total = db.session.query(
        db.func.sum(
            GiftTransaction.quantity
        )
    ).filter_by(
        post_id=post_id
    ).scalar()

    return success_response(
        "Gift count retrieved",
        {
            "count": total or 0
        }
    )
@app.post("/api/gifts/send")
@jwt_required()
def send_gift():

    data = request.get_json(silent=True)

    if not data:
        return error_response("Invalid request")

    user_id = int(get_jwt_identity())

    post_id = data.get("post_id")
    gift_id = data.get("gift_id")
    quantity = int(data.get("quantity", 1))

    if not post_id:
        return error_response("Post ID is required")

    if not gift_id:
        return error_response("Gift ID is required")

    if quantity <= 0:
        return error_response("Invalid quantity")

    gift = Gift.query.get(gift_id)
    post = Post.query.get(post_id)

    if not gift or not post:
        return error_response(
            "Invalid gift or post"
        )

    gift_balance = UserGiftBalance.query.filter_by(
        user_id=user_id,
        gift_id=gift_id
    ).with_for_update().first()

    if not gift_balance:
        return error_response(
            "You don't own this gift"
        )

    if gift_balance.quantity < quantity:
        return error_response(
            f"Only {gift_balance.quantity} left"
        )

    gift_balance.quantity -= quantity

    if gift_balance.quantity <= 0:
        db.session.delete(gift_balance)
    elif gift_balance.quantity < 0:
        gift_balance.quantity = 0

    creator_earn = (
        gift.payout * quantity
        if hasattr(gift, "payout")
        else 0
    )

    earning = Earning(
        user_id=post.user_id,
        amount=creator_earn
    )

    sender = User.query.get(user_id)

    notification = Notification(
        user_id=post.user_id,
        title="Gift Received",
        message=f"{sender.full_name} sent you {quantity} {gift.name}"
    )

    db.session.add(notification)
    db.session.add(earning)

    add_to_wallet(
        post.user_id,
        creator_earn
    )

    transaction = GiftTransaction(
        sender_id=user_id,
        receiver_id=post.user_id,
        post_id=post_id,
        gift_id=gift_id,
        quantity=quantity,
        total_amount=0
    )

    db.session.add(transaction)

    db.session.commit()

    return success_response(
        "Gift sent successfully",
        {
            "remaining": (
                gift_balance.quantity
                if gift_balance.quantity > 0
                else 0
            )
        }
    )
@app.get("/api/gifts/my")
@jwt_required()
def my_gifts():

    user_id = int(get_jwt_identity())

    balances = db.session.query(
        Gift.id,
        Gift.name,
        UserGiftBalance.quantity
    ).join(
        UserGiftBalance,
        Gift.id == UserGiftBalance.gift_id
    ).filter(
        UserGiftBalance.user_id == user_id,
        UserGiftBalance.quantity > 0
    ).all()

    return success_response(
        "Gift inventory retrieved",
        {
            "gifts": [
                {
                    "id": gift_id,
                    "name": name,
                    "quantity": quantity
                }
                for gift_id, name, quantity in balances
            ]
        }
    )
@app.post("/api/gifts/check-access")
@jwt_required()
def check_gift_access():

    data = request.get_json(silent=True)

    if not data:
        return error_response("Invalid request")

    user_id = int(get_jwt_identity())

    gift_id = data.get("gift_id")

    if not gift_id:
        return error_response("Gift ID is required")

    gift = Gift.query.get(gift_id)

    if not gift:
        return success_response(
            "Gift access checked",
            {
                "allowed": False
            }
        )

    wallet = Wallet.query.filter_by(
        user_id=user_id
    ).first()

    if not wallet:
        return success_response(
            "Gift access checked",
            {
                "allowed": False
            }
        )

    owned = GiftTransaction.query.filter_by(
        sender_id=user_id,
        gift_id=gift_id
    ).first()

    if not owned and wallet.balance < gift.price:
        return success_response(
            "Gift access checked",
            {
                "allowed": False
            }
        )

    return success_response(
        "Gift access checked",
        {
            "allowed": True
        }
    )
# ==========================================================
# SETTINGS
# ==========================================================
@app.get("/api/settings/terms")
def terms():

    return success_response(
        "Terms retrieved successfully",
        {}
    )
@app.get("/api/settings/about")
def about():

    return success_response(
        "About retrieved successfully",
        {}
    )
# ==========================================================
# NOTIFICATIONS
# ==========================================================
@app.get("/api/notifications/count")
@jwt_required()
def notification_count():

    user_id = int(get_jwt_identity())

    count = Notification.query.filter_by(
        user_id=user_id,
        is_read=False
    ).count()

    return success_response(
        "Notification count retrieved",
        {
            "count": count
        }
    )
@app.get("/api/notifications")
@jwt_required()
def notifications():

    user_id = int(get_jwt_identity())

    Notification.query.filter_by(
        user_id=user_id,
        is_read=False
    ).update(
        {
            "is_read": True
        }
    )

    db.session.commit()

    notifications = Notification.query.filter_by(
        user_id=user_id
    ).order_by(
        Notification.created_at.desc()
    ).all()

    return success_response(
        "Notifications retrieved",
        {
            "notifications": [
                {
                    "id": notification.id,
                    "title": notification.title,
                    "message": notification.message,
                    "is_read": notification.is_read,
                    "created_at": notification.created_at.strftime(
                        "%Y-%m-%d %H:%M"
                    )
                }
                for notification in notifications
            ]
        }
    )
# ==========================================================
# SEARCH
# ==========================================================
@app.get("/api/search")
@jwt_required()
def search():

    q = request.args.get(
        "q",
        ""
    ).strip()

    if not q:

        return success_response(
            "Search completed",
            {
                "users": [],
                "posts": [],
                "messages": [],
                "transactions": []
            }
        )

    user_id = int(get_jwt_identity())

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
        DepositTransaction.paypal_order_id.ilike(f"%{q}%")
    ).limit(10).all()

    return success_response(
        "Search completed",
        {
            "users": [
                {
                    "id": user.id,
                    "name": user.full_name,
                    "dp": user.user_dp_pic
                }
                for user in users
            ],

            "posts": [
                {
                    "id": post.id,
                    "content": (
                        post.content[:100]
                        if post.content
                        else ""
                    )
                }
                for post in posts
            ],

            "messages": [
                {
                    "id": message.id,
                    "message": (
                        message.message[:100]
                        if message.message
                        else ""
                    ),
                    "sender": message.sender_id,
                    "receiver": message.receiver_id
                }
                for message in messages
            ],

            "transactions": [
                {
                    "id": transaction.id,
                    "reference": transaction.paypal_order_id,
                    "amount": transaction.amount
                }
                for transaction in transactions
            ]
        }
    )
# ==========================================================
# ADMIN
# ==========================================================
def admin_only():

    user = User.query.get(
        int(get_jwt_identity())
    )

    if not user:
        return None, error_response(
            "User not found",
            404
        )

    if not user.is_admin:
        return None, error_response(
            "Admin access only",
            403
        )

    return user, None
@app.get("/api/admin/dashboard")
@jwt_required()
def admin_dashboard():

    _, error = admin_only()

    if error:
        return error

    revenue = db.session.query(
        db.func.sum(
            GiftTransaction.total_amount
        )
    ).scalar() or 0

    payouts = db.session.query(
        db.func.sum(
            Earning.amount
        )
    ).scalar() or 0

    profit = revenue - payouts

    total_users = User.query.count()

    total_posts = Post.query.count()

    total_comments = Comment.query.count()

    total_likes = Like.query.count()

    total_gifts = db.session.query(
        db.func.sum(
            GiftTransaction.quantity
        )
    ).scalar() or 0

    popular_gifts = db.session.query(
        Gift.name,
        db.func.sum(
            GiftTransaction.quantity
        )
    ).join(
        GiftTransaction,
        Gift.id == GiftTransaction.gift_id
    ).group_by(
        Gift.name
    ).order_by(
        db.func.sum(
            GiftTransaction.quantity
        ).desc()
    ).limit(10).all()

    top_creators = db.session.query(
        User.full_name,
        db.func.sum(
            Earning.amount
        )
    ).join(
        Earning,
        User.id == Earning.user_id
    ).group_by(
        User.full_name
    ).order_by(
        db.func.sum(
            Earning.amount
        ).desc()
    ).limit(10).all()

    recent_users = User.query.order_by(
        User.timestamp.desc()
    ).limit(10).all()

    recent_posts = Post.query.order_by(
        Post.created_at.desc()
    ).limit(10).all()

    return success_response(
        "Dashboard retrieved",
        {
            "revenue": revenue,
            "payouts": payouts,
            "profit": profit,
            "total_users": total_users,
            "total_posts": total_posts,
            "total_comments": total_comments,
            "total_likes": total_likes,
            "total_gifts": total_gifts,
            "popular_gifts": [
                {
                    "name": name,
                    "quantity": quantity
                }
                for name, quantity in popular_gifts
            ],
            "top_creators": [
                {
                    "name": name,
                    "earnings": earnings
                }
                for name, earnings in top_creators
            ],
            "recent_users": [
                {
                    "id": user.id,
                    "full_name": user.full_name,
                    "phone": user.phone,
                    "email": user.email,
                    "created_at": user.timestamp.strftime(
                        "%Y-%m-%d %H:%M"
                    )
                }
                for user in recent_users
            ],
            "recent_posts": [
                {
                    "id": post.id,
                    "user_id": post.user_id,
                    "content": post.content,
                    "media_url": post.media_url,
                    "media_type": post.media_type,
                    "created_at": post.created_at.strftime(
                        "%Y-%m-%d %H:%M"
                    )
                }
                for post in recent_posts
            ]
        }
    )
@app.get("/api/admin/users")
@jwt_required()
def admin_users():

    _, error = admin_only()

    if error:
        return error

    users = User.query.order_by(
        User.timestamp.desc()
    ).all()

    return success_response(
        "Users retrieved",
        {
            "users": [
                {
                    "id": user.id,
                    "full_name": user.full_name,
                    "phone": user.phone,
                    "email": user.email,
                    "country": user.country,
                    "is_verified": user.is_verified,
                    "is_admin": user.is_admin,
                    "balance": user.balance,
                    "created_at": user.timestamp.strftime(
                        "%Y-%m-%d %H:%M"
                    )
                }
                for user in users
            ]
        }
    )
@app.delete("/api/admin/users")
@jwt_required()
def delete_selected_users():

    _, error = admin_only()

    if error:
        return error

    data = request.get_json(silent=True)

    if not data:
        return error_response("Invalid request")

    user_ids = data.get("user_ids", [])

    if not user_ids:
        return error_response("No users selected")

    for uid in user_ids:

        user = User.query.get(uid)

        if not user:
            continue

        if user.is_admin:
            continue

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

    return success_response(
        "Selected users deleted successfully"
    )


@app.delete("/api/admin/posts/<int:post_id>")
@jwt_required()
def delete_post_admin(post_id):

    _, error = admin_only()

    if error:
        return error

    post = Post.query.get(post_id)

    if not post:
        return error_response(
            "Post not found",
            404
        )

    if post.media_url:

        try:

            filename = os.path.basename(
                post.media_url
            )

            path = os.path.join(
                app.config["POST_UPLOAD_FOLDER"],
                filename
            )

            if os.path.exists(path):
                os.remove(path)

        except Exception as e:
            print("Media delete error:", e)

    Like.query.filter_by(
        post_id=post.id
    ).delete()

    Comment.query.filter_by(
        post_id=post.id
    ).delete()

    GiftTransaction.query.filter_by(
        post_id=post.id
    ).delete()

    db.session.delete(post)

    db.session.commit()

    return success_response(
        "Post deleted successfully"
    )


@app.get("/api/admin/posts")
@jwt_required()
def admin_posts():

    _, error = admin_only()

    if error:
        return error

    posts = Post.query.order_by(
        Post.created_at.desc()
    ).all()

    result = []

    for post in posts:

        user = User.query.get(
            post.user_id
        )

        likes = Like.query.filter_by(
            post_id=post.id,
            is_active=True
        ).count()

        comments = Comment.query.filter_by(
            post_id=post.id
        ).count()

        gifts = db.session.query(
            db.func.sum(
                GiftTransaction.quantity
            )
        ).filter_by(
            post_id=post.id
        ).scalar() or 0

        result.append(
            {
                "id": post.id,
                "user_name": (
                    user.full_name
                    if user else "Unknown"
                ),
                "content": post.content,
                "media": post.media_url,
                "type": post.media_type,
                "created_at": post.created_at.strftime(
                    "%Y-%m-%d %H:%M"
                ),
                "likes": likes,
                "comments": comments,
                "gifts": gifts
            }
        )

    return success_response(
        "Posts retrieved",
        {
            "posts": result
        }
    )
@app.delete("/api/admin/posts")
@jwt_required()
def delete_selected_posts():

    _, error = admin_only()

    if error:
        return error

    data = request.get_json(silent=True)

    if not data:
        return error_response("Invalid request")

    post_ids = data.get("post_ids", [])

    if not post_ids:
        return error_response("No posts selected")

    for pid in post_ids:

        post = Post.query.get(pid)

        if not post:
            continue

        if post.media_url:

            try:

                filename = os.path.basename(
                    post.media_url
                )

                path = os.path.join(
                    app.config["POST_UPLOAD_FOLDER"],
                    filename
                )

                if os.path.exists(path):
                    os.remove(path)

            except Exception as e:
                print("Delete error:", e)

        Like.query.filter_by(
            post_id=post.id
        ).delete()

        Comment.query.filter_by(
            post_id=post.id
        ).delete()

        GiftTransaction.query.filter_by(
            post_id=post.id
        ).delete()

        db.session.delete(post)

    db.session.commit()

    return success_response(
        "Selected posts deleted successfully"
    )


@app.delete("/api/admin/posts/all")
@jwt_required()
def clear_all_posts():

    _, error = admin_only()

    if error:
        return error

    posts = Post.query.all()

    for post in posts:

        if post.media_url:

            try:

                filename = os.path.basename(
                    post.media_url
                )

                path = os.path.join(
                    app.config["POST_UPLOAD_FOLDER"],
                    filename
                )

                if os.path.exists(path):
                    os.remove(path)

            except Exception as e:
                print("Delete error:", e)

        Like.query.filter_by(
            post_id=post.id
        ).delete()

        Comment.query.filter_by(
            post_id=post.id
        ).delete()

        GiftTransaction.query.filter_by(
            post_id=post.id
        ).delete()

        db.session.delete(post)

    db.session.commit()

    return success_response(
        "All posts cleared successfully"
    )


@app.get("/api/admin/withdrawals")
@jwt_required()
def admin_withdrawals():

    _, error = admin_only()

    if error:
        return error

    requests = WithdrawalRequest.query.order_by(
        WithdrawalRequest.created_at.desc()
    ).all()

    return success_response(
        "Withdrawal requests retrieved",
        {
            "requests": [
                {
                    "id": req.id,
                    "user_id": req.user_id,
                    "amount": req.amount,
                    "account_name": req.account_name,
                    "bank_name": req.bank_name,
                    "account_number": req.account_number,
                    "status": req.status,
                    "created_at": req.created_at.strftime(
                        "%Y-%m-%d %H:%M"
                    ),
                    "processed_at": (
                        req.processed_at.strftime(
                            "%Y-%m-%d %H:%M"
                        )
                        if req.processed_at
                        else None
                    )
                }
                for req in requests
            ]
        }
    )
@app.post("/api/admin/withdrawals/<int:id>/approve")
@jwt_required()
def approve_withdrawal(id):

    _, error = admin_only()

    if error:
        return error

    req = WithdrawalRequest.query.get(id)

    if not req:
        return error_response(
            "Withdrawal request not found",
            404
        )

    if req.status != "pending":
        return error_response(
            "Withdrawal request has already been processed"
        )

    wallet = Wallet.query.filter_by(
        user_id=req.user_id
    ).first()

    if not wallet:
        return error_response(
            "Wallet not found",
            404
        )

    if wallet.balance < req.amount:

        req.status = "rejected"

        req.processed_at = datetime.utcnow()

        db.session.commit()

        return error_response(
            "Insufficient wallet balance. Withdrawal rejected."
        )

    wallet.balance -= req.amount

    req.status = "approved"

    req.processed_at = datetime.utcnow()

    db.session.commit()

    return success_response(
        "Withdrawal approved successfully"
    )


@app.post("/api/admin/withdrawals/<int:id>/reject")
@jwt_required()
def reject_withdrawal(id):

    _, error = admin_only()

    if error:
        return error

    req = WithdrawalRequest.query.get(id)

    if not req:
        return error_response(
            "Withdrawal request not found",
            404
        )

    if req.status != "pending":
        return error_response(
            "Withdrawal request has already been processed"
        )

    req.status = "rejected"

    req.processed_at = datetime.utcnow()

    db.session.commit()

    return success_response(
        "Withdrawal rejected successfully"
    )

# ==========================================================
# START APPLICATION
# ==========================================================

if __name__ == "__main__":
    socketio.run(
        app,
        host="0.0.0.0",
        port=5001,
        debug=True
    )