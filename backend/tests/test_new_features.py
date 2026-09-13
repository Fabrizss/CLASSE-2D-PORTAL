"""Backend tests for new features: Google AI settings, Orario, Professore role, Direct Messages."""
import os
import uuid
import pytest
import requests

def _load_backend_url():
    v = os.environ.get("REACT_APP_BACKEND_URL")
    if v:
        return v.rstrip("/")
    try:
        with open("/app/frontend/.env") as f:
            for line in f:
                if line.startswith("REACT_APP_BACKEND_URL="):
                    return line.split("=", 1)[1].strip().rstrip("/")
    except Exception:
        pass
    raise RuntimeError("REACT_APP_BACKEND_URL not set")

BASE_URL = _load_backend_url()
API = f"{BASE_URL}/api"

ADMIN_EMAIL = "admin@noidi2d.it"
ADMIN_PASSWORD = "AdminNoi2D!"
PROF_EMAIL = "prof@noidi2d.it"
PROF_PASSWORD = "ProfNoi2D!"


def _login(email, pw):
    return requests.post(f"{API}/auth/login", json={"email": email, "password": pw}, timeout=15)


def _register(name, email, pw):
    return requests.post(f"{API}/auth/register", json={"name": name, "email": email, "password": pw}, timeout=15)


def _auth(tok):
    return {"Authorization": f"Bearer {tok}"}


@pytest.fixture(scope="module")
def admin_h():
    r = _login(ADMIN_EMAIL, ADMIN_PASSWORD)
    assert r.status_code == 200, r.text
    return _auth(r.json()["token"])


@pytest.fixture(scope="module")
def prof_h():
    r = _login(PROF_EMAIL, PROF_PASSWORD)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["user"]["role"] == "professore"
    return _auth(d["token"])


def _make_member(admin_h, prefix="dm"):
    email = f"{prefix}_{uuid.uuid4().hex[:8]}@noidi2d.it"
    pw = "MemberPass1!"
    assert _register("Test Member", email, pw).status_code == 200
    users = requests.get(f"{API}/admin/users", headers=admin_h, timeout=15).json()
    uid = next(u["id"] for u in users if u["email"] == email)
    assert requests.post(f"{API}/admin/users/{uid}/approve", headers=admin_h, timeout=15).status_code == 200
    tok = _login(email, pw).json()["token"]
    return {"email": email, "id": uid, "h": _auth(tok)}


@pytest.fixture(scope="module")
def student1(admin_h):
    return _make_member(admin_h, "stud1")


@pytest.fixture(scope="module")
def student2(admin_h):
    return _make_member(admin_h, "stud2")


# ============ Google AI Settings ============
class TestGoogleAI:
    def test_default_no_google_key(self, admin_h):
        requests.post(f"{API}/admin/ai-settings", json={"api_key": ""}, headers=admin_h, timeout=15)
        r = requests.get(f"{API}/admin/ai-settings", headers=admin_h, timeout=15)
        assert r.status_code == 200
        assert r.json().get("google_ai_configured") is False

    def test_save_google_key(self, admin_h):
        r = requests.post(f"{API}/admin/ai-settings",
                          json={"api_key": "AIzaSyFakeGoogleKey12345"}, headers=admin_h, timeout=15)
        assert r.status_code == 200, r.text
        assert r.json().get("google_ai_configured") is True
        g = requests.get(f"{API}/admin/ai-settings", headers=admin_h, timeout=15)
        assert g.json().get("google_ai_configured") is True

    def test_remove_google_key(self, admin_h):
        r = requests.post(f"{API}/admin/ai-settings", json={"api_key": ""}, headers=admin_h, timeout=15)
        assert r.status_code == 200
        assert r.json().get("google_ai_configured") is False

    def test_prof_can_access_ai_settings(self, prof_h):
        # Professore == staff, must be allowed by require_admin
        r = requests.get(f"{API}/admin/ai-settings", headers=prof_h, timeout=15)
        assert r.status_code == 200

    def test_student_forbidden(self, student1):
        r = requests.get(f"{API}/admin/ai-settings", headers=student1["h"], timeout=15)
        assert r.status_code == 403


# ============ Professore role permissions ============
class TestProfessorePermissions:
    def test_prof_can_list_users(self, prof_h):
        r = requests.get(f"{API}/admin/users", headers=prof_h, timeout=15)
        assert r.status_code == 200

    def test_prof_can_manage_orario(self, prof_h):
        r = requests.get(f"{API}/admin/orario", headers=prof_h, timeout=15)
        assert r.status_code == 200

    def test_student_admin_endpoints_forbidden(self, student1):
        for path in ["/admin/users", "/admin/orario", "/admin/ai-settings"]:
            r = requests.get(f"{API}{path}", headers=student1["h"], timeout=15)
            assert r.status_code == 403, f"{path} should be 403 for student, got {r.status_code}"


# ============ Orario ============
class TestOrario:
    def test_admin_save_definitivo(self, admin_h):
        grid = {"Lun-1": "Matematica", "Lun-2": "Italiano", "Mar-1": "Storia"}
        r = requests.post(f"{API}/admin/orario",
                          json={"type": "definitivo", "grid": grid}, headers=admin_h, timeout=15)
        assert r.status_code == 200

    def test_prof_save_settimana_with_label(self, prof_h):
        grid = {"Lun-1": "Prova"}
        r = requests.post(f"{API}/admin/orario",
                          json={"type": "settimana", "grid": grid, "week_label": "Settimana 15-19 Gen"},
                          headers=prof_h, timeout=15)
        assert r.status_code == 200

    def test_invalid_type_rejected(self, admin_h):
        r = requests.post(f"{API}/admin/orario",
                          json={"type": "invalid", "grid": {}}, headers=admin_h, timeout=15)
        assert r.status_code == 400

    def test_admin_get_all_grids(self, admin_h):
        r = requests.get(f"{API}/admin/orario", headers=admin_h, timeout=15)
        assert r.status_code == 200
        d = r.json()
        assert "grids" in d and "active_type" in d
        assert "definitivo" in d["grids"]
        assert d["grids"]["definitivo"]["grid"].get("Lun-1") == "Matematica"

    def test_set_active_orario(self, admin_h):
        r = requests.post(f"{API}/admin/orario/active",
                          json={"type": "definitivo"}, headers=admin_h, timeout=15)
        assert r.status_code == 200

    def test_public_orario_returns_active(self, student1):
        r = requests.get(f"{API}/orario", headers=student1["h"], timeout=15)
        assert r.status_code == 200
        d = r.json()
        assert d["active_type"] == "definitivo"
        assert d["grid"].get("Lun-1") == "Matematica"
        assert "my_overrides" in d
        assert isinstance(d["days"], list) and len(d["days"]) == 5
        assert isinstance(d["hours"], list) and len(d["hours"]) == 6

    def test_personal_override(self, student1, student2):
        # student1 saves personal override
        r = requests.post(f"{API}/orario/personal",
                          json={"cell": "Lun-1", "subject": "Ripasso", "note": "Portare libro"},
                          headers=student1["h"], timeout=15)
        assert r.status_code == 200
        # student1 sees their override
        g1 = requests.get(f"{API}/orario", headers=student1["h"], timeout=15).json()
        assert g1["my_overrides"].get("Lun-1", {}).get("subject") == "Ripasso"
        assert g1["my_overrides"].get("Lun-1", {}).get("note") == "Portare libro"
        # student2 does NOT see student1's override
        g2 = requests.get(f"{API}/orario", headers=student2["h"], timeout=15).json()
        assert "Lun-1" not in g2["my_overrides"]

    def test_personal_clear(self, student1):
        r = requests.post(f"{API}/orario/personal",
                          json={"cell": "Lun-1", "subject": "", "note": ""},
                          headers=student1["h"], timeout=15)
        assert r.status_code == 200
        g = requests.get(f"{API}/orario", headers=student1["h"], timeout=15).json()
        assert "Lun-1" not in g["my_overrides"]


# ============ Direct Messages ============
class TestDirectMessages:
    def test_staff_sees_all_students(self, prof_h, student1, student2):
        r = requests.get(f"{API}/dm/contacts", headers=prof_h, timeout=15)
        assert r.status_code == 200
        ids = [c["id"] for c in r.json()]
        assert student1["id"] in ids
        assert student2["id"] in ids

    def test_prof_sends_to_student(self, prof_h, student1):
        r = requests.post(f"{API}/dm/messages/{student1['id']}",
                          json={"text": "Ciao, come vanno gli studi?"}, headers=prof_h, timeout=15)
        assert r.status_code == 200, r.text
        assert r.json()["text"] == "Ciao, come vanno gli studi?"

    def test_student_sees_prof_in_contacts_after_dm(self, prof_h, student1):
        # Ensure at least one message from prof to student1
        requests.post(f"{API}/dm/messages/{student1['id']}",
                      json={"text": "Ciao"}, headers=prof_h, timeout=15)
        r = requests.get(f"{API}/dm/contacts", headers=student1["h"], timeout=15)
        assert r.status_code == 200
        contacts = r.json()
        assert any(c["role"] == "professore" for c in contacts)

    def test_student_replies_to_prof(self, prof_h, student1):
        # Ensure thread exists
        requests.post(f"{API}/dm/messages/{student1['id']}",
                      json={"text": "hey"}, headers=prof_h, timeout=15)
        # student1 fetches prof id via contacts
        contacts = requests.get(f"{API}/dm/contacts", headers=student1["h"], timeout=15).json()
        prof_id = next(c["id"] for c in contacts if c["role"] == "professore")
        r = requests.post(f"{API}/dm/messages/{prof_id}",
                          json={"text": "Va bene grazie"}, headers=student1["h"], timeout=15)
        assert r.status_code == 200

    def test_thread_messages_retrieved(self, prof_h, student1):
        r = requests.get(f"{API}/dm/messages/{student1['id']}", headers=prof_h, timeout=15)
        assert r.status_code == 200
        msgs = r.json()
        assert isinstance(msgs, list)
        assert len(msgs) >= 1

    def test_student_to_student_forbidden(self, student1, student2):
        r = requests.get(f"{API}/dm/messages/{student2['id']}", headers=student1["h"], timeout=15)
        assert r.status_code == 403
        r2 = requests.post(f"{API}/dm/messages/{student2['id']}",
                           json={"text": "ciao"}, headers=student1["h"], timeout=15)
        assert r2.status_code == 403

    def test_staff_to_staff_forbidden(self, prof_h, admin_h):
        # get admin id
        admin_me = requests.get(f"{API}/auth/me", headers=admin_h, timeout=15).json()
        r = requests.post(f"{API}/dm/messages/{admin_me['id']}",
                          json={"text": "ciao collega"}, headers=prof_h, timeout=15)
        assert r.status_code == 403

    def test_empty_message_rejected(self, prof_h, student1):
        r = requests.post(f"{API}/dm/messages/{student1['id']}",
                          json={"text": "   "}, headers=prof_h, timeout=15)
        assert r.status_code == 400

    def test_dm_unknown_user(self, prof_h):
        r = requests.post(f"{API}/dm/messages/nonexistent-id",
                          json={"text": "hi"}, headers=prof_h, timeout=15)
        assert r.status_code == 404


# ============ Regression: AI still works with default (Gemini via Emergent key) ============
class TestRegressionAI:
    def test_flashcards_default(self, admin_h):
        requests.post(f"{API}/admin/ai-settings", json={"api_key": ""}, headers=admin_h, timeout=15)
        r = requests.post(f"{API}/study/flashcards",
                          json={"topic": "matematica base", "count": 2}, headers=admin_h, timeout=60)
        assert r.status_code == 200, r.text[:400]
        cards = r.json().get("cards", [])
        assert isinstance(cards, list) and len(cards) >= 1
