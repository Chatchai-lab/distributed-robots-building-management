import socket
import json
import random
import threading
import paho.mqtt.client as mqtt
import time

HOST = "0.0.0.0"
PORT = 8080
BROKER_HOST = "vs-mqtt-broker"


STATUS_IDLE = "IDLE"
STATUS_ACTIVE = "ACTIVE"

W, H = 20, 20
grid = [["." for _ in range(W)] for _ in range(H)]
robots = {}
robot_role = {'D': 'detector', 'C': 'cleaner', 'R': 'repair' }
next_robot_id = 1

ROLE_TO_SYMBOL = {
    "detector": "D",
    "cleaner": "C",
    "repair": "R",
}

ui_problem_counter = 1

problems = {}

last_seen = {}
assigned = {}

mqtt_client = None
state_lock = threading.Lock()

# mqtt handling for incoming messages
def on_message(client, userdata, msg):
    try:
        data = json.loads(msg.payload.decode())

        if msg.topic.startswith("robot/status/"):
            robot_id = data["id"]
            last_seen[robot_id] = time.time()
            new_x, new_y = data["x"], data["y"]
            role = (data.get("role") or "").strip().lower()
            status_str = data.get("status", "ACTIVE")

            with state_lock:
                if robot_id not in robots:
                    return

                robot = robots[robot_id]
                old_x, old_y = robot["x"], robot["y"]

                if grid[old_y][old_x] in ("D", "C", "R"):
                    grid[old_y][old_x] = "."

                robot["x"] = new_x
                robot["y"] = new_y
                robot["status"] = status_str

                symbol = ROLE_TO_SYMBOL.get(role, "?")
                if grid[new_y][new_x] not in ("$", "!"):
                    grid[new_y][new_x] = symbol

        elif msg.topic == "problems/new":
            pid = data["id"]
            ptype = data["type"]
            x, y = data["x"], data["y"]

            with state_lock:
                global ui_problem_counter
                problems[pid] = {
                    "id": pid,
                    "ui_id": ui_problem_counter,
                    "type": ptype,
                    "x": x,
                    "y": y,
                    "status": "OPEN"
                }
                ui_problem_counter += 1

                # grid symbol
                if ptype == "SCHMUTZ":
                    grid[y][x] = "$"
                elif ptype == "DEFEKT":
                    grid[y][x] = "!"

                print(f"[MQTT] Neues Problem {ptype} bei ({x},{y})")

        elif msg.topic.startswith("tasks/assigned/"):
            pid = msg.topic.split("/")[-1]
            robot_id = data.get("robot_id")

            with state_lock:
                if pid in problems:
                    problems[pid]["status"] = "ASSIGNED"
                    problems[pid]["assigned_robot"] = robot_id

                assigned[pid] = {
                    "robot_id": robot_id,
                    "assigned_ts": time.time(),
                }
        elif msg.topic.startswith("tasks/done/"):
            pid = msg.topic.split("/")[-1]
            with state_lock:
                problem = problems.pop(pid, None)
                if problem:
                    x, y = problem["x"], problem["y"]
                    if grid[y][x] in ("!", "$"):
                        grid[y][x] = "."

    except Exception as e:
        print(f"[MQTT ERROR] {e}")


# create mqtt client and subscribe to needed topics
def start_mqtt_subscriber():
    global mqtt_client
    mqtt_client = mqtt.Client()
    mqtt_client.on_message = on_message

    print(f"[MQTT] Verbinde zu Broker: {BROKER_HOST}")
    mqtt_client.connect(BROKER_HOST, 1883)

    # subscribe to all robot status updates
    mqtt_client.subscribe("robot/status/#")
    mqtt_client.subscribe("problems/new")
    mqtt_client.subscribe("tasks/assigned/#")
    mqtt_client.subscribe("tasks/done/#")

    mqtt_client.loop_start()


# watches for robot status and after no contact to robot resend assigned problems
def watchdog_loop(timeout_sec=10):
    while True:
        time.sleep(2)
        if mqtt_client is None:
            continue

        now = time.time()

        with state_lock:
            for pid, meta in list(assigned.items()):
                rid = meta["robot_id"]
                last = last_seen.get(rid)

                # never seen bot
                if last is None:
                    continue

                # bot dead
                if now - last > timeout_sec:
                    print(f"[WATCHDOG] robot {rid} timeout -> release problem {pid}")

                    # release problem
                    if pid in problems:
                        problems[pid]["status"] = "OPEN"
                        problems[pid].pop("assigned_robot", None)

                        problems[pid]["round"] = problems[pid].get("round", 1) + 1

                        payload = {
                            "id": problems[pid]["id"],
                            "type": problems[pid]["type"],
                            "x": problems[pid]["x"],
                            "y": problems[pid]["y"],
                            "round": problems[pid]["round"],
                            "reason": "watchdog_timeout"
                        }

                        mqtt_client.publish("problems/new", json.dumps(payload))

                    assigned.pop(pid, None)

# generate random map at every start
def generate_map(w, h, wall_ratio=0.1):
    grid = [["." for _ in range(w)] for _ in range(h)]
    num_walls = int(w * h * wall_ratio)
    for _ in range(num_walls):
        x = random.randint(0, w - 1)
        y = random.randint(0, h - 1)
        grid[y][x] = "#"
    return grid

# json helper
def json_response_body(payload_dict):
    payload = json.dumps(payload_dict, indent=2).encode("utf-8")
    return (
        "HTTP/1.1 200 OK\r\n"
        "Content-Type: application/json\r\n"
        f"Content-Length: {len(payload)}\r\n"
        "Connection: close\r\n"
        "\r\n"
    ).encode("utf-8") + payload


def recv_http_request(conn):
    buffer = b""

    # read complete header
    while b"\r\n\r\n" not in buffer:
        chunk = conn.recv(1024)
        if not chunk:
            return None
        buffer += chunk

    header_raw, rest = buffer.split(b"\r\n\r\n", 1)

    header_text = header_raw.decode("utf-8", errors="ignore")
    header_lines = header_text.split("\r\n")
    request_line = header_lines[0].split(" ")

    if len(request_line) < 3:
        return None

    method, path, version = request_line

    # get content length
    content_length = 0
    for line in header_lines[1:]:
        if line.lower().startswith("content-length:"):
            content_length = int(line.split(":")[1].strip())

    # read body
    body = rest
    while len(body) < content_length:
        chunk = conn.recv(1024)
        if not chunk:
            break
        body += chunk

    body = body[:content_length]

    return method, path, version, header_lines, body


# handle client http requests
def handle_client(conn, addr):
    try:
        client_ip, _ = addr
        origin = "[CONTAINER]" if client_ip.startswith("172.") else "[HOST]"
        print(f"{origin} [CONNECTED] {addr}")

        # eine Anfrage pro Verbindung
        req = recv_http_request(conn)
        if req is None:
            return

        method, path, version, header_lines, body_raw = req

        # default unknown path
        body = b"Unknown path"
        response = (
                       "HTTP/1.1 400 Bad Request\r\n"
                       "Content-Type: text/plain; charset=utf-8\r\n"
                       f"Content-Length: {len(body)}\r\n"
                       "Connection: close\r\n"
                       "\r\n"
                   ).encode("utf-8") + body

        if method == "GET":
            if path == '/':
                content = open('frontend/index.html').read()
                response = (
                        version + " 200 OK\r\n"
                                  "Content-Type: text/html; charset=utf-8\r\n"
                                  f"Content-Length: {len(content.encode('utf-8'))}\r\n"
                                  "Connection: close\r\n"
                                  "\r\n"
                        + content
                ).encode("utf-8")

            elif path == '/status':
                data = {
                    "robots": len(robots),
                    "list": list(robots.values())
                }
                response = json_response_body(data)

            elif path == '/map':
                data = {
                    "map": ["".join(row) for row in grid],
                    "robots": list(robots.values()),
                    "problems": list(problems.values()),
                }
                response = json_response_body(data)

        elif method == "POST":
            global next_robot_id
            if path == '/robot':
                robot_id = next_robot_id
                next_robot_id += 1
                x, y = random.randint(0, W - 1), random.randint(0, H - 1)
                robots[robot_id] = {
                    'id': robot_id,
                    'x': x,
                    'y': y,
                    'role': robot_role['D'],
                    'status': STATUS_ACTIVE,
                }
                grid[y][x] = "D"

                data = {
                    "id": robot_id,
                    'role': robot_role['D'],
                    "position": {"x": x, "y": y},
                    "map": ["".join(row) for row in grid]
                }
                response = json_response_body(data)

            elif path == '/robot-cleaner':
                robot_id = next_robot_id
                next_robot_id += 1
                x, y = random.randint(0, W - 1), random.randint(0, H - 1)

                robots[robot_id] = {
                    'id': robot_id,
                    'x': x,
                    'y': y,
                    'role':  robot_role['C'],
                    'status': STATUS_IDLE,
                }
                grid[y][x] = "C"

                data = {
                    "id": robot_id,
                    "role": robot_role['C'],
                    "position": {"x": x, "y": y},
                    "map": ["".join(row) for row in grid]
                }

                response = json_response_body(data)

            elif path == '/robot-repair':
                robot_id = next_robot_id
                next_robot_id += 1
                x, y = random.randint(0, W - 1), random.randint(0, H - 1)

                robots[robot_id] = {
                    'id': robot_id,
                    'x': x,
                    'y': y,
                    'role': robot_role['R'],
                    'status': STATUS_IDLE,
                }
                grid[y][x] = "R"

                data = {
                    "id": robot_id,
                    "role": robot_role['R'],
                    "position": {"x": x, "y": y},
                    "map": ["".join(row) for row in grid]
                }

                response = json_response_body(data)

        conn.sendall(response)

    except ConnectionResetError:
        print(f"[DISCONNECTED] {addr}")
    finally:
        conn.close()

# start coordinator http server
def start_server():
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind((HOST, PORT))
    server.listen()
    print(f"[START] Webserver {HOST}:{PORT}")
    while True:
        conn, addr = server.accept()
        threading.Thread(target=handle_client, args=(conn, addr), daemon=True).start()


if __name__ == "__main__":
    # generate map
    grid = generate_map(W, H, wall_ratio=0.15)

    # start mqtt client
    start_mqtt_subscriber()

    # start robot status watcher
    threading.Thread(target=watchdog_loop, daemon=True).start()

    # start http server
    start_server()