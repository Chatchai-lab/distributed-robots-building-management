import time
import json
import requests
import pytest
import paho.mqtt.client as mqtt

# basic config
COORDINATOR = "http://localhost:8080"
BROKER_HOST = "localhost"
BROKER_PORT = 1883

# helpers

# get current state from coordinator
def get_map():
    r = requests.get(f"{COORDINATOR}/map", timeout=3)
    r.raise_for_status()
    return r.json()


# create detector robot via REST
def register_detector():
    r = requests.post(f"{COORDINATOR}/robot", timeout=3)
    r.raise_for_status()
    data = r.json()
    return data["id"], data["position"]["x"], data["position"]["y"]


# send MQTT status update
def publish_status(robot_id, x, y, status="ACTIVE"):
    payload = {
        "id": robot_id,
        "x": x,
        "y": y,
        "role": "detector",
        "status": status
    }

    client = mqtt.Client()
    client.connect(BROKER_HOST, BROKER_PORT, 60)
    client.loop_start()
    client.publish(f"robot/status/{robot_id}", json.dumps(payload))
    time.sleep(0.1)
    client.loop_stop()
    client.disconnect()


# find robot entry in /map response
def find_robot(map_json, robot_id):
    for r in map_json.get("robots", []):
        if r["id"] == robot_id:
            return r
    return None


# functional test
# MQTT status updates must appear in GET /map
def test_mqtt_status_updates_map():
    print(f"\ntest_mqtt_status_updates_map...")
    robot_id, x, y = register_detector()
    print(f"[TEST] Registered detector id={robot_id} at ({x},{y})")

    # move robot via MQTT
    publish_status(robot_id, x + 1, y)
    print(f"[TEST] Published MQTT move to ({x+1},{y})")

    time.sleep(1)
    data = get_map()
    robot = find_robot(data, robot_id)

    # check if robot exists and has new position
    print(f"[TEST] /map robot={robot}")
    assert robot is not None
    assert robot["x"] == x + 1
    assert robot["y"] == y


# non-functional test
# robot stops sending MQTT messages (failure case)
# coordinator must stay consistent
def test_robot_failure_no_mqtt_messages():
    print(f"\ntest_robot_failure_no_mqtt_messages...")
    robot_id, x, y = register_detector()
    print(f"[TEST] Registered detector id={robot_id} at ({x},{y})")

    # init status messages
    publish_status(robot_id, x, y)
    publish_status(robot_id, x, y + 1)
    print(f"[TEST] Sent last MQTT status at ({x},{y+1})")

    # simulate failure
    print("[TEST] Simulating failure: no more MQTT messages now")
    time.sleep(2)

    data = get_map()
    robot = find_robot(data, robot_id)
    print(f"[TEST] /map robot after dropout={robot}")

    # check if coordinator still responds correctly
    assert "map" in data
    assert "robots" in data
    assert robot is not None
    assert robot["x"] == x
    assert robot["y"] == y + 1