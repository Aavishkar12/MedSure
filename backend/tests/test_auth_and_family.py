from tests.conftest import login


def test_wrong_codes_rejected(client):
    client.post("/auth/request-otp", json={"phone": "9876500001", "email": "a@x.in"})
    r = client.post("/auth/verify", json={"phone": "9876500001", "email": "a@x.in", "otp_phone": "000000",
                                          "otp_email": "000000", "role": "patient"})
    assert r.status_code == 400


def test_both_codes_required(client):
    client.post("/auth/request-otp", json={"phone": "9876500001", "email": "a@x.in"})
    # right dev code for SMS but a wrong email code is not enough (dev code is accepted for both, so use real mismatch)
    r = client.post("/auth/verify", json={"phone": "9876500001", "email": "a@x.in", "otp_phone": "123456",
                                          "otp_email": "999999", "role": "patient"})
    assert r.status_code == 400


def test_otp_sent_to_phone_and_email(client, fake):
    client.post("/auth/request-otp", json={"phone": "98765 00001", "email": "A@X.in"})
    assert fake.sms_sent[0][0] == "+919876500001"
    assert fake.emails[0][0] == "a@x.in"


def test_family_cannot_login_without_invite(client):
    client.post("/auth/request-otp", json={"phone": "9876599999", "email": "z@x.in"})
    r = client.post("/auth/verify", json={"phone": "9876599999", "email": "z@x.in", "otp_phone": "123456",
                                          "otp_email": "123456", "role": "family"})
    assert r.status_code == 404


def test_patient_can_add_only_one_member(client):
    pat, _ = login(client, "9876500001", "l@x.in", "patient", "Lakshmi")
    ok = client.post("/members", headers=pat, json={"name": "Arjun", "phone": "9876500002", "email": "arjun@x.in"})
    assert ok.status_code == 201 and ok.json()["permission"] == "approve"
    again = client.post("/members", headers=pat, json={"name": "Meera", "phone": "9876500003", "email": "m@x.in"})
    assert again.status_code == 403


def test_family_with_approve_can_invite_more_but_view_only_cannot(client, family_setup):
    f = family_setup
    r = client.post("/members", headers=f["arjun"], json={"name": "Dev", "phone": "9876500005", "email": "dev@x.in", "permission": "view"})
    assert r.status_code == 201
    r = client.post("/members", headers=f["ravi"], json={"name": "Nope", "phone": "9876500006", "email": "n@x.in"})
    assert r.status_code == 403


def test_patient_cannot_use_family_only_actions(client, family_setup):
    f = family_setup
    r = client.post("/checkins", headers=f["arjun"], json={"breathing": "normal", "swelling": "none", "medicine": "none"})
    assert r.status_code == 403  # only the patient submits check-ins


def test_stranger_cannot_read_alert(client, family_setup):
    f = family_setup
    r = client.post("/checkins", headers=f["pat"], json={"breathing": "hard_resting", "swelling": "none", "medicine": "none"})
    alert_id = r.json()["alert_id"]
    other, _ = login(client, "9000000001", "o@x.in", "patient", "Other")
    assert client.get(f"/alerts/{alert_id}", headers=other).status_code == 403
