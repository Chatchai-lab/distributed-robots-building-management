# Tests und Validierung

Zum Starten der Anwendung müssen die Docker-Images im Stammverzeichnis gebaut und gestartet werden:

```bash
cd docker
docker compose down -v 
docker compose build --no-cache
docker compose up
```

---

## Aufgabe 1 - Koordinator Tests
Zur Überprüfung der grundlegenden Funktionalität des Koordinators wurden REST-Schnittstellen-Tests durchgeführt.

---
### test_create_robot (Funktionaler Test)
Dieser Test validiert das dynamische Hinzufügen von Robotern zum System.
* **Ablauf:** Es wird ein POST-Request an den Endpunkt `/robot` gesendet.
* **Validierung:** Der Test stellt sicher, dass der Koordinator mit dem Statuscode 200 antwortet und ein valides JSON-Objekt zurückgibt, welches eine eindeutige `id`, die Start-`position` sowie das aktuelle `map`-Layout enthält.

---
### test_get_map (Funktionaler Test)
Dieser Test prüft die korrekte Bereitstellung des digitalen Abbilds der Einsatzumgebung (Grid).
* **Ablauf:** Nach der Initialisierung eines Roboters wird der GET-Endpunkt `/map` aufgerufen.
* **Validierung:** Es wird geprüft, ob die API das Grid als Liste von Strings zurückgibt, wobei jede Zeile der Karte korrekt serialisiert ist. Dies ist die Grundlage für die Visualisierung im Frontend.

---
### test_unknown_path (Nicht-funktionaler Test)
Ein Negativ-Test zur Überprüfung der Fehlerbehandlung des API-Gateways.
* **Ablauf:** Es wird ein Request an einen nicht existierenden Pfad (`/xyz`) gesendet.
* **Validierung:** Der Test bestätigt, dass das System robust reagiert und einen entsprechenden Fehlercode (Status 400) zurückgibt.

---

![Testergebnis - success](images/test_aufgabe_2.png)

Zum Ausführen der Tests:
```bash
cd tests
pytest test_coordinator.py -s -v
```
---

## Aufgabe 3 - MQTT-Tests

Zur Überprüfung, ob die Kommunikation mit MQTT funktioniert wurden folgende beiden Tests durchgeführt.

---

### test_mqtt_status_updates_map (Funktionaler Test)
Der Test erstellt einen weiteren Detektor-Bot und sendet eine vorher definierte Bewegung mittels MQTT an den Koordinator. Danach wird der `/map` Endpunkt des Koordinators aufgerufen und es wird überprüft, ob die Bewegung korrekt übermittelt wurde und der Roboter an der korrekten Position ist.

### test_robot_failure_no_mqtt_messages (Nicht-funktionaler Test)
Bei diesem Test wird ebenfalls eine Bewegung eines Detektor-Bots simuliert und danach keine Bewegung mehr gesendet, um zu überprüfen, ob der Systemzustand konsistent ist. Das Ergebnis zeigt, dass bei Ausfall der Kommunikation der ausgefallene Roboter stehen bleibt.

---

![Testergebnis - success](images/test_mqtt.png)

Zum Ausführen der Tests:
```bash
cd tests
pytest mqtt.py -s -v
```

--- 

## Aufgabe 5 - Dezentrale Koordination & Fehlertoleranz

### test_system_robustness_watchdog_auto (Nicht-funktionaler Test)
Dieser Test weist die Fehlertoleranz und Robustheit des Gesamtsystems bei einem plötzlichen Prozessausfall nach (Aufgabe 5).

* **Funktionaler Aspekt:** Es wird simuliert, dass ein Service-Bot während der Bearbeitung eines Tasks abstürzt. Der Test nutzt Docker-Befehle (`docker stop`), um den Container des aktiven Bots gewaltsam zu beenden.
* **Validierung:** Der Koordinator muss den Ausfall über den fehlenden MQTT-Heartbeat (Watchdog) erkennen. Der Test ist erfolgreich, wenn der Koordinator das Problem automatisch mit einer erhöhten `round`-Nummer neu auf das Topic `problems/new` publiziert.

**Ergebnis:** Die Robustheit wird bewiesen, indem das System den Ausfall erkennt und sicherstellt, dass die Aufgabe nicht im System "verloren" geht, sondern für andere Bots wieder freigegeben wird.

---
![Testergebnis - success](images/test_system_robustness_watchdog_auto.png)

---

Zum Ausführen des Tests:
```bash
cd tests
pytest aufgabe5.py::test_system_robustness_watchdog_auto -s -v
```

---
