import pytest
import grpc
import time
from backend import robots_pb2, robots_pb2_grpc

CLEANER_ADDR = "localhost:50051"


# Ziel 1: Funktional: Direkte Aufgabenvergabe via gRPC
# Ziel 2: Nicht-funktional: Messung der Latenz
@pytest.mark.timeout(30)
def test_grpc_assignment_and_performance():

    # Verbindung zum gRPC-Server des Bots aufbauen
    channel = grpc.insecure_channel(CLEANER_ADDR)
    stub = robots_pb2_grpc.ServiceBotStub(channel)

    # gRPC-Task erstellen
    task_request = robots_pb2.Task(
        task_id=123,
        type=robots_pb2.SCHMUTZ,
        location=robots_pb2.Position(x=5, y=5)
    )

    try:
        # Startzeitmessung für Nicht-funktionaler Aspekt
        start_time = time.perf_counter()

        # gRPC-Call ausführen
        response = stub.AssignTask(task_request)

        # Endzeitmessung
        duration_ms = (time.perf_counter() - start_time) * 1000

        # Validierung (funktional)
        assert response.ok is True, "Bot hat den Task via gRPC abgelehnt"

        print(f"\n[FUNKTIONAL] gRPC-Call erfolgreich: {response.message}")
        print(f"[NON-FUNKTIONAL] RPC-Latenz: {duration_ms:.2f} ms")

        # Performance-Check (nicht-funktional)
        assert duration_ms < 25000, f"Bot braucht zu lange für die Arbeit: {duration_ms:.2f}ms"
    except grpc.RpcError as e:
        pytest.fail(f"gRPC Verbindung zu {CLEANER_ADDR} fehlgeschlagen: {e}")
    finally:
        channel.close()