"""Known issues from AUDIT.md, written as tests of the behavior we WANT.

Each test is marked xfail(strict=True): it is expected to fail today.
- While the bug exists, pytest reports it as "xfailed" and the suite stays green.
- strict=True means that once a milestone fixes the bug, the test starts
  passing, pytest reports that as a failure ("XPASS(strict)"), and that forces
  us to delete the marker and keep the test as a normal regression test.
"""

import pytest


@pytest.mark.xfail(
    strict=True,
    reason="AUDIT #4: explicit null reaches the DB, NOT NULL fails, 500. Fix in milestone 4.",
)
def test_patch_null_on_required_field_returns_422(client, make_application):
    """AUDIT #4: an explicit null on a required field should be rejected."""
    app_data = make_application()

    resp = client.patch(f"/api/applications/{app_data['id']}", json={"company": None})

    assert resp.status_code == 422
