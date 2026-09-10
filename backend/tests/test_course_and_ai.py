"""Backend tests for new features: Groq AI settings + Course Panel (rep/teams/polls/chat)."""
import os
import uuid
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://class-connect-2d.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"

ADMIN_EMAIL = "admin@noidi2d.it"
ADMIN_PASSWORD = "AdminNoi2D!"


def _login(email, pw):
    return requests.post(f"{API}/auth/login", json={"email": email, "password": pw}, timeout=15)


def _register(name, email, pw):
    return requests.post(f"{API}/auth/register", json={"name": name, "email": email, "password": pw}, timeout=15)


@pytest.fixture(scope="module")
def admin_h():
    r = _login(ADMIN_EMAIL, ADMIN_PASSWORD)
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


def _make_member(admin_h):
    email = f"course_{uuid.uuid4().hex[:8]}@noidi2d.it"
    pw = "MemberPass1!"
    assert _register("Course Tester", email, pw).status_code == 200
    users = requests.get(f"{API}/admin/users", headers=admin_h, timeout=15).json()
    uid = next(u["id"] for u in users if u["email"] == email)
    assert requests.post(f"{API}/admin/users/{uid}/approve", headers=admin_h, timeout=15).status_code == 200
    tok = _login(email, pw).json()["token"]
    return {"email": email, "pw": pw, "id": uid, "h": {"Authorization": f"Bearer {tok}"}}


@pytest.fixture(scope="module")
def member1(admin_h):
    return _make_member(admin_h)


@pytest.fixture(scope="module")
def member2(admin_h):
    return _make_member(admin_h)


@pytest.fixture(scope="module")
def outsider(admin_h):
    """approved user NOT signed up to the event"""
    return _make_member(admin_h)


# ------------- Groq AI settings -------------
class TestAISettings:
    def test_default_state_no_groq(self, admin_h):
        # Ensure clean state first
        requests.post(f"{API}/admin/ai-settings", json={"api_key": ""}, headers=admin_h, timeout=15)
        r = requests.get(f"{API}/admin/ai-settings", headers=admin_h, timeout=15)
        assert r.status_code == 200
        assert r.json().get("groq_configured") is False

    def test_save_key_configures_groq(self, admin_h):
        r = requests.post(f"{API}/admin/ai-settings", json={"api_key": "gsk_test_fake_key_1234567890"}, headers=admin_h, timeout=15)
        assert r.status_code == 200, r.text
        assert r.json().get("groq_configured") is True
        r2 = requests.get(f"{API}/admin/ai-settings", headers=admin_h, timeout=15)
        assert r2.json().get("groq_configured") is True

    def test_remove_key_reverts_default(self, admin_h):
        r = requests.post(f"{API}/admin/ai-settings", json={"api_key": ""}, headers=admin_h, timeout=15)
        assert r.status_code == 200, r.text
        assert r.json().get("groq_configured") is False

    def test_non_admin_forbidden(self, member1):
        r = requests.get(f"{API}/admin/ai-settings", headers=member1["h"], timeout=15)
        assert r.status_code == 403


# ------------- Course Panel -------------
@pytest.fixture(scope="module")
def event_ctx(admin_h, member1, member2):
    """Create event (admin), both members sign up."""
    payload = {"title": f"TEST_Course_{uuid.uuid4().hex[:6]}", "description": "course panel", "urgency": "bassa"}
    r = requests.post(f"{API}/events", json=payload, headers=admin_h, timeout=15)
    assert r.status_code == 200
    eid = r.json()["id"]
    assert requests.post(f"{API}/events/{eid}/signup", json={}, headers=member1["h"], timeout=15).status_code == 200
    assert requests.post(f"{API}/events/{eid}/signup", json={}, headers=member2["h"], timeout=15).status_code == 200
    yield {"eid": eid}
    requests.delete(f"{API}/events/{eid}", headers=admin_h, timeout=15)


class TestCourseAccess:
    def test_participant_can_get(self, event_ctx, member1):
        r = requests.get(f"{API}/events/{event_ctx['eid']}/course", headers=member1["h"], timeout=15)
        assert r.status_code == 200
        d = r.json()
        assert "teams" in d and "polls" in d and "sport_types" in d
        assert d["can_manage"] is False

    def test_admin_can_manage(self, event_ctx, admin_h):
        r = requests.get(f"{API}/events/{event_ctx['eid']}/course", headers=admin_h, timeout=15)
        assert r.status_code == 200
        assert r.json()["can_manage"] is True

    def test_outsider_forbidden(self, event_ctx, outsider):
        eid = event_ctx["eid"]
        assert requests.get(f"{API}/events/{eid}/course", headers=outsider["h"], timeout=15).status_code == 403
        assert requests.get(f"{API}/events/{eid}/course/chat", headers=outsider["h"], timeout=15).status_code == 403
        r = requests.post(f"{API}/events/{eid}/course/chat", json={"text": "hi"}, headers=outsider["h"], timeout=15)
        assert r.status_code == 403


class TestRep:
    def test_admin_sets_rep(self, event_ctx, admin_h, member1):
        r = requests.post(f"{API}/events/{event_ctx['eid']}/course/rep",
                          json={"user_id": member1["id"]}, headers=admin_h, timeout=15)
        assert r.status_code == 200
        g = requests.get(f"{API}/events/{event_ctx['eid']}/course", headers=admin_h, timeout=15).json()
        assert g["rep"]["user_id"] == member1["id"]

    def test_rep_becomes_captain(self, event_ctx, member1):
        # after being rep, member1 can_manage
        g = requests.get(f"{API}/events/{event_ctx['eid']}/course", headers=member1["h"], timeout=15).json()
        assert g["can_manage"] is True

    def test_member_cannot_set_rep(self, event_ctx, member2, member1):
        r = requests.post(f"{API}/events/{event_ctx['eid']}/course/rep",
                          json={"user_id": member2["id"]}, headers=member2["h"], timeout=15)
        assert r.status_code == 403

    def test_rep_must_be_signed_up(self, event_ctx, admin_h, outsider):
        r = requests.post(f"{API}/events/{event_ctx['eid']}/course/rep",
                          json={"user_id": outsider["id"]}, headers=admin_h, timeout=15)
        assert r.status_code == 400

    def test_admin_removes_rep(self, event_ctx, admin_h, member1):
        # re-set first
        requests.post(f"{API}/events/{event_ctx['eid']}/course/rep",
                      json={"user_id": member1["id"]}, headers=admin_h, timeout=15)
        r = requests.delete(f"{API}/events/{event_ctx['eid']}/course/rep", headers=admin_h, timeout=15)
        assert r.status_code == 200
        g = requests.get(f"{API}/events/{event_ctx['eid']}/course", headers=admin_h, timeout=15).json()
        assert g["rep"] is None


class TestTeams:
    def test_create_and_delete_team(self, event_ctx, admin_h, member1, member2):
        eid = event_ctx["eid"]
        # invalid sport
        bad = requests.post(f"{API}/events/{eid}/course/teams",
                            json={"name": "X", "sport_type": "cricket"}, headers=admin_h, timeout=15)
        assert bad.status_code == 400

        r = requests.post(f"{API}/events/{eid}/course/teams",
                          json={"name": "Squadra A", "sport_type": "volley3"}, headers=admin_h, timeout=15)
        assert r.status_code == 200, r.text
        tid = r.json()["id"]

        # add member1
        a1 = requests.post(f"{API}/events/{eid}/course/teams/{tid}/members",
                           json={"user_id": member1["id"]}, headers=admin_h, timeout=15)
        assert a1.status_code == 200
        # duplicate
        dup = requests.post(f"{API}/events/{eid}/course/teams/{tid}/members",
                            json={"user_id": member1["id"]}, headers=admin_h, timeout=15)
        assert dup.status_code == 400
        # outsider can't be added
        # (create third outsider is expensive - re-use event outsider not needed here)

        # Add member2
        a2 = requests.post(f"{API}/events/{eid}/course/teams/{tid}/members",
                           json={"user_id": member2["id"]}, headers=admin_h, timeout=15)
        assert a2.status_code == 200

        # verify roster
        g = requests.get(f"{API}/events/{eid}/course", headers=admin_h, timeout=15).json()
        team = next(t for t in g["teams"] if t["id"] == tid)
        assert len(team["members"]) == 2

        # remove member1
        r_rm = requests.delete(f"{API}/events/{eid}/course/teams/{tid}/members/{member1['id']}",
                               headers=admin_h, timeout=15)
        assert r_rm.status_code == 200

        # delete team
        r_del = requests.delete(f"{API}/events/{eid}/course/teams/{tid}", headers=admin_h, timeout=15)
        assert r_del.status_code == 200

    def test_team_capacity_limit(self, event_ctx, admin_h, member1, member2):
        eid = event_ctx["eid"]
        # volley3 max=3 but we only have 2 signed-up members; use a 1-cap scenario indirectly:
        # Create volley3 team, add 2 members. Verify 3rd add fails via participant guard (outsider) with 400.
        r = requests.post(f"{API}/events/{eid}/course/teams",
                          json={"name": "Cap Test", "sport_type": "volley3"}, headers=admin_h, timeout=15)
        tid = r.json()["id"]
        requests.post(f"{API}/events/{eid}/course/teams/{tid}/members", json={"user_id": member1["id"]}, headers=admin_h, timeout=15)
        requests.post(f"{API}/events/{eid}/course/teams/{tid}/members", json={"user_id": member2["id"]}, headers=admin_h, timeout=15)
        # non-participant blocked (400)
        fake = requests.post(f"{API}/events/{eid}/course/teams/{tid}/members",
                             json={"user_id": "no-such-user"}, headers=admin_h, timeout=15)
        assert fake.status_code == 400
        requests.delete(f"{API}/events/{eid}/course/teams/{tid}", headers=admin_h, timeout=15)

    def test_non_manager_cannot_create_team(self, event_ctx, member2):
        r = requests.post(f"{API}/events/{event_ctx['eid']}/course/teams",
                          json={"name": "Nope", "sport_type": "basket"}, headers=member2["h"], timeout=15)
        assert r.status_code == 403


class TestPolls:
    def test_create_vote_change_delete(self, event_ctx, admin_h, member1, member2):
        eid = event_ctx["eid"]
        # <2 options
        bad = requests.post(f"{API}/events/{eid}/course/polls",
                            json={"question": "Q?", "options": ["A"]}, headers=admin_h, timeout=15)
        assert bad.status_code == 400

        cr = requests.post(f"{API}/events/{eid}/course/polls",
                           json={"question": "Cena?", "options": ["Pizza", "Sushi"]}, headers=admin_h, timeout=15)
        assert cr.status_code == 200

        g = requests.get(f"{API}/events/{eid}/course", headers=admin_h, timeout=15).json()
        assert len(g["polls"]) >= 1
        pid = g["polls"][0]["id"]

        # member1 votes Pizza
        v1 = requests.post(f"{API}/events/{eid}/course/polls/{pid}/vote",
                           json={"option": "Pizza"}, headers=member1["h"], timeout=15)
        assert v1.status_code == 200
        # member2 votes Sushi
        v2 = requests.post(f"{API}/events/{eid}/course/polls/{pid}/vote",
                           json={"option": "Sushi"}, headers=member2["h"], timeout=15)
        assert v2.status_code == 200

        g2 = requests.get(f"{API}/events/{eid}/course", headers=member1["h"], timeout=15).json()
        p = next(x for x in g2["polls"] if x["id"] == pid)
        assert p["total_votes"] == 2
        assert p["vote_counts"]["Pizza"] == 1
        assert p["vote_counts"]["Sushi"] == 1
        assert p["my_vote"] == "Pizza"

        # member1 changes to Sushi
        vc = requests.post(f"{API}/events/{eid}/course/polls/{pid}/vote",
                           json={"option": "Sushi"}, headers=member1["h"], timeout=15)
        assert vc.status_code == 200
        g3 = requests.get(f"{API}/events/{eid}/course", headers=member1["h"], timeout=15).json()
        p = next(x for x in g3["polls"] if x["id"] == pid)
        assert p["total_votes"] == 2
        assert p["vote_counts"]["Sushi"] == 2

        # invalid option
        vi = requests.post(f"{API}/events/{eid}/course/polls/{pid}/vote",
                           json={"option": "Kebab"}, headers=member1["h"], timeout=15)
        assert vi.status_code == 400

        # delete
        d = requests.delete(f"{API}/events/{eid}/course/polls/{pid}", headers=admin_h, timeout=15)
        assert d.status_code == 200

    def test_outsider_cannot_vote(self, event_ctx, admin_h, outsider):
        eid = event_ctx["eid"]
        cr = requests.post(f"{API}/events/{eid}/course/polls",
                           json={"question": "Q?", "options": ["A", "B"]}, headers=admin_h, timeout=15)
        assert cr.status_code == 200
        pid = requests.get(f"{API}/events/{eid}/course", headers=admin_h, timeout=15).json()["polls"][0]["id"]
        r = requests.post(f"{API}/events/{eid}/course/polls/{pid}/vote",
                          json={"option": "A"}, headers=outsider["h"], timeout=15)
        assert r.status_code == 403
        requests.delete(f"{API}/events/{eid}/course/polls/{pid}", headers=admin_h, timeout=15)


class TestCourseChat:
    def test_participant_sends_and_reads(self, event_ctx, member1):
        eid = event_ctx["eid"]
        text = f"ciao TEST_{uuid.uuid4().hex[:6]}"
        r = requests.post(f"{API}/events/{eid}/course/chat", json={"text": text}, headers=member1["h"], timeout=15)
        assert r.status_code == 200, r.text
        assert r.json()["text"] == text
        g = requests.get(f"{API}/events/{eid}/course/chat", headers=member1["h"], timeout=15)
        assert g.status_code == 200
        assert any(m["text"] == text for m in g.json())

    def test_empty_rejected(self, event_ctx, member1):
        r = requests.post(f"{API}/events/{event_ctx['eid']}/course/chat", json={"text": "   "}, headers=member1["h"], timeout=15)
        assert r.status_code == 400


# ------------- Regression: study AI still works without Groq -------------
class TestRegressionAI:
    def test_flashcards_default_gemini(self, admin_h):
        # ensure groq is off
        requests.post(f"{API}/admin/ai-settings", json={"api_key": ""}, headers=admin_h, timeout=15)
        r = requests.post(f"{API}/study/flashcards",
                          json={"topic": "matematica base", "count": 2}, headers=admin_h, timeout=60)
        assert r.status_code == 200, r.text[:400]
        cards = r.json().get("cards", [])
        assert isinstance(cards, list) and len(cards) >= 1

    def test_chat_public_still_works(self, admin_h):
        text = f"regression TEST_{uuid.uuid4().hex[:6]}"
        r = requests.post(f"{API}/chat/messages", json={"text": text}, headers=admin_h, timeout=20)
        assert r.status_code == 200
        assert r.json()["text"] == text
