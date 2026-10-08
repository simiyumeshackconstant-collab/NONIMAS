import os
import json
import ssl
import threading
from flask import Flask
from models import User
from helpers import send_incoming_call_notification

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

        self.connected = False

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

        if reason_code == 0:

            self.connected = True

            print("✅ MQTT CONNECTED")

            # Backend listens for realtime events
            # published by Android clients.
            client.subscribe(
                "nonimas/users/+/events",
                qos=1
            )

            print(
                "📡 MQTT SUBSCRIBED:",
                "nonimas/users/+/events"
            )

        else:

            self.connected = False

            print(
                "❌ MQTT CONNECTION REJECTED:",
                reason_code
            )

    # =========================================================
    # DISCONNECT CALLBACK
    # =========================================================

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

        elif event_type == "call_invite":

            self.handle_call_invite(
                topic,
                payload
            )

        elif event_type == "call_accept":

            self.handle_call_accept(
                topic,
                payload
            )

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

        else:

            print(
                "⚠️ UNKNOWN MQTT EVENT:",
                event_type
            )

    # =========================================================
    # PUBLISH
    # =========================================================

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

    # =========================================================
    # TYPING
    # =========================================================

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

    # =========================================================
    # CALL INVITE
    # =========================================================

    def handle_call_invite(
        self,
        topic,
        payload
    ):

        caller_id = payload.get("caller_id")
        receiver_id = payload.get("receiver_id")
        call_type = payload.get(
            "call_type",
            "voice"
        )

        if not caller_id or not receiver_id:
            return


        caller = User.query.get(caller_id)
        receiver = User.query.get(receiver_id)

        if not caller or not receiver:
            return

        call_payload = {
            "type": "call_invite",
            "caller_id": caller_id,
            "caller_name": caller.full_name,
            "receiver_id": receiver_id,
            "call_type": call_type
        }

        self.publish(
            self.user_topic(receiver_id),
            call_payload
        )

        # Keep FCM for background incoming calls.
        try:

        

            send_incoming_call_notification(
                receiver_id=receiver_id,
                caller_id=caller_id,
                caller_name=caller.full_name,
                call_type=call_type
            )

        except Exception as e:

            print(
                "⚠️ FCM CALL NOTIFICATION ERROR:",
                repr(e)
            )

    # =========================================================
    # CALL ACCEPT
    # =========================================================

    def handle_call_accept(
        self,
        topic,
        payload
    ):

        caller_id = payload.get("caller_id")
        receiver_id = payload.get("receiver_id")

        if not caller_id or not receiver_id:
            return

        self.publish(
            self.user_topic(caller_id),
            {
                "type": "call_accept",
                "receiver_id": receiver_id
            }
        )

    # =========================================================
    # CALL REJECT
    # =========================================================

    def handle_call_reject(
        self,
        topic,
        payload
    ):

        caller_id = payload.get("caller_id")
        receiver_id = payload.get("receiver_id")

        if not caller_id or not receiver_id:
            return

        self.publish(
            self.user_topic(caller_id),
            {
                "type": "call_reject",
                "receiver_id": receiver_id
            }
        )

    # =========================================================
    # CALL END
    # =========================================================

    def handle_call_end(
        self,
        topic,
        payload
    ):

        user_id = payload.get("user_id")
        other_user_id = payload.get(
            "other_user_id"
        )

        if not user_id or not other_user_id:
            return

        self.publish(
            self.user_topic(other_user_id),
            {
                "type": "call_end",
                "user_id": user_id
            }
        )


mqtt_service = MQTTService()