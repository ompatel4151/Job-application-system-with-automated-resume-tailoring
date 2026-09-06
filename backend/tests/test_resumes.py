def test_create_and_list_resume(client, make_resume):
    resume = make_resume()
    assert resume["is_default"] is True
    assert resume["content"]["full_name"] == "Om Patel"

    resp = client.get("/api/resumes")
    assert len(resp.json()) == 1


def test_only_one_default_resume(client, make_resume):
    first = make_resume(name="First")
    second = make_resume(name="Second")

    resumes = {r["name"]: r for r in client.get("/api/resumes").json()}
    assert resumes["First"]["is_default"] is False
    assert resumes["Second"]["is_default"] is True
    assert first["id"] != second["id"]


def test_make_default_via_update(client, make_resume):
    first = make_resume(name="First")
    make_resume(name="Second")

    resp = client.put(f"/api/resumes/{first['id']}", json={"is_default": True})
    assert resp.status_code == 200
    resumes = {r["name"]: r for r in client.get("/api/resumes").json()}
    assert resumes["First"]["is_default"] is True
    assert resumes["Second"]["is_default"] is False


def test_update_resume_content(client, make_resume, sample_resume_content):
    resume = make_resume()
    sample_resume_content["skills"].append("Docker")
    resp = client.put(
        f"/api/resumes/{resume['id']}", json={"content": sample_resume_content}
    )
    assert resp.status_code == 200
    assert "Docker" in resp.json()["content"]["skills"]


def test_delete_resume(client, make_resume):
    resume = make_resume()
    assert client.delete(f"/api/resumes/{resume['id']}").status_code == 204
    assert client.get(f"/api/resumes/{resume['id']}").status_code == 404
