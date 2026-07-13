"""Backend API tests for NOI DI 2D portal."""
import os
import time
import uuid
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://class-connect-2d.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"

ADMIN_EMAIL = "admin@noidi2d.it"
ADMIN_PASSWORD = "AdminNoi2D!"


# ---------------- fixtures ----------------
@pytest.fixture(scope="session")
def admin_token():
    r = requests.post(f"{API}/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}, timeout=15)
    assert r.status_code == 200, f"Admin login failed: {r.status_code} {r.text}"
    data = r.json()
    assert "token" in data
    assert data["user"]["role"] == "admin"
    return data["token"]


@pytest.fixture(scope="session")
def admin_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}"}


def _register(name, email, password):
    return requests.post(f"{API}/auth/register", json={"name": name, "email": email, "password": password}, timeout=15)


def _login(email, password):
    return requests.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=15)


@pytest.fixture(scope="session")
def member_creds():
    """Register + approve a fresh member. Returns (email, password, token, user_id)."""
    email = f"test_member_{uuid.uuid4().hex[:8]}@noidi2d.it"
    password = "MemberPass123!"
    r = _register("Test Member", email, password)
    assert r.status_code == 200, f"register failed: {r.text}"

    # login must be blocked (pending)
    r2 = _login(email, password)
    assert r2.status_code == 403, f"pending login should be 403 got {r2.status_code}"

    # admin approves
    admin = _login(ADMIN_EMAIL, ADMIN_PASSWORD).json()
    admin_h = {"Authorization": f"Bearer {admin['token']}"}
    users = requests.get(f"{API}/admin/users", headers=admin_h, timeout=15).json()
    uid = next(u["id"] for u in users if u["email"] == email)
    ap = requests.post(f"{API}/admin/users/{uid}/approve", headers=admin_h, timeout=15)
    assert ap.status_code == 200

    r3 = _login(email, password)
    assert r3.status_code == 200, f"approved login failed: {r3.text}"
    tok = r3.json()["token"]
    return {"email": email, "password": password, "token": tok, "id": uid}


@pytest.fixture(scope="session")
def member_headers(member_creds):
    return {"Authorization": f"Bearer {member_creds['token']}"}


@pytest.fixture(scope="session")
def member2_creds():
    """Second approved member for P2P actions."""
    email = f"test_member2_{uuid.uuid4().hex[:8]}@noidi2d.it"
    password = "MemberPass123!"
    _register("Test Member2", email, password)
    admin = _login(ADMIN_EMAIL, ADMIN_PASSWORD).json()
    admin_h = {"Authorization": f"Bearer {admin['token']}"}
    users = requests.get(f"{API}/admin/users", headers=admin_h, timeout=15).json()
    uid = next(u["id"] for u in users if u["email"] == email)
    requests.post(f"{API}/admin/users/{uid}/approve", headers=admin_h, timeout=15)
    tok = _login(email, password).json()["token"]
    return {"email": email, "password": password, "token": tok, "id": uid}


# ---------------- health / auth ----------------
class TestAuth:
    def test_root(self):
        r = requests.get(f"{API}/", timeout=15)
        assert r.status_code == 200
        assert "message" in r.json()

    def test_admin_login_success(self, admin_token):
        assert isinstance(admin_token, str) and len(admin_token) > 20

    def test_admin_me(self, admin_headers):
        r = requests.get(f"{API}/auth/me", headers=admin_headers, timeout=15)
        assert r.status_code == 200
        me = r.json()
        assert me["role"] == "admin"
        assert me["status"] == "approved"
        assert me["email"] == ADMIN_EMAIL

    def test_wrong_password(self):
        r = _login(ADMIN_EMAIL, "wrong")
        assert r.status_code == 401

    def test_register_and_pending_blocks_login(self):
        email = f"pending_{uuid.uuid4().hex[:8]}@noidi2d.it"
        pw = "PendingPass1!"
        r = _register("Pending", email, pw)
        assert r.status_code == 200
        r2 = _login(email, pw)
        assert r2.status_code == 403
        assert "attesa" in r2.json().get("detail", "").lower()

    def test_duplicate_email(self):
        email = f"dup_{uuid.uuid4().hex[:8]}@noidi2d.it"
        r1 = _register("Dup", email, "PassPass1!")
        assert r1.status_code == 200
        r2 = _register("Dup", email, "PassPass1!")
        assert r2.status_code == 400


# ---------------- admin panel ----------------
class TestAdmin:
    def test_list_users_admin(self, admin_headers):
        r = requests.get(f"{API}/admin/users", headers=admin_headers, timeout=15)
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_non_admin_cannot_list(self, member_headers):
        r = requests.get(f"{API}/admin/users", headers=member_headers, timeout=15)
        assert r.status_code == 403

    def test_authorize_events_toggle(self, admin_headers, member_creds):
        uid = member_creds["id"]
        r = requests.post(f"{API}/admin/users/{uid}/authorize/1", headers=admin_headers, timeout=15)
        assert r.status_code == 200
        users = requests.get(f"{API}/admin/users", headers=admin_headers, timeout=15).json()
        target = next(u for u in users if u["id"] == uid)
        assert target["can_create_events"] is True
        # toggle off
        r2 = requests.post(f"{API}/admin/users/{uid}/authorize/0", headers=admin_headers, timeout=15)
        assert r2.status_code == 200
        users = requests.get(f"{API}/admin/users", headers=admin_headers, timeout=15).json()
        target = next(u for u in users if u["id"] == uid)
        assert target["can_create_events"] is False

    def test_role_change(self, admin_headers, member2_creds):
        uid = member2_creds["id"]
        r = requests.post(f"{API}/admin/users/{uid}/role/admin", headers=admin_headers, timeout=15)
        assert r.status_code == 200
        users = requests.get(f"{API}/admin/users", headers=admin_headers, timeout=15).json()
        assert next(u for u in users if u["id"] == uid)["role"] == "admin"
        # revert
        requests.post(f"{API}/admin/users/{uid}/role/member", headers=admin_headers, timeout=15)


# ---------------- events ----------------
class TestEvents:
    created_id = None

    def test_admin_create_event(self, admin_headers):
        payload = {
            "title": "TEST_Evento Urgente",
            "description": "Descrizione di test",
            "urgency": "urgente",
            "location": "Aula 2D",
        }
        r = requests.post(f"{API}/events", json=payload, headers=admin_headers, timeout=15)
        assert r.status_code == 200, r.text
        ev = r.json()
        assert ev["title"] == payload["title"]
        assert ev["urgency"] == "urgente"
        assert ev["signup_count"] == 0
        TestEvents.created_id = ev["id"]

    def test_event_appears_in_list(self, member_headers):
        r = requests.get(f"{API}/events", headers=member_headers, timeout=15)
        assert r.status_code == 200
        assert any(e["id"] == TestEvents.created_id for e in r.json())

    def test_member_signup(self, member_headers):
        r = requests.post(f"{API}/events/{TestEvents.created_id}/signup", headers=member_headers, timeout=15)
        assert r.status_code == 200
        d = r.json()
        assert d["signed_up"] is True
        assert d["signup_count"] == 1

    def test_signup_persisted(self, member_headers):
        r = requests.get(f"{API}/events", headers=member_headers, timeout=15)
        ev = next(e for e in r.json() if e["id"] == TestEvents.created_id)
        assert ev["signed_up"] is True
        assert ev["signup_count"] == 1

    def test_member_cannot_create_event(self, member_headers):
        r = requests.post(f"{API}/events", json={"title": "nope", "description": "no"}, headers=member_headers, timeout=15)
        assert r.status_code == 403

    def test_authorized_member_can_create(self, admin_headers, member_headers, member_creds):
        uid = member_creds["id"]
        requests.post(f"{API}/admin/users/{uid}/authorize/1", headers=admin_headers, timeout=15)
        r = requests.post(f"{API}/events", json={"title": "TEST_by_member", "description": "d", "urgency": "bassa"},
                         headers=member_headers, timeout=15)
        assert r.status_code == 200
        eid = r.json()["id"]
        # cleanup
        d = requests.delete(f"{API}/events/{eid}", headers=member_headers, timeout=15)
        assert d.status_code == 200
        requests.post(f"{API}/admin/users/{uid}/authorize/0", headers=admin_headers, timeout=15)

    def test_delete_event(self, admin_headers):
        r = requests.delete(f"{API}/events/{TestEvents.created_id}", headers=admin_headers, timeout=15)
        assert r.status_code == 200
        # verify not in list
        r2 = requests.get(f"{API}/events", headers=admin_headers, timeout=15)
        assert not any(e["id"] == TestEvents.created_id for e in r2.json())


# ---------------- chat ----------------
class TestChat:
    def test_post_and_get_message(self, member_headers):
        text = f"TEST_hello_{uuid.uuid4().hex[:6]}"
        r = requests.post(f"{API}/chat/messages", json={"text": text}, headers=member_headers, timeout=15)
        assert r.status_code == 200
        msg = r.json()
        assert msg["text"] == text
        assert msg["censored"] is False

        r2 = requests.get(f"{API}/chat/messages", headers=member_headers, timeout=15)
        assert r2.status_code == 200
        assert any(m["id"] == msg["id"] for m in r2.json())

    def test_bad_word_censored(self, member_headers):
        text = "questo è un cazzo di test"
        r = requests.post(f"{API}/chat/messages", json={"text": text}, headers=member_headers, timeout=15)
        assert r.status_code == 200
        msg = r.json()
        assert msg["censored"] is True
        assert "cazzo" not in msg["text"].lower()
        assert "*" in msg["text"]

    def test_empty_message(self, member_headers):
        r = requests.post(f"{API}/chat/messages", json={"text": "   "}, headers=member_headers, timeout=15)
        assert r.status_code == 400


# ---------------- P2P actions ----------------
class TestActions:
    def test_send_action(self, member_headers, member2_creds):
        r = requests.post(f"{API}/actions",
                          json={"to_user_id": member2_creds["id"], "type": "cuore"},
                          headers=member_headers, timeout=15)
        assert r.status_code == 200, r.text
        assert r.json()["ok"] is True

    def test_antispam_429(self, member_headers, member2_creds):
        # immediate second send should be blocked
        r = requests.post(f"{API}/actions",
                          json={"to_user_id": member2_creds["id"], "type": "pizza"},
                          headers=member_headers, timeout=15)
        assert r.status_code == 429, f"expected 429 got {r.status_code}"

    def test_inbox_receives(self, member2_creds):
        h = {"Authorization": f"Bearer {member2_creds['token']}"}
        r = requests.get(f"{API}/actions/inbox", headers=h, timeout=15)
        assert r.status_code == 200
        inbox = r.json()
        assert isinstance(inbox, list)
        assert any(a["type"] == "cuore" for a in inbox)

        # second call inbox is empty (marked seen)
        r2 = requests.get(f"{API}/actions/inbox", headers=h, timeout=15)
        assert len(r2.json()) == 0

    def test_invalid_action_type(self, member_headers, member2_creds):
        time.sleep(5)  # wait past antispam window
        r = requests.post(f"{API}/actions",
                          json={"to_user_id": member2_creds["id"], "type": "bomb"},
                          headers=member_headers, timeout=15)
        assert r.status_code == 400


# ---------------- push ----------------
class TestPush:
    def test_vapid_public(self):
        r = requests.get(f"{API}/push/vapid-public", timeout=15)
        assert r.status_code == 200
        d = r.json()
        assert "key" in d
        assert d["key"] and len(d["key"]) > 40


# ---------------- study AI (may be slow) ----------------
class TestStudy:
    @pytest.mark.timeout(60)
    def test_flashcards_from_topic(self, member_headers):
        r = requests.post(f"{API}/study/flashcards",
                          json={"topic": "La Divina Commedia di Dante", "count": 3},
                          headers=member_headers, timeout=60)
        assert r.status_code == 200, f"{r.status_code} {r.text[:400]}"
        cards = r.json()["cards"]
        assert isinstance(cards, list) and len(cards) >= 1
        assert "q" in cards[0] and "a" in cards[0]

    @pytest.mark.timeout(60)
    def test_study_chat(self, member_headers):
        session_id = f"test-{uuid.uuid4().hex[:8]}"
        r = requests.post(f"{API}/study/chat",
                          json={"session_id": session_id, "message": "Inizia interrogazione", "subject": "storia"},
                          headers=member_headers, timeout=60)
        assert r.status_code == 200, f"{r.status_code} {r.text[:400]}"
        assert isinstance(r.json()["reply"], str) and len(r.json()["reply"]) > 5
