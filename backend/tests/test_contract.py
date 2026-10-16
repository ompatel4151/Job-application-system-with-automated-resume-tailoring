"""Contract tests: behavior the hardening milestones must NOT change.

They pin what the API does today: status codes, response shapes, what a
partial update touches. The frontend's TypeScript types are generated from
these exact shapes, so a later milestone that changes one of them by accident
fails here first.
"""

import pytest

APPLICATION_KEYS = {
    "id",
    "company",
    "role",
    "status",
    "job_description",
    "job_url",
    "notes",
    "applied_at",
    "created_at",
    "updated_at",
    "tailored_count",
}


def test_create_application_returns_the_full_shape(make_application):
    app_data = make_application()
    assert set(app_data) == APPLICATION_KEYS
    assert app_data["status"] == "saved"
    assert app_data["applied_at"] is None
    assert app_data["tailored_count"] == 0


def test_patch_only_changes_the_fields_sent(client, make_application):
    app_data = make_application(notes="keep me")

    resp = client.patch(
        f"/api/applications/{app_data['id']}", json={"role": "Staff Engineer"}
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["role"] == "Staff Engineer"
    assert body["company"] == app_data["company"]
    assert body["notes"] == "keep me"


@pytest.mark.parametrize(
    "method, path",
    [
        ("get", "/api/applications/999"),
        ("patch", "/api/applications/999"),
        ("delete", "/api/applications/999"),
        ("get", "/api/resumes/999"),
        ("put", "/api/resumes/999"),
        ("delete", "/api/resumes/999"),
        ("post", "/api/applications/999/tailor"),
        ("get", "/api/applications/999/tailored"),
        ("get", "/api/tailored/999"),
    ],
)
def test_missing_ids_return_404(client, method, path):
    resp = client.request(method, path, json={})
    assert resp.status_code == 404


def test_missing_required_field_returns_422(client):
    resp = client.post("/api/applications", json={"role": "SWE"})
    assert resp.status_code == 422


def test_unknown_status_returns_422(client):
    resp = client.post(
        "/api/applications",
        json={"company": "A", "role": "B", "status": "ghosted"},
    )
    assert resp.status_code == 422


def test_list_returns_most_recently_updated_first(client, make_application):
    older = make_application(company="Older")
    make_application(company="Newer")

    # Touching the older one moves it to the top.
    client.patch(f"/api/applications/{older['id']}", json={"notes": "touched"})

    companies = [a["company"] for a in client.get("/api/applications").json()]
    assert companies == ["Older", "Newer"]


def test_deleting_an_application_deletes_its_tailored_resumes(
    client, make_application, make_resume, fake_tailoring
):
    make_resume()
    app_data = make_application()
    tailored = client.post(
        f"/api/applications/{app_data['id']}/tailor", json={}
    ).json()

    assert client.delete(f"/api/applications/{app_data['id']}").status_code == 204
    assert client.get(f"/api/tailored/{tailored['id']}").status_code == 404
