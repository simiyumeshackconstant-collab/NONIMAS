import os
import logging
import uuid
import json
import ssl
import threading
from flask import Flask
from datetime import datetime, timedelta
from models import User, ChatMessage, CallSession
from extensions import db, migrate, jwt, cors
from helpers import send_incoming_call_notification, send_chat_message_notification
import paho.mqtt.client as mqtt


MQTT_BROKER = os.getenv(
    "MQTT_BROKER",
    "zc183c1b.ala.us-east-1.emqxsl.com"
)

MQTT_PORT = int(
    os.getenv("MQTT_PORT", "8883")
)

MQTT_USERNAME = os.getenv(
    "MQTT_USERNAME"
)

MQTT_PASSWORD = os.getenv(
    "MQTT_PASSWORD"
)

MQTT_CLIENT_ID = os.getenv(
    "MQTT_CLIENT_ID",
    "nonimas-backend"
)


class MQTTService:
    EVENT_CALL_INVITE = "call_invite"
    EVENT_CALL_RINGING = "call_ringing"
    EVENT_CALL_BUSY = "call_busy"
    EVENT_CALL_OFFLINE = "call_offline"
    EVENT_CALL_ACCEPT = "call_accept"
    EVENT_CALL_CONNECTED = "call_connected"
    EVENT_CALL_REJECT = "call_reject"
    EVENT_CALL_END = "call_end"
    EVENT_CALL_MISSED = "call_missed"

    def __init__(self, flask_app=None):

        self.flask_app = flask_app
        self.client = mqtt.Client(
            mqtt.CallbackAPIVersion.VERSION2,
            client_id=MQTT_CLIENT_ID,
            clean_session=True
        )

        if MQTT_USERNAME:
            self.client.username_pw_set(
                MQTT_USERNAME,
                MQTT_PASSWORD
            )

        # EMQX Serverless requires TLS on 8883.
        self.client.tls_set(
            cert_reqs=ssl.CERT_REQUIRED,
            tls_version=ssl.PROTOCOL_TLS_CLIENT
        )

        self.client.on_connect = self._on_connect
        self.client.on_disconnect = self._on_disconnect
        self.client.on_message = self._on_message
        self.client.on_subscribe = self._on_subscribe

        self.connected = False
        # Protects active call state shared by MQTT callbacks.
        self.call_lock = threading.RLock()
        self.active_calls = {}
        self.calls = {}
        self.call_timers = {}

    # =========================================================
    # CONNECT
    # =========================================================

    def connect(self):

        print("========================================")
        print("📡 MQTT CONNECTING")
        print("📡 BROKER:", MQTT_BROKER)
        print("📡 PORT:", MQTT_PORT)
        print("📡 CLIENT ID:", MQTT_CLIENT_ID)
        print("========================================")

        try:

            self.client.connect(
                MQTT_BROKER,
                MQTT_PORT,
                keepalive=60
            )

            self.client.loop_start()

        except Exception as e:

            print(
                "❌ MQTT CONNECTION ERROR:",
                type(e).__name__,
                repr(e)
            )

    # =========================================================
    # CONNECT CALLBACK
    # =========================================================
    def _on_connect(
        self,
        client,
        userdata,
        flags,
        reason_code,
        properties=None
    ):
        print("========================================")
        print("📡 MQTT CONNECT RESULT")
        print("📡 REASON CODE:", reason_code)
        print("========================================")

        if reason_code != 0:
            self.connected = False
            print("❌ MQTT CONNECTION REJECTED:", reason_code)
            return

        self.connected = True
        print("✅ MQTT CONNECTED")

        result, mid = client.subscribe("nonimas/in/+", qos=1)

        if result != mqtt.MQTT_ERR_SUCCESS:
            print("❌ MQTT SUBSCRIBE REQUEST FAILED:", result)
            return

        print(
            "📡 MQTT SUBSCRIBE REQUEST SENT:",
            "nonimas/in/+",
            "MID:",
            mid
        )

    def _on_subscribe(
        self,
        client,
        userdata,
        mid,
        reason_code_list,
        properties=None
    ):
        print("📡 MQTT SUBSCRIBE RESULT:", reason_code_list)

        for reason_code in reason_code_list:
            if getattr(reason_code, "is_failure", False):
                print("❌ MQTT SUBSCRIPTION REJECTED:", reason_code)
            else:
                print("✅ MQTT SUBSCRIPTION ACCEPTED:", reason_code)


    def _on_disconnect(
        self,
        client,
        userdata,
        disconnect_flags,
        reason_code,
        properties=None
    ):

        self.connected = False

        print(
            "⚠️ MQTT DISCONNECTED:",
            reason_code
        )

    # =========================================================
    # MESSAGE CALLBACK
    # =========================================================

    def _on_message(
        self,
        client,
        userdata,
        msg
    ):

        print("========================================")
        print("📨 MQTT MESSAGE RECEIVED")
        print("📨 TOPIC:", msg.topic)
        print("📨 PAYLOAD:", msg.payload)
        print("========================================")

        try:

            payload = json.loads(
                msg.payload.decode("utf-8")
            )

        except Exception as e:

            print(
                "❌ MQTT INVALID JSON:",
                repr(e)
            )

            return

        if self.flask_app:

            with self.flask_app.app_context():

                self.handle_event(
                    msg.topic,
                    payload
                )

    # =========================================================
    # EVENT ROUTER
    # =========================================================

    def handle_event(
        self,
        topic,
        payload
    ):

        print(
            "📡 MQTT EVENT:",
            topic,
            payload
        )

        event_type = payload.get("type")

        if not event_type:

            print(
                "⚠️ MQTT EVENT HAS NO TYPE"
            )

            return

        if event_type == "typing":

            self.handle_typing(
                topic,
                payload
            )

        elif event_type == "stop_typing":

            self.handle_stop_typing(
                topic,
                payload
            )
        
        elif event_type == "new_message":

            self.handle_new_message(
                topic,
                payload
            )

        elif event_type == "call_invite":

            self.handle_call_invite(
                topic,
                payload
            )

        elif event_type == "call_ringing":
            self.handle_call_ringing(topic, payload)

        elif event_type == "call_accept":

            self.handle_call_accept(
                topic,
                payload
            )
        elif event_type == self.EVENT_CALL_CONNECTED:
            self.handle_call_connected(topic, payload)

        elif event_type == self.EVENT_CALL_MISSED:
            self.handle_call_missed(topic, payload)

        elif event_type == "call_reject":

            self.handle_call_reject(
                topic,
                payload
            )

        elif event_type == "call_end":

            self.handle_call_end(
                topic,
                payload
            )
        elif event_type in (
            "webrtc_offer",
            "webrtc_answer",
            "webrtc_ice_candidate",
        ):
            self.handle_webrtc_signal(topic, payload)
        elif event_type == "messages_read":

            self.handle_messages_read(
                topic,
                payload
            )

        else:

            print(
                "⚠️ UNKNOWN MQTT EVENT:",
                event_type
            )
    def handle_messages_read(
        self,
        topic,
        payload
    ):

        print(
            "👁️ MQTT MESSAGES READ:",
            payload
        )
    def publish(
        self,
        topic,
        payload,
        qos=1,
        retain=False
    ):

        if not self.connected:

            print(
                "❌ MQTT NOT CONNECTED"
            )

            return False

        try:

            result = self.client.publish(
                topic,
                json.dumps(payload),
                qos=qos,
                retain=retain
            )

            if result.rc != mqtt.MQTT_ERR_SUCCESS:

                print(
                    "❌ MQTT PUBLISH FAILED:",
                    result.rc
                )

                return False

            print(
                "📤 MQTT PUBLISHED:",
                topic,
                payload
            )

            return True

        except Exception as e:

            print(
                "❌ MQTT PUBLISH ERROR:",
                repr(e)
            )

            return False

    # =========================================================
    # USER TOPIC
    # =========================================================

    @staticmethod
    def user_topic(user_id):
        return f"nonimas/users/{user_id}/events"


    @staticmethod
    def inbound_topic(user_id):
        return f"nonimas/in/{user_id}"

    def handle_typing(
        self,
        topic,
        payload
    ):

        sender_id = payload.get("sender_id")
        receiver_id = payload.get("receiver_id")

        if not sender_id or not receiver_id:
            return

        self.publish(
            self.user_topic(receiver_id),
            {
                "type": "typing",
                "user_id": sender_id
            }
        )

    # =========================================================
    # STOP TYPING
    # =========================================================

    def handle_stop_typing(
        self,
        topic,
        payload
    ):

        sender_id = payload.get("sender_id")
        receiver_id = payload.get("receiver_id")

        if not sender_id or not receiver_id:
            return

        self.publish(
            self.user_topic(receiver_id),
            {
                "type": "stop_typing",
                "user_id": sender_id
            }
        )
    def handle_new_message(
        self,
        topic,
        payload
    ):

        print(
            "💬 MQTT NEW MESSAGE:",
            payload
        )
    TERMINAL_CALL_STATUSES = {
        "ended",
        "declined",
        "missed",
        "cancelled",
        "failed",
        "busy",
        "offline",
    }

    def _get_active_call(self, user_a, user_b, call_id=None):
        """Find an active call shared by two participants."""

        try:
            user_a = int(user_a)
            user_b = int(user_b)
        except (TypeError, ValueError):
            return None

        if user_a == user_b:
            return None

        with self.call_lock:
            if call_id:
                call = self.calls.get(str(call_id))

                if not call:
                    return None

                participants = {
                    int(call["caller_id"]),
                    int(call["receiver_id"]),
                }

                if participants == {user_a, user_b}:
                    return call

                return None

            active_call_id = self.active_calls.get(user_a)

            if not active_call_id:
                return None

            call = self.calls.get(active_call_id)

            if not call:
                return None

            participants = {
                int(call["caller_id"]),
                int(call["receiver_id"]),
            }

            if participants != {user_a, user_b}:
                return None

            return call

    def _get_call_session(self, call_id):
        return CallSession.query.filter_by(
            call_id=str(call_id)
        ).with_for_update().first()

    def _update_call_session(self, call_id, **updates):
        """Update a call session within the current Flask app context."""

        session = self._get_call_session(call_id)

        if not session:
            logging.error(
                "Call session not found: %s",
                call_id,
            )
            return None

        for field, value in updates.items():
            if hasattr(session, field):
                setattr(session, field, value)

        db.session.commit()
        return session
    def handle_call_invite(self, topic, payload):
        """Create and route a persisted outgoing call session."""

        try:
            parts = topic.split("/")

            if (
                len(parts) != 3
                or parts[:2] != ["nonimas", "in"]
                or not parts[2].isdigit()
            ):
                logging.warning("Invalid call_invite topic: %s", topic)
                return

            caller_id = int(parts[2])
            receiver_id = int(payload.get("receiver_id"))

        except (TypeError, ValueError):
            logging.warning("Invalid call_invite participant IDs")
            return

        if caller_id == receiver_id:
            logging.warning("Rejected self-call")
            return

        call_type = payload.get("call_type", "voice")

        if call_type not in ("voice", "video"):
            logging.warning("Unsupported call type: %s", call_type)
            return

        caller = db.session.get(User, caller_id)
        receiver = db.session.get(User, receiver_id)

        if not caller or not receiver:
            logging.warning("Call participant does not exist")
            return

        call_id = str(uuid.uuid4())
        now = datetime.utcnow()

        with self.call_lock:
            if caller_id in self.active_calls:
                self.notify_call_user(
                    caller_id,
                    self.EVENT_CALL_BUSY,
                    receiver_id=receiver_id,
                    reason="caller_busy",
                )
                return

            if receiver_id in self.active_calls:
                busy_call_id = str(uuid.uuid4())
                self._create_call_history(
                    {
                        "call_id": busy_call_id,
                        "caller_id": caller_id,
                        "receiver_id": receiver_id,
                    },
                    outcome="busy",
                    duration_seconds=0,
                )
                self.notify_call_user(
                    caller_id,
                    self.EVENT_CALL_RINGING,
                    call_id=busy_call_id,
                    receiver_id=receiver_id,
                )
                busy_timer = threading.Timer(
                    1,
                    self.notify_call_user,
                    args=(caller_id, self.EVENT_CALL_BUSY), 
                    kwargs={
                        "call_id": call_id,
                        "receiver_id": receiver_id,
                        "reason": "receiver_busy",
                    },
                )
                busy_timer.daemon = True
                busy_timer.start()
            call = {
                "call_id": call_id,
                "caller_id": caller_id,
                "receiver_id": receiver_id,
                "call_type": call_type,
                "status": "calling",
                "answered": False,
                "connected_at": None,
            }

            self.calls[call_id] = call
            self.active_calls[caller_id] = call_id
            self.active_calls[receiver_id] = call_id

        try:
            session = CallSession(
                call_id=call_id,
                caller_id=caller_id,
                receiver_id=receiver_id,
                call_type=call_type,
                status="calling",
                created_at=now,
                duration_seconds=0,
                history_created=False,
            )

            db.session.add(session)
            db.session.commit()

        except Exception:
            db.session.rollback()
            logging.exception("Failed to persist call session")

            self._finish_call(call_id)

            self.notify_call_user(
                caller_id,
                self.EVENT_CALL_OFFLINE,
                receiver_id=receiver_id,
            )
            return

        published = self.notify_call_user(
            receiver_id,
            self.EVENT_CALL_INVITE,
            call_id=call_id,
            caller_id=caller_id,
            caller_name=getattr(caller, "full_name", None)
            or "Nonimas user",
            receiver_id=receiver_id,
            call_type=call_type,
        )

        if not published:
            self._finalize_call(
                call_id,
                outcome="offline",
                end_reason="offline",
            )

            self.notify_call_user(
                caller_id,
                self.EVENT_CALL_OFFLINE,
                call_id=call_id,
                receiver_id=receiver_id,
            )
            return

        try:
            send_incoming_call_notification(
                receiver_id=receiver_id,
                caller_id=caller_id,
                caller_name=getattr(caller, "full_name", None)
                or "Nonimas user",
                call_type=call_type,
            )
        except Exception:
            logging.exception("Failed to send incoming-call notification")

        self._schedule_call_timeout(call_id)

        logging.info(
            "Call invitation created: call_id=%s caller=%s receiver=%s",
            call_id,
            caller_id,
            receiver_id,
        )
    def _create_call_history(self, call, outcome, duration_seconds=0):
   
        call_id = str(call["call_id"])
        caller_id = int(call["caller_id"])
        receiver_id = int(call["receiver_id"])

        duration_seconds = max(0, int(duration_seconds or 0))

        # Define which records each participant should receive.
        if outcome == "declined":
            entries = [
                (caller_id, receiver_id, "📞 CALL DECLINED"),
                (receiver_id, caller_id, "📞 YOU DECLINED THE CALL"),
            ]

        elif outcome in ("missed", "offline", "cancelled"):
            entries = [
                (caller_id, receiver_id, "📞 NO ANSWER"),
                (receiver_id, caller_id, "📞 MISSED CALL"),
            ]

        elif outcome == "busy":
            entries = [
                (caller_id, receiver_id, "📞 ENDED, BUSY"),
                (receiver_id, caller_id, "📞 CALL BUSY"),
            ]

        elif outcome == "ended":
            duration_text = f"{duration_seconds // 60:02d}:{duration_seconds % 60:02d}"
            entries = [
                (
                    caller_id,
                    receiver_id,
                    f"📞 CALL LASTED {duration_text}",
                ),
                (
                    receiver_id,
                    caller_id,
                    f"📞 CALL LASTED {duration_text}",
                ),
            ]

        else:
            logging.warning(
                "Unknown call-history outcome '%s' for call %s",
                outcome,
                call_id,
            )
            return False

        messages_to_publish = []

        try:
            for sender_id, recipient_id, message_text in entries:
                existing = ChatMessage.query.filter_by(
                    call_id=call_id,
                    sender_id=sender_id,
                ).first()

                if existing:
                    continue

                message = ChatMessage(
                    sender_id=sender_id,
                    receiver_id=recipient_id,
                    message=message_text,
                    media_url=None,
                    media_type=None,
                    message_type="call",
                    call_id=call_id,
                    call_duration=duration_seconds,
                    is_read=False,
                    created_at=datetime.utcnow(),
                )

                db.session.add(message)
                db.session.flush()

                messages_to_publish.append(message)

            db.session.commit()

        except Exception:
            db.session.rollback()

            logging.exception(
                "Failed to create call history for %s",
                call_id,
            )

            return False

        for message in messages_to_publish:
            try:
                self._publish_call_history(message)
            except Exception:
                logging.exception(
                    "Failed to publish call-history message %s",
                    message.id,
                )

        return True
        
    def _publish_call_history(self, message):
        """Send each call-history entry only to the user it describes."""

        payload = {
            "type": "new_message",
            "message_id": message.id,
            "sender_id": message.sender_id,
            "receiver_id": message.receiver_id,
            "message": message.message,
           "media_url": message.media_url,
            "media_type": message.media_type,
            "message_type": message.message_type,
            "call_id": message.call_id,
            "call_duration": message.call_duration,
            "created_at": (
                message.created_at.isoformat()
                if message.created_at
                else datetime.utcnow().isoformat()
            ),
            "is_read": message.is_read,
        }

        self.notify_call_user(
            message.sender_id,
            "new_message",
            **{
                key: value
                for key, value in payload.items()
                if key != "type"
            },
        )


    def _finish_call(self, call_id):
        """Release participants and cancel a call's timeout timer."""

        call_id = str(call_id)

        with self.call_lock:
            call = self.calls.pop(call_id, None)

            timer = self.call_timers.pop(call_id, None)

            if timer:
                timer.cancel()

            if not call:
                return None

            caller_id = int(call["caller_id"])
            receiver_id = int(call["receiver_id"])

            if self.active_calls.get(caller_id) == call_id:
                self.active_calls.pop(caller_id, None)

            if self.active_calls.get(receiver_id) == call_id:
                self.active_calls.pop(receiver_id, None)

            return call
    def handle_call_ringing(self, topic, payload):
        """Record that the receiver's device received the call."""

        try:
            parts = topic.split("/")

            if (
                len(parts) != 3
                or parts[:2] != ["nonimas", "in"]
                or not parts[2].isdigit()
            ):
                return

            receiver_id = int(parts[2])
            call_id = str(payload.get("call_id", "")).strip()

            if not call_id:
                logging.warning("call_ringing missing call_id")
                return

        except (TypeError, ValueError):
            return

        with self.call_lock:
            call = self.calls.get(call_id)

            if not call:
                logging.warning("Unknown call_ringing call_id=%s", call_id)
                return

            if int(call["receiver_id"]) != receiver_id:
                logging.warning("call_ringing receiver mismatch")
                return

            if call["status"] != "calling":
                # Ignore duplicate ringing events.
                if call["status"] == "ringing":
                    return
                return

            call["status"] = "ringing"
            caller_id = int(call["caller_id"])

        try:
            session = self._get_call_session(call_id)

            if session and session.status == "calling":
                session.status = "ringing"
                session.ringing_at = datetime.utcnow()
                db.session.commit()

        except Exception:
            db.session.rollback()
            logging.exception("Failed to update ringing state")
            return

        self.notify_call_user(
            caller_id,
            self.EVENT_CALL_RINGING,
            call_id=call_id,
            receiver_id=receiver_id,
        )
    def handle_webrtc_signal(self, topic, payload):
        """Forward WebRTC signaling to the intended participant."""

        event_type = payload.get("type")

        # Get sender ID from the inbound MQTT topic.
        try:
            topic_parts = topic.split("/")
            if len(topic_parts) != 3 or topic_parts[0:2] != ["nonimas", "in"]:
                logging.warning("Rejected WebRTC signal: invalid topic")
                return

            sender_id = int(topic_parts[2])
            receiver_id = int(payload.get("receiver_id"))

        except (TypeError, ValueError):
            logging.warning("Rejected WebRTC signal: invalid participant IDs")
            return

        if sender_id == receiver_id:
            logging.warning("Rejected WebRTC signal: sender and receiver are identical")
            return

        # Only permit supported WebRTC signaling events.
        if event_type not in (
            "webrtc_offer",
            "webrtc_answer",
            "webrtc_ice_candidate",
        ):
            logging.warning("Rejected unknown WebRTC event: %s", event_type)
            return

        # Validate the required payload for each event.
        if event_type in ("webrtc_offer", "webrtc_answer"):
            if not isinstance(payload.get("sdp"), str) or not payload["sdp"]:
                logging.warning("Rejected WebRTC signal: missing SDP")
                return

        elif event_type == "webrtc_ice_candidate":
            if not isinstance(payload.get("candidate"), str):
                logging.warning("Rejected WebRTC signal: missing ICE candidate")
                return

        forwarded_payload = dict(payload)
        forwarded_payload["sender_id"] = sender_id

        self.publish(
            self.user_topic(receiver_id),
            forwarded_payload,
            qos=1,
        )
    def handle_call_accept(self, topic, payload):
        """Validate receiver acceptance and notify the caller."""

        try:
            parts = topic.split("/")

            if (
                len(parts) != 3
                or parts[:2] != ["nonimas", "in"]
                or not parts[2].isdigit()
            ):
                logging.warning("Invalid call_accept topic")
                return

            receiver_id = int(parts[2])
            caller_id = int(payload.get("caller_id"))
            call_id = payload.get("call_id")

        except (TypeError, ValueError):
            logging.warning("Invalid call_accept payload")
            return

        if receiver_id == caller_id:
            return

        # Compatibility: older Android versions may omit call_id.
        call = self._get_active_call(
            caller_id,
            receiver_id,
            call_id=call_id,
        )

        if not call:
            logging.warning(
                "Rejected call_accept: no matching active call"
            )
            return

        call_id = str(call["call_id"])

        with self.call_lock:
            if call["status"] not in ("calling", "ringing"):
                logging.warning(
                    "Rejected call_accept for call in state %s",
                    call["status"],
                )
                return

            call["status"] = "accepted"
            call["answered"] = True

            timer = self.call_timers.pop(call_id, None)
            if timer:
                timer.cancel()

        try:
            session = self._get_call_session(call_id)

            if not session:
                logging.error(
                    "CallSession missing during acceptance: %s",
                    call_id,
                )
                return

            if session.status not in ("calling", "ringing"):
                return

            session.status = "accepted"
            session.accepted_at = datetime.utcnow()
            db.session.commit()

        except Exception:
            db.session.rollback()
            logging.exception("Failed to persist call acceptance")
            return

        self.notify_call_user(
            caller_id,
            self.EVENT_CALL_ACCEPT,
            call_id=call_id,
            caller_id=caller_id,
            receiver_id=receiver_id,
        )

        logging.info("Call accepted: %s", call_id)
    def handle_call_connected(self, topic, payload):
        """
        Record the time WebRTC actually establishes a connection.

        Android must send this event when its PeerConnection reaches
        the CONNECTED state.
        """

        try:
            parts = topic.split("/")

            if (
                len(parts) != 3
                or parts[:2] != ["nonimas", "in"]
                or not parts[2].isdigit()
            ):
                return

            sender_id = int(parts[2])
            receiver_id = int(payload.get("receiver_id"))
            call_id = str(payload.get("call_id", "")).strip()

        except (TypeError, ValueError):
            logging.warning("Invalid call_connected payload")
            return

        if sender_id == receiver_id or not call_id:
            logging.warning("Rejected call_connected: invalid participants")
            return

        call = self._get_active_call(
            sender_id,
            receiver_id,
            call_id=call_id,
        )

        if not call:
            logging.warning(
                "Rejected call_connected: no matching active call"
            )
            return

        with self.call_lock:
            if call["status"] not in ("accepted", "connected"):
                logging.warning(
                    "Rejected call_connected in state %s",
                    call["status"],
                )
                return

            if call["status"] == "connected":
                # Duplicate WebRTC callbacks must not reset duration.
                return

            call["status"] = "connected"
            call["connected_at"] = datetime.utcnow()

        try:
            session = self._get_call_session(call_id)

            if not session:
                return

            if session.status != "accepted":
                return

            session.status = "connected"
            session.connected_at = call["connected_at"]
            db.session.commit()

        except Exception:
            db.session.rollback()
            logging.exception("Failed to persist connected state")
            return

        # Inform both participants of the authoritative connection state.
        for user_id in (sender_id, receiver_id):
            self.notify_call_user(
                user_id,
                self.EVENT_CALL_CONNECTED,
                call_id=call_id,
                caller_id=int(call["caller_id"]),
                receiver_id=int(call["receiver_id"]),
                connected_at=call["connected_at"].isoformat(),
            )

        logging.info("Call connected: %s", call_id)
    def handle_call_reject(self, topic, payload):
        """Handle an explicit rejection from the receiver."""

        try:
            parts = topic.split("/")

            if (
                len(parts) != 3
                or parts[:2] != ["nonimas", "in"]
                or not parts[2].isdigit()
            ):
                return

            receiver_id = int(parts[2])
            caller_id = int(payload.get("caller_id"))
            payload_receiver_id = payload.get("receiver_id")
            call_id = payload.get("call_id")

            if (
                payload_receiver_id is not None
                and int(payload_receiver_id) != receiver_id
            ):
                return

        except (TypeError, ValueError):
            logging.warning("Invalid call_reject payload")
            return

        if receiver_id == caller_id:
            return

        call = self._get_active_call(
            caller_id,
            receiver_id,
            call_id=call_id,
        )

        if not call:
            logging.warning(
                "Rejected call_reject: no matching active call"
            )
            return

        call_id = str(call["call_id"])

        if call["status"] not in ("calling", "ringing"):
            logging.warning(
                "Rejected call_reject in state %s",
                call["status"],
            )
            return

        finalized = self._finalize_call(
            call_id,
            outcome="declined",
            end_reason="declined",
        )

        if not finalized:
            return

        self.notify_call_user(
            caller_id,
            self.EVENT_CALL_REJECT,
            call_id=call_id,
            caller_id=caller_id,
            receiver_id=receiver_id,
        )

        logging.info("Call rejected: %s", call_id)
    def handle_call_end(self, topic, payload):
        """End a call and create the correct history outcome."""

        try:
            parts = topic.split("/")

            if (
                len(parts) != 3
                or parts[:2] != ["nonimas", "in"]
                or not parts[2].isdigit()
            ):
                return

            sender_id = int(parts[2])
            user_id = int(payload.get("user_id", sender_id))
            other_user_id = int(payload.get("other_user_id"))
            call_id = payload.get("call_id")

        except (TypeError, ValueError):
            logging.warning("Invalid call_end payload")
            return

        # Do not allow one user to end another user's call by
        # supplying a different user_id in the payload.
        if sender_id != user_id or sender_id == other_user_id:
            logging.warning("Rejected call_end: participant mismatch")
            return

        call = self._get_active_call(
            sender_id,
            other_user_id,
            call_id=call_id,
        )

        if not call:
            logging.warning(
                "Rejected call_end: no matching active call"
            )
            return

        call_id = str(call["call_id"])
        caller_id = int(call["caller_id"])
        receiver_id = int(call["receiver_id"])

        if call["status"] in self.TERMINAL_CALL_STATUSES:
            return

        if call["status"] in ("accepted", "connected"):
            outcome = "ended"
            end_reason = "completed"

        elif call["status"] in ("calling", "ringing"):
            # The call ended before the receiver accepted.
            outcome = "cancelled"
            end_reason = "cancelled"

        else:
            # Accepted but never reached WebRTC CONNECTED.
            outcome = "cancelled"
            end_reason = "connection_failed"

        finalized = self._finalize_call(
            call_id,
            outcome=outcome,
            end_reason=end_reason,
        )

        if not finalized:
            return

        self.notify_call_user(
            other_user_id,
            self.EVENT_CALL_END,
            call_id=call_id,
            other_user_id=other_user_id,
        )

        logging.info(
            "Call ended: %s outcome=%s",
            call_id,
            outcome,
        )
    def handle_call_missed(self, topic, payload):
        """
        Handle a receiver-side missed-call event.

        This is for an incoming call that timed out without acceptance,
        not an explicit rejection.
        """

        try:
            parts = topic.split("/")

            if (
                len(parts) != 3
                or parts[:2] != ["nonimas", "in"]
                or not parts[2].isdigit()
            ):
                return

            receiver_id = int(parts[2])
            caller_id = int(payload.get("caller_id"))
            call_id = payload.get("call_id")

        except (TypeError, ValueError):
            logging.warning("Invalid call_missed payload")
            return

        if caller_id == receiver_id:
            return

        call = self._get_active_call(
            caller_id,
            receiver_id,
            call_id=call_id,
        )

        if not call:
            logging.warning(
                "Ignored call_missed: no matching active call"
            )
            return

        call_id = str(call["call_id"])
        session = self._get_call_session(call_id)
        if not session:
            return
        if session.status not in ("calling", "ringing"):
            logging.info(
                "Ignoring missed event for call %s in database state %s",
                call_id,
                session.status,
            )
            return

        if call["status"] not in ("calling", "ringing"):
            return

        finalized = self._finalize_call(
            call_id,
            outcome="missed",
            end_reason="no_answer",
        )

        if not finalized:
            return

        self.notify_call_user(
            caller_id,
            self.EVENT_CALL_MISSED,
            call_id=call_id,
            caller_id=caller_id,
            receiver_id=receiver_id,
        )

        logging.info("Missed call recorded: %s", call_id)
    def notify_call_user(self, user_id, event_type, **data):
        payload = {
            "type": event_type,
            **data,
        }

        return self.publish(
            self.user_topic(user_id),
            payload,
            qos=1,
        )
    def _schedule_call_timeout(self, call_id, timeout_seconds=45):
        """Automatically finalize a call that was never answered."""

        call_id = str(call_id)

        timer = threading.Timer(
            timeout_seconds,
            self._call_timeout_fired,
            args=(call_id,),
        )

        timer.daemon = True

        with self.call_lock:
            old_timer = self.call_timers.pop(call_id, None)

            if old_timer:
                old_timer.cancel()

            self.call_timers[call_id] = timer

        timer.start()

    def _call_timeout_fired(self, call_id):
        """Timeout callback; enter Flask context before using SQLAlchemy."""

        if not self.flask_app:
            return

        with self.flask_app.app_context():
            try:
                session = self._get_call_session(call_id)

                if not session:
                    return

                # A call that was accepted or connected must not be
                # treated as an unanswered call.
                if session.status not in ("calling", "ringing"):
                    return
                finalized = self._finalize_call(
                    call_id,
                    outcome="missed",
                    end_reason="no_answer",
                )
                if finalized:
                    self.notify_call_user(
                        session.caller_id,
                        self.EVENT_CALL_MISSED,
                        call_id=call_id,
                        caller_id=session.caller_id,
                        receiver_id=session.receiver_id,
                    )

            except Exception:
                db.session.rollback()
                logging.exception("Call timeout processing failed")

    def _finalize_call(
        self,
        call_id,
        outcome,
        end_reason,
        ended_at=None,
    ):
        call_id = str(call_id)
        ended_at = ended_at or datetime.utcnow()

        if not self.flask_app:
            logging.error(
                "Cannot finalize call without Flask app: %s",
                call_id,
            )
            return False

        with self.flask_app.app_context():
            try:
                session = (
                    CallSession.query
                    .filter_by(call_id=call_id)
                    .with_for_update()
                    .first()
                )

                if not session:
                    logging.warning(
                        "Cannot finalize missing call session: %s",
                        call_id,
                    )
                    self._finish_call(call_id)
                    return False

                if session.status in self.TERMINAL_CALL_STATUSES:
                    self._finish_call(call_id)
                    return False

                if outcome not in self.TERMINAL_CALL_STATUSES:
                    logging.error(
                        "Invalid terminal outcome '%s' for call %s",
                        outcome,
                        call_id,
                    )
                    return False

                connected_at = session.connected_at

                duration = (
                    max(
                        0,
                        int((ended_at - connected_at).total_seconds()),
                    )
                    if connected_at
                    else 0
                )

                call = {
                    "call_id": session.call_id,
                    "caller_id": session.caller_id,
                    "receiver_id": session.receiver_id,
                    "call_type": session.call_type,
                }
                session.status = outcome
                session.end_reason = end_reason
                session.ended_at = ended_at
                session.duration_seconds = duration

                db.session.commit()

            except Exception:
                db.session.rollback()
                logging.exception(
                    "Failed to finalize call %s",
                    call_id,
                )
                return False

            history_saved = self._create_call_history(
                call,
                outcome=outcome,
                duration_seconds=duration,
            )

            if history_saved:
                try:
                    session = CallSession.query.filter_by(
                        call_id=call_id
                    ).first()

                    if session and not session.history_created:
                        session.history_created = True
                        db.session.commit()

                except Exception:
                    db.session.rollback()
                    logging.exception(
                        "Failed to update history_created for call %s",
                        call_id,
                    )

            else:
                logging.error(
                    "Call %s finalized, but call history was not saved. "
                    "history_created remains false for recovery.",
                    call_id,
                )

            self._finish_call(call_id)

            logging.info(
                "Call finalized: id=%s outcome=%s duration=%s history_saved=%s",
                call_id,
                outcome,
                duration,
                history_saved,
            )

            return True
mqtt_service = MQTTService()