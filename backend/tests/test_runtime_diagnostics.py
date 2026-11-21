from fastapi.testclient import TestClient
from backend.app.main import app


def test_runtime_diagnostics_reports_backend_database_and_worker_state():
    response = TestClient(app).get("/api/v1/settings/runtime", headers={"host": "127.0.0.1:8000"})
    assert response.status_code == 200
    body = response.json()
    assert body["backend"]["status"] == "ok"
    assert body["backend"]["version"]
    assert body["database"]["status"] in {"ok", "unavailable"}
    assert isinstance(body["worker"]["enabled"], bool)
    assert body["worker"]["status"] in {"running", "stopped", "disabled"}
    assert isinstance(body["worker"]["registered_handlers"], list)
    assert "not a creative production handler" in body["execution_note"]
