"""Integration tests for FastAPI REST routers."""

import pytest
from fastapi.testclient import TestClient

from web_server import app
from core.database import session_scope
from core.models import Person, VerificationLog, AppSettings


@pytest.fixture()
def client():
    return TestClient(app)


class TestRouters:
    def test_health_check(self, client):
        res = client.get("/health")
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "healthy"
        assert "database" in data

    def test_stats_and_timeline(self, client):
        res = client.get("/api/stats")
        assert res.status_code == 200
        data = res.json()
        assert "total_registered" in data
        assert "detections_today" in data

        res_timeline = client.get("/api/analytics/timeline")
        assert res_timeline.status_code == 200
        timeline = res_timeline.json()
        assert "timeline" in timeline
        assert len(timeline["timeline"]) == 24

    def test_settings_get_and_update(self, client):
        res = client.get("/api/v1/settings")
        assert res.status_code == 200
        cfg = res.json()
        assert "similarity_threshold" in cfg
        assert "audio_alerts_enabled" in cfg

        # Update settings
        update_payload = {
            "similarity_threshold": 0.55,
            "webhook_url": "https://example.com/webhook",
            "audio_alerts_enabled": False,
        }
        put_res = client.put("/api/v1/settings", json=update_payload)
        assert put_res.status_code == 200
        updated = put_res.json()
        assert updated["similarity_threshold"] == 0.55
        assert updated["webhook_url"] == "https://example.com/webhook"
        assert updated["audio_alerts_enabled"] is False

    def test_persons_crud_and_merge(self, client):
        # Insert two persons directly in database
        import asyncio

        async def setup_people():
            async with session_scope() as session:
                p1 = Person(name="Alice Silva", embedding=[0.2] * 512, sighting_count=3)
                p2 = Person(name="Alice S.", embedding=[0.25] * 512, sighting_count=2)
                session.add_all([p1, p2])
                await session.flush()
                p1_id, p2_id = p1.id, p2.id

                # Add logs
                session.add(VerificationLog(person_id=p2_id, confidence=0.95, source="test"))
                return p1_id, p2_id

        p1_id, p2_id = asyncio.run(setup_people())

        # List persons
        res = client.get("/api/v1/persons")
        assert res.status_code == 200
        people = res.json()
        assert len(people) >= 2

        # Rename person 1
        rename_res = client.put(f"/api/v1/persons/{p1_id}", json={"name": "Alice Silva Oficial"})
        assert rename_res.status_code == 200
        assert rename_res.json()["name"] == "Alice Silva Oficial"

        # Merge person 2 into person 1
        merge_res = client.post(f"/api/v1/persons/{p2_id}/merge/{p1_id}")
        assert merge_res.status_code == 200
        merge_data = merge_res.json()
        assert merge_data["success"] is True
        assert merge_data["target_id"] == p1_id

        # Person 2 should no longer exist (404)
        get_p2 = client.get(f"/api/v1/persons/{p2_id}")
        assert get_p2.status_code == 404

        # Person 1 should now have combined sighting count (3 + 2 = 5)
        get_p1 = client.get(f"/api/v1/persons/{p1_id}")
        assert get_p1.status_code == 200
        assert get_p1.json()["sighting_count"] == 5

        # Delete person 1
        del_res = client.delete(f"/api/v1/persons/{p1_id}")
        assert del_res.status_code == 200

    def test_csv_exports(self, client):
        # Logs CSV
        logs_csv = client.get("/api/logs/export.csv")
        assert logs_csv.status_code == 200
        assert "text/csv" in logs_csv.headers["content-type"]
        assert "ID Log" in logs_csv.text

        # Presence CSV
        pres_csv = client.get("/api/presence/export.csv")
        assert pres_csv.status_code == 200
        assert "text/csv" in pres_csv.headers["content-type"]
        assert "ID Pessoa" in pres_csv.text

    def test_events_api_flow(self, client):
        # Create event
        create_res = client.post("/api/v1/events", json={"name": "Feira de Inovação 2026"})
        assert create_res.status_code == 200
        event = create_res.json()
        event_id = event["id"]

        # Check active
        active_res = client.get("/api/v1/events/active")
        assert active_res.status_code == 200
        assert active_res.json()["id"] == event_id

        # Export event CSV
        csv_res = client.get(f"/api/v1/events/{event_id}/export.csv")
        assert csv_res.status_code == 200
        assert "text/csv" in csv_res.headers["content-type"]

        # End event
        end_res = client.post(f"/api/v1/events/{event_id}/end")
        assert end_res.status_code == 200
        assert end_res.json()["is_active"] is False

    def test_verify_faces_endpoint_with_device_id(self, client):
        import cv2
        import numpy as np
        import io

        # Cria uma imagem preta de teste (válida)
        img = np.zeros((100, 100, 3), dtype=np.uint8)
        _, buf = cv2.imencode(".jpg", img)
        file_bytes = io.BytesIO(buf.tobytes())

        res = client.post(
            "/api/v1/verify",
            files={"file": ("frame.jpg", file_bytes, "image/jpeg")},
            data={"device_id": "pi-portaria-01"},
        )
        assert res.status_code == 200
        data = res.json()
        assert "faces_detected" in data
        assert isinstance(data["results"], list)

