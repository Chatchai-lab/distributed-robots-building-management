import json
import time
import threading
import requests
import paho.mqtt.client as mqtt

from backend.RobotLogic import RobotLogic
from backend.detector import COORDINATOR_PORT


HOST = "vs-coordinator"
BROKER_HOST = "vs-mqtt-broker"

STATUS_IDLE = 0
STATUS_BUSY = 1

ROLE_CAN_SOLVE = {
    "cleaner": {"SCHMUTZ"},
    "repair": {"DEFEKT"},
}


# registrate bots at coordinator
def register_servicebot(role):
    if role == "cleaner":
        endpoint = "/robot-cleaner"
    elif role == "repair":
        endpoint = "/robot-repair"
    else:
        raise ValueError(f"Unbekannte Rolle: {role}")

    url = f"http://{HOST}:{COORDINATOR_PORT}{endpoint}"
    res = requests.post(url)
    res.raise_for_status()
    data = res.json()

    print( f"[ServiceBot] Registriert als {role}, "
        f"id={data['id']} pos=({data['position']['x']},{data['position']['y']})")

    return data["id"], data["position"]["x"], data["position"]["y"], data["map"]


# service bot class which contains mqtt logic and task processing
class ServiceBot:
    def __init__(self, robot_id, start_x, start_y, role, grid):
        self.robot_id = robot_id
        self.x = start_x
        self.y = start_y
        self.role = role
        self.grid = grid

        self.status = STATUS_IDLE

        self.problems = {}
        self.claims = {}
        self.started = set()
        self.claim_timer_started = set()

        self.lock = threading.Lock()

        # MQTT
        self.mqtt = mqtt.Client()
        self.mqtt.on_message = self.on_message
        self.mqtt.connect(BROKER_HOST, 1883)

        self.mqtt.subscribe("problems/new")
        self.mqtt.subscribe("tasks/claim/#")
        self.mqtt.subscribe("tasks/assigned/#")
        self.mqtt.subscribe("tasks/done/#")

        self.fetch_existing_open_problems()

        # danach einmal “retry/claim” anstoßen
        with self.lock:
            probs = list(self.problems.values())
        for p in probs:
            self.handle_new_problem(p)

        self.mqtt.loop_start()

        # start process which simulates a robot heartbeat and loop for tasks
        threading.Thread(target=self._heartbeat, daemon=True).start()
        threading.Thread(target=self.idle_retry_loop, daemon=True).start()


    # mqtt handling
    def on_message(self, client, userdata, msg):
        try:
            data = json.loads(msg.payload.decode())
        except Exception:
            return

        if msg.topic == "problems/new":
            pid = data["id"]
            with self.lock:
                self.problems[pid] = data
            self.handle_new_problem(data)

        elif msg.topic.startswith("tasks/claim/"):
            pid = msg.topic.split("/")[-1]
            self.claims.setdefault(pid, []).append(data)


        elif msg.topic.startswith("tasks/assigned/"):
            pid = data["problem_id"]

            with self.lock:
                self.problems.pop(pid, None)
                self.claims.pop(pid, None)
                self.claim_timer_started.discard(pid)

                # task is already started
                if pid in self.started:
                    return

                if data.get("robot_id") != self.robot_id:
                    return

                self.started.add(pid)

            print(f"[START] Gehe zu Problem {pid}")
            threading.Thread(target=self.start_problem, args=(data,), daemon=True).start()

        elif msg.topic.startswith("tasks/done/"):
            pid = msg.topic.split("/")[-1]
            with self.lock:
                self.problems.pop(pid, None)
                self.claims.pop(pid, None)
                self.claim_timer_started.discard(pid)


    # claim and leader election
    def handle_new_problem(self, problem):
        if self.status != STATUS_IDLE:
            return

        if problem["type"] not in ROLE_CAN_SOLVE.get(self.role, set()):
            return

        pid = problem["id"]
        dist = self.manhattan(problem["x"], problem["y"])

        claim = {
            "problem_id": pid,
            "robot_id": self.robot_id,
            "dist": dist,
            "round": problem.get("round", 1),
            "ts": time.time(),
        }

        with self.lock:
            if pid in self.claim_timer_started:
                return
            self.claim_timer_started.add(pid)
            # Eigenen Claim sofort lokal speichern
            self.claims.setdefault(pid, []).append(claim)

        self.mqtt.publish(f"tasks/claim/{pid}", json.dumps(claim))
        print(f"[CLAIM] bot={self.robot_id} problem={pid} dist={dist}")

        threading.Timer(0.3, self.decide_winner, args=(pid,)).start()


    # leader election
    def decide_winner(self, pid):
        with self.lock:
            claims = list(self.claims.get(pid, []))
            problem = self.problems.get(pid)

        if not claims or not problem:
            return

        current_round = problem.get("round", 1)

        valid_claims = [c for c in claims if c.get("round", 1) == current_round]

        if not valid_claims:
            return

        winner = min(valid_claims, key=lambda c: (c["dist"], c["robot_id"]))
        if winner["robot_id"] == self.robot_id:
            print(f"[WINNER] Ich übernehme Problem {pid}")
            problem = {
                "problem_id": pid,
                "robot_id": self.robot_id,
                "x": problem["x"],
                "y": problem["y"],
                "type": problem["type"],
                "round": problem.get("round", 1),
                "assigned_ts": time.time(),
            }
            self.mqtt.publish(f"tasks/assigned/{pid}", json.dumps(problem))


    # task assigned and now start go to problem and fix it
    def start_problem(self, data):
        pid = data["problem_id"]
        with self.lock:
            if self.status != STATUS_IDLE:
                return
            self.status = STATUS_BUSY

        self.send_status()

        logic = RobotLogic(self.robot_id, self.x, self.y, self.grid)
        path = logic.find_path_bfs(self.x, self.y, data["x"], data["y"])

        if path:
            for nx, ny in path:
                self.x, self.y = nx, ny
                self.send_status()
                time.sleep(1)

        # simulate work time
        time.sleep(5)

        task_done_message = {
            "problem_id": data["problem_id"],
            "robot_id": self.robot_id,
            "finished_ts": time.time(),
        }

        self.mqtt.publish( f"tasks/done/{data['problem_id']}", json.dumps(task_done_message))

        with self.lock:
            self.started.discard(pid)
            self.status = STATUS_IDLE

        self.send_status()

    # send status with mqtt to coordinator
    def send_status(self):
        status_message = {
            "id": self.robot_id,
            "x": self.x,
            "y": self.y,
            "role": self.role,
            "status": "BUSY" if self.status else "IDLE",
        }
        self.mqtt.publish(f"robot/status/{self.robot_id}", json.dumps(status_message))

    # simulate heartbeat from servicebot
    def _heartbeat(self):
        while True:
            self.send_status()
            time.sleep(1)

    # Retry for new Problems if bot status is not idle
    def idle_retry_loop(self):
        while True:
            time.sleep(3)
            if self.status != STATUS_IDLE:
                continue

            with self.lock:
                problems = list(self.problems.values())

            for p in problems:
                self.handle_new_problem(p)

    # calculate distance to problem
    def manhattan(self, x, y):
        return abs(self.x - x) + abs(self.y - y)

    def fetch_existing_open_problems(self, retries=20, sleep_s=0.5):
        url = f"http://{HOST}:{COORDINATOR_PORT}/map"

        for _ in range(retries):
            try:
                r = requests.get(url, timeout=2)
                r.raise_for_status()
                data = r.json()

                existing = data.get("problems", [])
                with self.lock:
                    for p in existing:
                        pid = p["id"]
                        if p.get("status") == "OPEN":
                            p["round"] = p.get("round", 1)
                            self.problems[pid] = p

                print(f"[BOOTSTRAP] loaded {len(existing)} problems from coordinator")
                return
            except Exception:
                time.sleep(sleep_s)

        print("[BOOTSTRAP] could not fetch /map (coordinator not ready)")

# create cleaner/repair bot
def start(role):
    robot_id, x, y, grid = register_servicebot(role)
    ServiceBot(robot_id, x, y, role, grid)
    print(f"[ServiceBot] {role} ready (id={robot_id})")

    while True:
        time.sleep(10)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--role", choices=["cleaner", "repair"], required=True)
    args = parser.parse_args()

    start(args.role)