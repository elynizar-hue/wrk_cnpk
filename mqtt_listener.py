import json
import os
from datetime import datetime
import traceback

import paho.mqtt.client as mqtt

from db import get_connection, init_db, execute_write

LOG_FILE = os.path.join(os.path.dirname(__file__), "mqtt_listener.log")


def _log(line: str):
    try:
        ts = datetime.utcnow().isoformat()
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(f"{ts} - {line}\n")
    except Exception:
        # best-effort logging, never fail the listener because logging broke
        pass

MQTT_BROKER = os.getenv("MQTT_BROKER", "localhost")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))
MQTT_PREFIX = os.getenv("MQTT_PREFIX", "canpack").strip().strip("/")


def _topic(*parts):
    return "/".join(part.strip("/") for part in parts if part and str(part).strip("/"))


def _build_armoires(prefix):
    return {
        "Body Maker": (
            [
                _topic(prefix, "bodymaker/fuite"),
                _topic(prefix, "bodymaker/dashboard"),
                _topic(prefix, "body_maker/fuite"),
                _topic(prefix, "body_maker/dashboard"),
            ],
            60.0,
            150.0,
        ),
        "Zone Laveuse": (
            [
                _topic(prefix, "laveuse/fuite"),
                _topic(prefix, "laveuse/dashboard"),
                _topic(prefix, "zone_laveuse/fuite"),
                _topic(prefix, "zone_laveuse/dashboard"),
            ],
            50.0,
            130.0,
        ),
        "LSM (Vernissage)": (
            [
                _topic(prefix, "lsm/fuite"),
                _topic(prefix, "lsm/dashboard"),
                _topic(prefix, "lsm_vernis/fuite"),
                _topic(prefix, "lsm_vernis/dashboard"),
            ],
            60.0,
            150.0,
        ),
    }


ARMOIRES = _build_armoires(MQTT_PREFIX)

_TOPIC_TO_ARMOIRE = {}
for armoire, (topics, *_rest) in ARMOIRES.items():
    for topic in topics:
        _TOPIC_TO_ARMOIRE[topic] = armoire


def _status_from_values(courant_mA, moyenne, seuil_precoce, seuil_critique):
    if moyenne >= seuil_critique or courant_mA >= seuil_critique:
        return "CRITIQUE"
    if moyenne >= seuil_precoce or courant_mA >= seuil_precoce:
        return "PRECOCE"
    return "normal"


def _parse_payload(payload):
    if payload is None:
        return None

    if isinstance(payload, (int, float)):
        return {"courant_mA": float(payload), "moyenne": 0.0, "statut": "normal"}

    if isinstance(payload, dict):
        return {
            "courant_mA": float(payload.get("courant_mA", payload.get("courant", payload.get("value", 0)))),
            "moyenne": float(payload.get("moyenne", payload.get("avg", payload.get("average", payload.get("moyenne_glissante", 0))))),
            "statut": payload.get("statut", payload.get("status", "normal")),
            "prediction": payload.get("prediction"),
            "couleur": payload.get("couleur", payload.get("color")),
            "horodatage": payload.get("horodatage", payload.get("timestamp")),
        }

    if isinstance(payload, (bytes, bytearray)):
        payload = payload.decode("utf-8", errors="ignore")

    if isinstance(payload, str):
        text = payload.strip()
        if not text:
            return None

        if text.lstrip("+-").replace(".", "", 1).isdigit():
            return {"courant_mA": float(text), "moyenne": 0.0, "statut": "normal"}

        try:
            data = json.loads(text)
            if isinstance(data, dict):
                return {
                    "courant_mA": float(data.get("courant_mA", data.get("courant", data.get("value", 0)))),
                    "moyenne": float(data.get("moyenne", data.get("avg", data.get("average", data.get("moyenne_glissante", 0))))),
                    "statut": data.get("statut", data.get("status", "normal")),
                    "prediction": data.get("prediction"),
                    "couleur": data.get("couleur", data.get("color")),
                    "horodatage": data.get("horodatage", data.get("timestamp")),
                }
            if isinstance(data, (int, float)):
                return {"courant_mA": float(data), "moyenne": 0.0, "statut": "normal"}
        except Exception:
            parts = text.replace("\n", "").split(",")
            if len(parts) >= 2:
                try:
                    return {
                        "courant_mA": float(parts[0].strip()),
                        "moyenne": float(parts[1].strip()),
                        "statut": parts[2].strip() if len(parts) >= 3 else "normal",
                    }
                except ValueError:
                    return None

    return None


def _on_message(client, userdata, msg):
    try:
        _log(f"Received MQTT topic={msg.topic} payload={repr(msg.payload)[:200]}")
    except Exception:
        pass

    armoire = _TOPIC_TO_ARMOIRE.get(msg.topic)
    if armoire is None:
        return

    parsed = _parse_payload(msg.payload)
    if parsed is None:
        return

    topics, seuil_precoce, seuil_critique = ARMOIRES[armoire]
    statut = _status_from_values(parsed["courant_mA"], parsed["moyenne"], seuil_precoce, seuil_critique)
    horodatage = parsed.get("horodatage") or datetime.utcnow().isoformat()

    # Use serialized write helper to reduce SQLITE_BUSY errors when multiple
    # threads read and write concurrently (Streamlit + MQTT background thread).
    try:
        execute_write(
            "INSERT INTO mesures (armoire, courant_mA, moyenne, statut, horodatage) VALUES (?, ?, ?, ?, ?)",
            (armoire, parsed["courant_mA"], parsed["moyenne"], statut, horodatage),
        )
        _log(f"Inserted mesure: {armoire} {parsed.get('courant_mA')} mA statut={statut} horodatage={horodatage}")
        if statut in {"PRECOCE", "CRITIQUE"}:
            execute_write(
                "INSERT INTO alertes (horodatage, armoire, niveau, valeur_mA) VALUES (?, ?, ?, ?)",
                (horodatage, armoire, statut, parsed["courant_mA"]),
            )
            _log(f"Inserted alerte: {armoire} niveau={statut} valeur={parsed.get('courant_mA')}")
    except Exception:
        _log("execute_write failed, falling back to raw connection:\n" + traceback.format_exc())
        # If execute_write fails unexpectedly, fall back to a raw connection
        conn = get_connection()
        try:
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO mesures (armoire, courant_mA, moyenne, statut, horodatage) VALUES (?, ?, ?, ?, ?)",
                (armoire, parsed["courant_mA"], parsed["moyenne"], statut, horodatage),
            )
            if statut in {"PRECOCE", "CRITIQUE"}:
                cur.execute(
                    "INSERT INTO alertes (horodatage, armoire, niveau, valeur_mA) VALUES (?, ?, ?, ?)",
                    (horodatage, armoire, statut, parsed["courant_mA"]),
                )
            conn.commit()
            _log(f"Fallback insert succeeded for {armoire}")
        finally:
            conn.close()


def demarrer_listener():
    init_db(seed_demo_data=False)

    client = mqtt.Client()
    client.on_message = _on_message
    def _on_connect(client, userdata, flags, rc):
        try:
            _log(f"MQTT connected rc={rc}")
        except Exception:
            pass

    client.on_connect = _on_connect

    try:
        client.connect(MQTT_BROKER, MQTT_PORT, keepalive=60)
        _log(f"Attempting connect to MQTT broker {MQTT_BROKER}:{MQTT_PORT}")
    except Exception:
        _log("MQTT connect failed:\n" + traceback.format_exc())
        return None

    dashboard_topics = [topic for topic in _TOPIC_TO_ARMOIRE.keys() if topic.endswith("/dashboard")]
    for topic in dashboard_topics:
        try:
            client.subscribe(topic)
            _log(f"Subscribed to {topic}")
        except Exception:
            _log(f"Failed to subscribe to {topic}:\n" + traceback.format_exc())

    client.loop_start()
    return client


if __name__ == "__main__":
    print("MQTT listener ready. Set MQTT_BROKER and MQTT_PORT to connect to your broker.")
