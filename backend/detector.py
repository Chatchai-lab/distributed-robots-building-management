import random
import time
import requests
import json
import paho.mqtt.client as mqtt
import uuid

# configuration
HOST = "vs-coordinator"
BROKER_HOST = "vs-mqtt-broker"
COORDINATOR_PORT = 8080
MQTT_CLIENT = None


def register_robot():
    response = requests.post(f'http://{HOST}:{COORDINATOR_PORT}/robot')
    data = response.json()
    return data['id'], data['position']['x'], data['position']['y'], data['map']

# init mqtt connection to coordinator
def init_mqtt():
    global MQTT_CLIENT
    MQTT_CLIENT = mqtt.Client()

    print(f"[DETECTOR] Verbinde mit Broker: {BROKER_HOST}")
    MQTT_CLIENT.connect(BROKER_HOST, 1883)

    MQTT_CLIENT.loop_start()


# send robot status via mqtt
def send_status_mqtt(robot_id, x, y):
    payload = {
        "id": robot_id,
        "x": x,
        "y": y,
        "role": "Detector",
        "status": "ACTIVE"
    }

    # publish mqtt status to all subscribers
    topic = f"robot/status/{robot_id}"
    MQTT_CLIENT.publish(topic, json.dumps(payload))


def next_move(x, y, grid):
    moves = [(0, 1), (0, -1), (1, 0), (-1, 0)]
    valid = []
    for dx, dy in moves:
        nx, ny = x + dx, y + dy
        if 0 <= ny < len(grid) and 0 <= nx < len(grid[0]) and grid[ny][nx] not in ("#",):
            valid.append((nx, ny))

    if valid:
        return random.choice(valid)
    return (x, y)


def maybe_send_event(x, y):
    if random.random() < 0.05:  # 5% Chance
        pid = str(uuid.uuid4())
        problem = {
            "id": pid,
            "type": random.choice(["SCHMUTZ", "DEFEKT"]),
            "x": x,
            "y": y,
            "round": 1,
            "timestamp": time.time(),
        }
        print(f"[DETECTOR] new problem {problem['type']} at ({problem['x']},{problem['y']}) id={pid}")
        MQTT_CLIENT.publish("problems/new", json.dumps(problem))


if __name__ == "__main__":
    time.sleep(5)
    robot_id, x, y, grid = register_robot()
    print(f"[START] Detector #{robot_id} gestartet bei ({x}, {y})")

    init_mqtt()

    try:
        while True:
            # send position to coordinator
            send_status_mqtt(robot_id, x, y)

            # search for problems
            maybe_send_event(x, y)

            # move robot
            x, y = next_move(x, y, grid)

            # simulate wait time
            time.sleep(1)

    except KeyboardInterrupt:
        print("[STOP] Beende Detector...")
    finally:
        if MQTT_CLIENT:
            MQTT_CLIENT.loop_stop()
            MQTT_CLIENT.disconnect()