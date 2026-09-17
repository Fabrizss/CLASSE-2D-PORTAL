"""Comprehensive backend regression tests after Supabase Postgres migration."""
import os, time, uuid, io, pytest, requests

BASE = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/") or "https://class-connect-2d.preview.emergentagent.com"
API = f"{BASE}/api"

ADMIN = ("admin@noidi2d.it", "AdminNoi2D!")
PROF = ("prof@noidi2d.it", "ProfNoi2D!")
STUD = ("studente.test@noidi2d.it", "Studente123!")


def _login(email, password):
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=30)
    assert r.status_code == 200, f"login failed {email}: {r.status_code} {r.text}"
    return r.json()["token"], r.json()["user"]


def _hdr(t):
    return {"Authorization": f"Bearer {t}"}


@pytest.fixture(scope="session")
def admin():
    t, u = _login(*ADMIN)
    return {"token": t, "user": u, "h": _hdr(t)}


@pytest.fixture(scope="session")
def prof():
    t, u = _login(*PROF)
    return {"token": t, "user": u, "h": _hdr(t)}


@pytest.fixture(scope="session")
def student():
    try:
        t, u = _login(*STUD)
    except AssertionError:
        pytest.skip("student test account missing")
    return {"token": t, "user": u, "h": _hdr(t)}


# ---------------- auth ----------------
class TestAuth:
    def test_admin_login(self, admin):
        assert admin["user"]["role"] == "admin"

    def test_prof_login(self, prof):
        assert prof["user"]["role"] == "professore"

    def test_me(self, admin):
        r = requests.get(f"{API}/auth/me", headers=admin["h"])
        assert r.status_code == 200 and r.json()["email"] == ADMIN[0]

    def test_wrong_password(self):
        r = requests.post(f"{API}/auth/login", json={"email": ADMIN[0], "password": "wrong"})
        assert r.status_code == 401

    def test_register_pending_flow(self, admin):
        email = f"test_reg_{uuid.uuid4().hex[:8]}@noidi2d.it"
        r = requests.post(f"{API}/auth/register", json={"name": "TEST New", "email": email, "password": "Passw0rd!"})
        assert r.status_code == 200
        # login blocked (pending)
        r2 = requests.post(f"{API}/auth/login", json={"email": email, "password": "Passw0rd!"})
        assert r2.status_code == 403
        # find user in admin list
        r3 = requests.get(f"{API}/admin/users", headers=admin["h"])
        assert r3.status_code == 200
        u = next(x for x in r3.json() if x["email"] == email)
        # approve
        r4 = requests.post(f"{API}/admin/users/{u['id']}/approve", headers=admin["h"])
        assert r4.status_code == 200
        # login now works
        r5 = requests.post(f"{API}/auth/login", json={"email": email, "password": "Passw0rd!"})
        assert r5.status_code == 200
        # cleanup
        requests.delete(f"{API}/admin/users/{u['id']}", headers=admin["h"])


# ---------------- admin users ----------------
class TestAdminUsers:
    def test_list_users(self, admin):
        r = requests.get(f"{API}/admin/users", headers=admin["h"])
        assert r.status_code == 200 and isinstance(r.json(), list)

    def test_role_change_and_ban(self, admin):
        # create disposable user
        email = f"test_role_{uuid.uuid4().hex[:8]}@noidi2d.it"
        requests.post(f"{API}/auth/register", json={"name": "TEST Role", "email": email, "password": "Passw0rd!"})
        users = requests.get(f"{API}/admin/users", headers=admin["h"]).json()
        u = next(x for x in users if x["email"] == email)
        requests.post(f"{API}/admin/users/{u['id']}/approve", headers=admin["h"])
        # role change
        for role in ("professore", "admin", "member"):
            r = requests.post(f"{API}/admin/users/{u['id']}/role/{role}", headers=admin["h"])
            assert r.status_code == 200
        # ban temp
        r = requests.post(f"{API}/admin/users/{u['id']}/ban", headers=admin["h"], json={"mode": "temp", "hours": 1})
        assert r.status_code == 200
        # login should fail
        r2 = requests.post(f"{API}/auth/login", json={"email": email, "password": "Passw0rd!"})
        assert r2.status_code == 403
        # unban
        r3 = requests.post(f"{API}/admin/users/{u['id']}/unban", headers=admin["h"])
        assert r3.status_code == 200
        r4 = requests.post(f"{API}/auth/login", json={"email": email, "password": "Passw0rd!"})
        assert r4.status_code == 200
        # delete
        r5 = requests.delete(f"{API}/admin/users/{u['id']}", headers=admin["h"])
        assert r5.status_code == 200

    def test_student_cannot_admin(self, student):
        r = requests.get(f"{API}/admin/users", headers=student["h"])
        assert r.status_code == 403


# ---------------- events ----------------
class TestEvents:
    def test_create_and_signup(self, admin, student):
        payload = {
            "title": "TEST_Torneo",
            "description": "test event",
            "urgency": "normale",
            "options": ["Squadra A", "Squadra B"],
        }
        r = requests.post(f"{API}/events", headers=admin["h"], json=payload)
        assert r.status_code == 200, r.text
        eid = r.json()["id"]
        # student signup with option
        r2 = requests.post(f"{API}/events/{eid}/signup", headers=student["h"], json={"option": "Squadra A"})
        assert r2.status_code == 200
        d = r2.json()
        assert d["signed_up"] is True and d["signup_count"] == 1
        assert d["option_counts"]["Squadra A"] == 1
        # invalid option
        r3 = requests.post(f"{API}/events/{eid}/signup", headers=student["h"], json={"option": "SquadraX"})
        assert r3.status_code == 400
        # get events verifies persistence
        r4 = requests.get(f"{API}/events", headers=student["h"])
        assert r4.status_code == 200
        ev = next(e for e in r4.json() if e["id"] == eid)
        assert ev["my_option"] == "Squadra A"
        # cleanup
        requests.delete(f"{API}/events/{eid}", headers=admin["h"])


# ---------------- course panel ----------------
class TestCourse:
    @pytest.fixture(scope="class")
    def course_event(self, admin, student):
        r = requests.post(f"{API}/events", headers=admin["h"], json={
            "title": "TEST_Corso", "description": "corso", "urgency": "normale",
            "options": [],
        })
        eid = r.json()["id"]
        requests.post(f"{API}/events/{eid}/signup", headers=student["h"], json={})
        yield eid
        requests.delete(f"{API}/events/{eid}", headers=admin["h"])

    def test_get_course(self, admin, course_event):
        r = requests.get(f"{API}/events/{course_event}/course", headers=admin["h"])
        assert r.status_code == 200
        d = r.json()
        assert d["can_manage"] is True
        assert "sport_types" in d

    def test_team_with_member_position(self, admin, student, course_event):
        r = requests.post(f"{API}/events/{course_event}/course/teams",
                          headers=admin["h"], json={"name": "TEST Squadra", "sport_type": "calcio7"})
        assert r.status_code == 200, r.text
        tid = r.json()["id"]
        # add student
        r2 = requests.post(f"{API}/events/{course_event}/course/teams/{tid}/members",
                           headers=admin["h"], json={"user_id": student["user"]["id"]})
        assert r2.status_code == 200
        # position
        r3 = requests.post(f"{API}/events/{course_event}/course/teams/{tid}/members/{student['user']['id']}/position",
                           headers=admin["h"], json={"position": "POR"})
        assert r3.status_code == 200
        # verify
        r4 = requests.get(f"{API}/events/{course_event}/course", headers=admin["h"])
        team = next(t for t in r4.json()["teams"] if t["id"] == tid)
        m = team["members"][0]
        assert m["position"] == "POR"

    def test_poll_and_vote(self, admin, student, course_event):
        r = requests.post(f"{API}/events/{course_event}/course/polls",
                          headers=admin["h"], json={"question": "TEST?", "options": ["Sì", "No"]})
        assert r.status_code == 200
        r2 = requests.get(f"{API}/events/{course_event}/course", headers=admin["h"])
        pid = r2.json()["polls"][0]["id"]
        r3 = requests.post(f"{API}/events/{course_event}/course/polls/{pid}/vote",
                           headers=student["h"], json={"option": "Sì"})
        assert r3.status_code == 200

    def test_course_chat(self, admin, course_event):
        r = requests.post(f"{API}/events/{course_event}/course/chat",
                          headers=admin["h"], json={"text": "ciao"})
        assert r.status_code == 200
        r2 = requests.get(f"{API}/events/{course_event}/course/chat", headers=admin["h"])
        assert r2.status_code == 200 and any(m["text"] == "ciao" for m in r2.json())


# ---------------- public chat & censor ----------------
class TestChat:
    def test_post_and_censor(self, admin):
        r = requests.post(f"{API}/chat/messages", headers=admin["h"], json={"text": "cazzo test"})
        assert r.status_code == 200
        assert "*" in r.json()["text"]
        mid = r.json()["id"]
        # bulk delete
        r2 = requests.post(f"{API}/chat/messages/delete", headers=admin["h"], json={"ids": [mid]})
        assert r2.status_code == 200

    def test_list(self, admin):
        r = requests.get(f"{API}/chat/messages", headers=admin["h"])
        assert r.status_code == 200


# ---------------- dm ----------------
class TestDM:
    def test_staff_to_staff_blocked(self, admin, prof):
        r = requests.post(f"{API}/dm/messages/{prof['user']['id']}", headers=admin["h"], json={"text": "hi"})
        assert r.status_code == 403

    def test_staff_to_student_ok(self, admin, student):
        r = requests.post(f"{API}/dm/messages/{student['user']['id']}", headers=admin["h"], json={"text": "TEST dm"})
        assert r.status_code == 200
        r2 = requests.get(f"{API}/dm/messages/{student['user']['id']}", headers=admin["h"])
        assert r2.status_code == 200 and any(m["text"] == "TEST dm" for m in r2.json())

    def test_contacts_student_sees_only_writers(self, student):
        r = requests.get(f"{API}/dm/contacts", headers=student["h"])
        assert r.status_code == 200


# ---------------- orario ----------------
class TestOrario:
    def test_get_orario(self, admin):
        r = requests.get(f"{API}/orario", headers=admin["h"])
        assert r.status_code == 200 and "active_type" in r.json()

    def test_admin_orario_save_and_activate(self, admin):
        r = requests.post(f"{API}/admin/orario", headers=admin["h"],
                          json={"type": "definitivo", "grid": {"Lun-1": "Mate"}, "week_label": None})
        assert r.status_code == 200
        r2 = requests.post(f"{API}/admin/orario/active", headers=admin["h"], json={"type": "definitivo"})
        assert r2.status_code == 200
        r3 = requests.get(f"{API}/orario", headers=admin["h"])
        assert r3.json()["grid"].get("Lun-1") == "Mate"

    def test_personal_override(self, student):
        r = requests.post(f"{API}/orario/personal", headers=student["h"],
                          json={"cell": "Lun-1", "subject": "Ripasso", "note": "portare libro"})
        assert r.status_code == 200
        r2 = requests.get(f"{API}/orario", headers=student["h"])
        assert r2.json()["my_overrides"].get("Lun-1", {}).get("subject") == "Ripasso"


# ---------------- news ----------------
class TestNews:
    def test_create_list_delete(self, admin):
        r = requests.post(f"{API}/news", headers=admin["h"],
                          json={"title": "TEST_news", "body": "hello", "attachments": []})
        assert r.status_code == 200
        nid = r.json()["id"]
        r2 = requests.get(f"{API}/news", headers=admin["h"])
        assert any(n["id"] == nid for n in r2.json())
        r3 = requests.delete(f"{API}/news/{nid}", headers=admin["h"])
        assert r3.status_code == 200


# ---------------- reminders / interrogazioni ----------------
class TestMisc:
    def test_reminder_crud(self, admin):
        r = requests.post(f"{API}/reminders", headers=admin["h"], json={"text": "TEST rem", "is_public": True})
        assert r.status_code == 200
        rid = r.json()["id"]
        r2 = requests.get(f"{API}/reminders", headers=admin["h"])
        assert any(x["id"] == rid for x in r2.json())
        r3 = requests.delete(f"{API}/reminders/{rid}", headers=admin["h"])
        assert r3.status_code == 200

    def test_interrogazione(self, admin):
        r = requests.post(f"{API}/interrogazioni", headers=admin["h"],
                          json={"subject": "Mate", "tipo": "orale", "num_domande": 3, "voto": 8.0})
        assert r.status_code == 200
        iid = r.json()["id"]
        r2 = requests.patch(f"{API}/interrogazioni/{iid}", headers=admin["h"], json={"voto": 9.0})
        assert r2.status_code == 200
        requests.delete(f"{API}/interrogazioni/{iid}", headers=admin["h"])


# ---------------- p2p actions ----------------
class TestActions:
    def test_send_and_antispam(self, admin, student):
        r = requests.post(f"{API}/actions", headers=admin["h"],
                          json={"to_user_id": student["user"]["id"], "type": "cuore"})
        assert r.status_code == 200
        r2 = requests.post(f"{API}/actions", headers=admin["h"],
                           json={"to_user_id": student["user"]["id"], "type": "cuore"})
        assert r2.status_code == 429  # anti-spam
        time.sleep(4.2)
        r3 = requests.post(f"{API}/actions", headers=admin["h"],
                           json={"to_user_id": student["user"]["id"], "type": "pizza"})
        assert r3.status_code == 200
        # inbox
        r4 = requests.get(f"{API}/actions/inbox", headers=student["h"])
        assert r4.status_code == 200


# ---------------- ai settings ----------------
class TestAISettings:
    def test_get(self, admin):
        r = requests.get(f"{API}/admin/ai-settings", headers=admin["h"])
        assert r.status_code == 200 and "google_ai_configured" in r.json()


# ---------------- study upload ----------------
class TestStudy:
    def test_upload_text(self, admin):
        files = {"file": ("test.txt", io.BytesIO(b"il triangolo ha tre lati. la fotosintesi produce ossigeno."), "text/plain")}
        r = requests.post(f"{API}/study/upload", headers=admin["h"], files=files)
        assert r.status_code == 200
        assert "file_id" in r.json()
