def test_create_and_get_application(client, make_application):
    app_data = make_application()
    assert app_data["company"] == "Globex"
    assert app_data["status"] == "saved"
    assert app_data["applied_at"] is None

    resp = client.get(f"/api/applications/{app_data['id']}")
    assert resp.status_code == 200
    assert resp.json()["role"] == "Backend Engineer"


def test_status_transition_stamps_applied_at(client, make_application):
    app_data = make_application()
    resp = client.patch(
        f"/api/applications/{app_data['id']}", json={"status": "applied"}
    )
    assert resp.status_code == 200
    assert resp.json()["applied_at"] is not None

    # Moving on to interview keeps the original applied_at
    applied_at = resp.json()["applied_at"]
    resp = client.patch(
        f"/api/applications/{app_data['id']}", json={"status": "interview"}
    )
    assert resp.json()["applied_at"] == applied_at


def test_created_as_applied_stamps_applied_at(client, make_application):
    app_data = make_application(status="applied")
    assert app_data["applied_at"] is not None


def test_filter_by_status(client, make_application):
    make_application(company="A")
    make_application(company="B", status="applied")

    resp = client.get("/api/applications", params={"status": "applied"})
    assert [a["company"] for a in resp.json()] == ["B"]

    resp = client.get("/api/applications")
    assert len(resp.json()) == 2


def test_stats(client, make_application):
    make_application()
    make_application(status="applied")
    make_application(status="applied")

    resp = client.get("/api/applications/stats")
    stats = resp.json()
    assert stats["total"] == 3
    assert stats["by_status"]["applied"] == 2
    assert stats["by_status"]["saved"] == 1
    assert stats["by_status"]["offer"] == 0


def test_delete_application(client, make_application):
    app_data = make_application()
    assert client.delete(f"/api/applications/{app_data['id']}").status_code == 204
    assert client.get(f"/api/applications/{app_data['id']}").status_code == 404


def test_get_missing_application_404(client):
    assert client.get("/api/applications/999").status_code == 404
