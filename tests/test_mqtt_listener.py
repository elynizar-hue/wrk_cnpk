import unittest

from mqtt_listener import _TOPIC_TO_ARMOIRE, _parse_payload


class MqttListenerTests(unittest.TestCase):
    def test_node_red_topics_are_mapped(self):
        self.assertEqual(_TOPIC_TO_ARMOIRE["canpack/bodymaker/fuite"], "Body Maker")
        self.assertEqual(_TOPIC_TO_ARMOIRE["canpack/laveuse/fuite"], "Zone Laveuse")
        self.assertEqual(_TOPIC_TO_ARMOIRE["canpack/lsm/fuite"], "LSM (Vernissage)")

    def test_payload_parsing_accepts_node_red_shape(self):
        parsed = _parse_payload('{"courant_mA": 12.3}')
        self.assertEqual(parsed["courant_mA"], 12.3)
        self.assertEqual(parsed["moyenne"], 0.0)


if __name__ == "__main__":
    unittest.main()
