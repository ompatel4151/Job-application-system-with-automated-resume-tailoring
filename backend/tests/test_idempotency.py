"""Idempotency-Key: retrying a create must not create a second record."""

BODY = {"company": "Acme", "role": "SWE", "job_description": "Python"}


def _count(client):
    return len(client.get("/api/applications").json()["items"])


def test_same_key_twice_creates_one_record(client):
    headers = {"Idempotency-Key": "key-1"}

    first = client.post("/api/applications", json=BODY, headers=headers)
    second = client.post("/api/applications", json=BODY, headers=headers)

    assert first.status_code == 201
    assert second.status_code == 201
    assert second.json() == first.json()
    assert second.headers.get("Idempotent-Replayed") == "true"
    assert _count(client) == 1


def test_same_key_with_a_different_body_is_rejected(client):
    headers = {"Idempotency-Key": "key-2"}
    client.post("/api/applications", json=BODY, headers=headers)

    resp = client.post(
        "/api/applications", json={**BODY, "role": "Other"}, headers=headers
    )

    assert resp.status_code == 422
    assert _count(client) == 1


def test_key_is_scoped_to_one_endpoint(client, sample_resume_content):
    headers = {"Idempotency-Key": "key-3"}
    client.post("/api/applications", json=BODY, headers=headers)

    resp = client.post(
        "/api/resumes",
        json={"name": "Base", "content": sample_resume_content},
        headers=headers,
    )

    assert resp.status_code == 422


def test_without_a_key_each_request_creates_a_record(client):
    """Backward compatible: clients that send no key behave as before."""
    client.post("/api/applications", json=BODY)
    client.post("/api/applications", json=BODY)

    assert _count(client) == 2


def test_retried_tailor_calls_the_model_once(
    client, make_application, make_resume, fake_tailoring, monkeypatch
):
    import app.routers.tailoring as router

    calls = []
    fake = router.tailoring.tailor_resume

    def counting(**kwargs):
        calls.append(kwargs)
        return fake(**kwargs)

    monkeypatch.setattr(router.tailoring, "tailor_resume", counting)
    make_resume()
    app_data = make_application()
    url = f"/api/applications/{app_data['id']}/tailor"
    headers = {"Idempotency-Key": "tailor-1"}

    first = client.post(url, json={}, headers=headers)
    second = client.post(url, json={}, headers=headers)

    assert first.status_code == second.status_code == 201
    assert second.json()["id"] == first.json()["id"]
    assert len(calls) == 1


def test_a_failed_request_is_not_stored(
    client, make_application, make_resume, fake_tailoring
):
    """Only successes are stored, so a retry after fixing the problem works."""
    make_resume()
    app_data = make_application(job_description=None)
    url = f"/api/applications/{app_data['id']}/tailor"
    headers = {"Idempotency-Key": "tailor-2"}

    assert client.post(url, json={}, headers=headers).status_code == 400

    client.patch(
        f"/api/applications/{app_data['id']}", json={"job_description": "Python"}
    )
    assert client.post(url, json={}, headers=headers).status_code == 201


def test_overlong_key_is_rejected(client):
    resp = client.post(
        "/api/applications", json=BODY, headers={"Idempotency-Key": "k" * 256}
    )
    assert resp.status_code == 422
