import json
import os
from datetime import datetime

import paho.mqtt.client as mqtt

from db import get_connection, init_db

MQTT_BROKER = os.getenv("MQTT_BROKER", "localhost")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))
MQTT_PREFIX = os.getenv("MQTT_PREFIX", "canpack")

ARMOIRES = {
    "Body Maker": (f"{MQTT_PREFIX}/body_maker", 15.0, 30.0),
    "Zone Laveuse": (f"{MQTT_PREFIX}/zone_laveuse", 18.0, 28.0),
    "LSM (Vernissage)": (f"{MQTT_PREFIX}/lsm_vernis", 20.0, 32.0),
}

_TOPIC_TO_ARMOIRE = {topic: nom for nom, (topic, *_rest) in ARMOIRES.items()}


def _status_from_values(courant_mA, moyenne, seuil_precoce, seuil_critique):
    if moyenne >= seuil_critique or courant_mA >= seuil_critique:
        return "CRITIQUE"
    if moyenne >= seuil_precoce or courant_mA >= seuil_precoce:
        return "PRECOCE"
    return "normal"


def _parse_payload(payload):
    if not payload:
        return None

    try:
        data = json.loads(payload)
        return {
            "courant_mA": float(data.get("courant_mA", data.get("courant", data.get("value", 0)))),
            "moyenne": float(data.get("moyenne", data.get("avg", data.get("average", 0)))),
            "statut": data.get("statut", data.get("status", "normal")),
        }
    except Exception:
        parts = payload.replace("\n", "").split(",")
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
    armoire = _TOPIC_TO_ARMOIRE.get(msg.topic)
    if armoire is None:
        return

    parsed = _parse_payload(msg.payload.decode("utf-8", errors="ignore"))
    if parsed is None:
        return

    topic, seuil_precoce, seuil_critique = ARMOIRES[armoire]
    statut = _status_from_values(parsed["courant_mA"], parsed["moyenne"], seuil_precoce, seuil_critique)
    horodatage = datetime.utcnow().isoformat()

    conn = get_connection()
    with conn:
        conn.execute(
            "INSERT INTO mesures (armoire, courant_mA, moyenne, statut, horodatage) VALUES (?, ?, ?, ?, ?)",
            (armoire, parsed["courant_mA"], parsed["moyenne"], statut, horodatage),
        )
        if statut in {"PRECOCE", "CRITIQUE"}:
            conn.execute(
                "INSERT INTO alertes (horodatage, armoire, niveau, valeur_mA) VALUES (?, ?, ?, ?)",
                (horodatage, armoire, statut, parsed["courant_mA"]),
            )


def demarrer_listener():
    init_db(seed_demo_data=False)

    client = mqtt.Client()
    client.on_message = _on_message

    try:
        client.connect(MQTT_BROKER, MQTT_PORT, keepalive=60)
    except Exception:
        return None

    for topic in _TOPIC_TO_ARMOIRE.keys():
        client.subscribe(topic)

    client.loop_start()
    return client


if __name__ == "__main__":
    print("MQTT listener stub loaded. Set MQTT_BROKER and MQTT_PORT to connect.")
