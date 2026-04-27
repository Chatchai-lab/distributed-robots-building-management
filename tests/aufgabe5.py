import pytest
import paho.mqtt.client as mqtt
import json
import time
import uuid
import subprocess

broker_addr = "localhost"
# Ziel: dezentrale Aufgabenverteilung durch ServiceBots
# Verhandeln die Bots untereinander?
@pytest.mark.timeout(20)
def test_decentralized_assignment_flow():
    client = mqtt.Client()
    client.connect(broker_addr, 1883)

    received_assignments = []

    def on_message(c, userdata, msg):
        received_assignments.append(json.loads(msg.payload.decode()))

    client.subscribe("tasks/assigned/#")
    client.on_message = on_message
    client.loop_start()

    # Problem simulieren
    prob_id = str(uuid.uuid4())
    problem = {"id": prob_id, "type": "SCHMUTZ", "x": 1, "y": 1, "round": 1}
    client.publish("problems/new", json.dumps(problem))

    # Zeit für Negotiation lassen
    time.sleep(5)
    client.loop_stop()

    # Ein Service-Bot muss sich selbst zugewiesen haben
    assert len(received_assignments) > 0, "Keine autonomer Task-Claim erkannt!"
    assert received_assignments[0]["problem_id"] == prob_id



# Ziel: Nachweis der Fehlertoleranz und Robustheit in einer verteilten Umgebung bei Prozessausfällen
@pytest.mark.timeout(60)
def test_system_robustness_watchdog_auto():
    client = mqtt.Client()
    client.connect(broker_addr, 1883)

    context = {"assigned_bot_id": None, "retry_detected": False}

    def on_message(c, userdata, msg):
        data = json.loads(msg.payload.decode())
        # Speichere, welcher Bot den Task übernommen hat
        if msg.topic.startswith("tasks/assigned/"):
            context["assigned_bot_id"] = data.get("robot_id")

        # Prüfe, ob der Koordinator das Problem neu veröffentlicht (round > 1)
        if msg.topic == "problems/new" and data.get("round", 1) > 1:
            context["retry_detected"] = True

    client.subscribe([("tasks/assigned/#", 0), ("problems/new", 0)])
    client.on_message = on_message
    client.loop_start()

    # Problem triggern
    prob_id = str(uuid.uuid4())
    problem = {"id": prob_id, "type": "SCHMUTZ", "x": 10, "y": 10, "round": 1}
    client.publish("problems/new", json.dumps(problem))

    # Warten, bis ein Bot den Task übernimmt
    for _ in range(20):
        if context["assigned_bot_id"]:
            break
        time.sleep(0.5)

    if context["assigned_bot_id"] is None:
        client.loop_stop()
        pytest.fail("KEIN BOT REAGIERT. Prüfe ob Bots IDLE sind und (10,10) erreichbar ist!")

    # Bot-Container finden und stoppen
    # Auflisten aller Service-Bot-Container -> 1. wird genommen
    cmd = "docker ps --format '{{.Names}}' | grep -E 'vs-cleaner|vs-repair'"
    running_bots = subprocess.getoutput(cmd).strip().split('\n')

    if not running_bots or not running_bots[0]:
        pytest.fail("Keine laufenden Service-Bot Container gefunden!")

    container_name = running_bots[0]
    print(f"\n[TEST] Töte Container: {container_name} (simuliert Ausfall von Bot {context['assigned_bot_id']})")
    subprocess.run(["docker", "stop", container_name], check=True)

    # Auf Watchdog warten
    time.sleep(15)

    client.loop_stop()

    # Container wiederbeleben für die nächsten Tests
    subprocess.run(["docker", "start", container_name], check=False)


    assert context["retry_detected"] is True, "Watchdog hat den Ausfall nicht bemerkt!"
    print(f"Robustheit bewiesen: Problem wurde nach Ausfall neu veröffentlicht.")


@pytest.mark.performance
def test_decentralized_lifecycle_latency():
    client = mqtt.Client()
    client.connect(broker_addr, 1883)

    timestamps = {
        "detected": 0,
        "assigned": 0,
        "done": 0
    }

    def on_message(c, userdata, msg):
        data = json.loads(msg.payload.decode())


        if data.get("problem_id") == test_id or data.get("id") == test_id:
            if "tasks/assigned" in msg.topic:
                timestamps["assigned"] = time.perf_counter()
                print(
                    f" -> Task wurde übernommen nach: {(timestamps['assigned'] - timestamps['detected']) * 1000:.2f}ms")
            elif "tasks/done" in msg.topic:
                timestamps["done"] = time.perf_counter()
                print(f" -> Task wurde abgeschlossen nach: {(timestamps['done'] - timestamps['detected']):.2f}s")

    client.on_message = on_message

    client.subscribe("tasks/assigned/#")
    client.subscribe("tasks/done/#")
    client.loop_start()

    # Problem wird erkannt
    test_id = str(uuid.uuid4())
    problem = {"id": test_id, "type": "SCHMUTZ", "x": 1, "y": 1}

    print(f"\n[START] Sende Problem {test_id}...")
    timestamps["detected"] = time.perf_counter()
    client.publish("problems/new", json.dumps(problem))

    # Warten bis der Bot GANZ FERTIG ist
    timeout = time.time() + 45
    while timestamps["done"] == 0 and time.time() < timeout:
        time.sleep(0.5)

    client.loop_stop()

    if timestamps["assigned"] > 0 and timestamps["done"] > 0:
        latency_negotiation = (timestamps["assigned"] - timestamps["detected"]) * 1000
        total_process_time = (timestamps["done"] - timestamps["detected"])

        print(f"\n--- ERGEBNISSE ---")
        print(f"Verhandlungs-Latenz: {latency_negotiation:.2f} ms")
        print(f"Gesamt-Prozesszeit: {total_process_time:.2f} s")

        assert latency_negotiation < 5000, "Verhandlung zu langsam!"
        assert total_process_time < 40, "Gesamtprozess dauert zu lange!"
    else:
        pytest.fail("Der Task wurde nicht vollständig abgeschlossen (Timeout).")