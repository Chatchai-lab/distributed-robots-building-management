import threading
import time
import requests

BASE_URL = "http://localhost:8080"

def test_create_robot():
    request = requests.post(f"{BASE_URL}/robot")
    data = request.json()

    assert request.status_code == 200
    assert "id" in data
    assert "position" in data
    assert "map" in data


def test_get_map():
    requests.post(f"{BASE_URL}/robot")
    request = requests.get(f"{BASE_URL}/map")

    data = request.json()
    grid = data["map"]

    assert request.status_code == 200
    assert all(isinstance(row, str) for row in grid)


def test_unknown_path():
    request = requests.get(f"{BASE_URL}/xyz")

    assert request.status_code == 400


