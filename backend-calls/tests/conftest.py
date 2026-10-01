import os

# Must be set before the app is imported.
os.environ.setdefault("DATABASE_URL", "sqlite://")
os.environ["JWT_SECRET"] = "test-secret"
os.environ["DEV_MODE"] = "true"
os.environ["DEV_OTP"] = "123456"
os.environ["TWILIO_AUTH_TOKEN"] = ""          # webhooks unsigned in tests
os.environ["BASE_URL"] = "https://example.test"
os.environ["ACK_WINDOW_SECONDS"] = "60"
os.environ["CANCEL_WINDOW_SECONDS"] = "0"

import pytest
from fastapi.testclient import TestClient

from app import notify
from app.db import Base, SessionLocal, engine
from app.main import app


class FakeNotifier(notify.Notifier):
    """Records every push/call/sms instead of sending it."""

    def __init__(self):
        super().__init__()
        self.pushes, self.calls, self.sms_sent, self.emails = [], [], [], []
        self.bad_tokens: set[str] = set()
        self.fail_calls = False
        self._n = 0

    def _ref(self, kind):
        self._n += 1
        return f"{kind}{self._n}"

    def push(self, token, data):
        if token in self.bad_tokens:
            raise notify.InvalidPushToken("unregistered")
        self.pushes.append((token, data))
        return self._ref("push")

    def call(self, to, voice_url, status_url):
        if self.fail_calls:
            raise RuntimeError("twilio down")
        self.calls.append((to, voice_url, status_url))
        return self._ref("CA")

    def sms(self, to, text):
        self.sms_sent.append((to, text))
        return self._ref("SM")

    def email(self, to, subject, body):
        self.emails.append((to, subject, body))


@pytest.fixture(autouse=True)
def fresh_db():
    from app import models  # noqa: F401

    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield


@pytest.fixture
def fake():
    f = FakeNotifier()
    notify.set_notifier(f)
    return f


@pytest.fixture
def client(fake):
    with TestClient(app) as c:
        yield c


@pytest.fixture
def db():
    s = SessionLocal()
    yield s
    s.close()


def login(client, phone, email, role, name=None):
    r = client.post("/auth/request-otp", json={"phone": phone, "email": email})
    assert r.status_code == 200, r.text
    r = client.post("/auth/verify", json={"phone": phone, "email": email, "otp_phone": "123456",
                                          "otp_email": "123456", "role": role, "name": name})
    assert r.status_code == 200, r.text
    d = r.json()
    return {"Authorization": f"Bearer {d['token']}"}, d


@pytest.fixture
def family_setup(client, fake):
    """Lakshmi (patient) + Arjun (approve, first) + Meera (approve) + Ravi (view only), each with a phone."""
    pat, pd = login(client, "9876500001", "lakshmi@x.in", "patient", "Lakshmi")
    r = client.post("/members", headers=pat, json={"name": "Arjun", "phone": "9876500002", "email": "arjun@x.in", "relation": "son"})
    assert r.status_code == 201, r.text
    arjun, ad = login(client, "9876500002", "arjun@x.in", "family")
    for name, ph, perm in [("Meera", "9876500003", "approve"), ("Ravi", "9876500004", "view")]:
        r = client.post("/members", headers=arjun, json={"name": name, "phone": ph, "email": f"{name.lower()}@x.in", "relation": "other", "permission": perm})
        assert r.status_code == 201, r.text
    meera, md = login(client, "9876500003", "meera@x.in", "family")
    ravi, rd = login(client, "9876500004", "ravi@x.in", "family")
    for h, tok in [(arjun, "tok-arjun-0000000"), (meera, "tok-meera-0000000"), (ravi, "tok-ravi-00000000"), (pat, "tok-lakshmi-000000")]:
        assert client.put("/devices", headers=h, json={"fcm_token": tok}).status_code == 200
    fake.pushes.clear(); fake.calls.clear(); fake.sms_sent.clear(); fake.emails.clear()   # forget the login OTPs
    return dict(pat=pat, arjun=arjun, meera=meera, ravi=ravi, ids=dict(pat=pd["user_id"], arjun=ad["user_id"], meera=md["user_id"], ravi=rd["user_id"]), case=pd["case_id"])
