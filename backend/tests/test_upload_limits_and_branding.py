"""Backend tests for upload limits (size/type/rate) and branding/logo endpoints."""
import io
import os
import uuid
import pytest
import requests


def _load_backend_url():
    v = os.environ.get("REACT_APP_BACKEND_URL")
    if v:
        return v.rstrip("/")
    with open("/app/frontend/.env") as f:
        for line in f:
            if line.startswith("REACT_APP_BACKEND_URL="):
                return line.split("=", 1)[1].strip().rstrip("/")
    raise RuntimeError("REACT_APP_BACKEND_URL not set")


BASE_URL = _load_backend_url()
API = f"{BASE_URL}/api"

ADMIN_EMAIL = "admin@noidi2d.it"
ADMIN_PASSWORD = "AdminNoi2D!"
PROF_EMAIL = "prof@noidi2d.it"
PROF_PASSWORD = "ProfNoi2D!"
STUD_EMAIL = "studente.test@noidi2d.it"
STUD_PASSWORD = "Studente123!"


def _login(email, pw):
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": pw}, timeout=15)
    assert r.status_code == 200, r.text
    return r.json()["token"]


def _auth(tok):
    return {"Authorization": f"Bearer {tok}"}


@pytest.fixture(scope="module")
def admin_h():
    return _auth(_login(ADMIN_EMAIL, ADMIN_PASSWORD))


@pytest.fixture(scope="module")
def prof_h():
    return _auth(_login(PROF_EMAIL, PROF_PASSWORD))


@pytest.fixture(scope="module")
def stud_h():
    return _auth(_login(STUD_EMAIL, STUD_PASSWORD))


@pytest.fixture(scope="module")
def fresh_student(admin_h):
    """Create a brand new approved student to keep rate-limit tests isolated."""
    email = f"test_upl_{uuid.uuid4().hex[:8]}@noidi2d.it"
    pw = "MemberPass1!"
    r = requests.post(f"{API}/auth/register",
                      json={"name": "TEST Upload", "email": email, "password": pw}, timeout=15)
    assert r.status_code == 200, r.text
    users = requests.get(f"{API}/admin/users", headers=admin_h, timeout=15).json()
    uid = next(u["id"] for u in users if u["email"] == email)
    assert requests.post(f"{API}/admin/users/{uid}/approve", headers=admin_h, timeout=15).status_code == 200
    tok = _login(email, pw)
    return {"id": uid, "email": email, "h": _auth(tok)}


# ============ /study/upload validation ============
class TestStudyUploadValidation:
    def test_reject_bad_extension(self, stud_h):
        files = {"file": ("evil.exe", b"MZ\x00\x00binary", "application/octet-stream")}
        r = requests.post(f"{API}/study/upload", files=files, headers=stud_h, timeout=30)
        assert r.status_code == 400
        assert "non supportato" in r.text.lower() or "pdf" in r.text.lower()

    def test_reject_oversized(self, stud_h):
        big = b"a" * (10 * 1024 * 1024 + 100)  # 10MB + 100 bytes
        files = {"file": ("big.txt", big, "text/plain")}
        r = requests.post(f"{API}/study/upload", files=files, headers=stud_h, timeout=60)
        assert r.status_code == 400
        assert "troppo grande" in r.text.lower() or "10" in r.text

    def test_accept_txt(self, stud_h):
        files = {"file": ("lezione.txt", b"La fotosintesi clorofilliana e un processo importante." * 3, "text/plain")}
        r = requests.post(f"{API}/study/upload", files=files, headers=stud_h, timeout=30)
        assert r.status_code == 200, r.text
        j = r.json()
        assert "file_id" in j
        assert j["chars"] > 0

    def test_accept_pdf(self, stud_h):
        # Minimal PDF (from pypdf docs) — actually a tiny valid PDF payload
        pdf = (b"%PDF-1.1\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
               b"2 0 obj<</Type/Pages/Count 1/Kids[3 0 R]>>endobj\n"
               b"3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 100 100]/Contents 4 0 R>>endobj\n"
               b"4 0 obj<</Length 44>>stream\nBT /F1 12 Tf 10 50 Td (Ciao mondo) Tj ET\nendstream endobj\n"
               b"xref\n0 5\n0000000000 65535 f \n"
               b"trailer<</Size 5/Root 1 0 R>>\nstartxref\n0\n%%EOF")
        files = {"file": ("doc.pdf", pdf, "application/pdf")}
        r = requests.post(f"{API}/study/upload", files=files, headers=stud_h, timeout=30)
        # Accept 200 (parsed ok) or 400 if text extraction failed (empty text). Either way we validated ext acceptance.
        assert r.status_code in (200, 400), r.text
        if r.status_code == 400:
            assert "estensione" not in r.text.lower() and "non supportato" not in r.text.lower()


# ============ /news/upload validation ============
class TestNewsUploadValidation:
    def test_student_forbidden(self, stud_h):
        files = {"file": ("a.png", b"\x89PNG\r\n\x1a\n" + b"0" * 100, "image/png")}
        r = requests.post(f"{API}/news/upload", files=files, headers=stud_h, timeout=30)
        assert r.status_code == 403

    def test_reject_bad_ext(self, admin_h):
        files = {"file": ("evil.exe", b"MZbinary", "application/octet-stream")}
        r = requests.post(f"{API}/news/upload", files=files, headers=admin_h, timeout=30)
        assert r.status_code == 400

    def test_reject_oversized(self, admin_h):
        big = b"\x89PNG\r\n\x1a\n" + b"0" * (10 * 1024 * 1024 + 100)
        files = {"file": ("big.png", big, "image/png")}
        r = requests.post(f"{API}/news/upload", files=files, headers=admin_h, timeout=60)
        assert r.status_code == 400

    def test_accept_valid_png(self, admin_h):
        files = {"file": ("hero.png", b"\x89PNG\r\n\x1a\n" + b"0" * 100, "image/png")}
        r = requests.post(f"{API}/news/upload", files=files, headers=admin_h, timeout=30)
        assert r.status_code == 200, r.text
        assert "path" in r.json()


# ============ /branding & /admin/logo ============
class TestBrandingLogo:
    def test_branding_public_no_auth(self):
        r = requests.get(f"{API}/branding", timeout=15)
        assert r.status_code == 200
        assert "logo_url" in r.json()

    def test_delete_logo_admin_reset(self, admin_h):
        # Ensure clean state
        r = requests.delete(f"{API}/admin/logo", headers=admin_h, timeout=15)
        assert r.status_code == 200
        b = requests.get(f"{API}/branding", timeout=15).json()
        assert b["logo_url"] is None
        # /branding/logo returns 404
        r2 = requests.get(f"{API}/branding/logo", timeout=15)
        assert r2.status_code == 404

    def test_student_forbidden_logo_upload(self, stud_h):
        files = {"file": ("l.png", b"\x89PNG\r\n\x1a\n" + b"0" * 100, "image/png")}
        r = requests.post(f"{API}/admin/logo", files=files, headers=stud_h, timeout=30)
        assert r.status_code == 403

    def test_logo_reject_bad_ext(self, admin_h):
        files = {"file": ("l.gif", b"GIF89a" + b"0" * 100, "image/gif")}
        r = requests.post(f"{API}/admin/logo", files=files, headers=admin_h, timeout=30)
        assert r.status_code == 400

    def test_logo_reject_oversized(self, admin_h):
        big = b"\x89PNG\r\n\x1a\n" + b"0" * (5 * 1024 * 1024 + 100)  # >5MB
        files = {"file": ("big.png", big, "image/png")}
        r = requests.post(f"{API}/admin/logo", files=files, headers=admin_h, timeout=60)
        assert r.status_code == 400

    def test_logo_upload_and_fetch_flow(self, admin_h):
        png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 200
        files = {"file": ("new_logo.png", png, "image/png")}
        r = requests.post(f"{API}/admin/logo", files=files, headers=admin_h, timeout=30)
        assert r.status_code == 200, r.text
        assert r.json()["logo_url"].startswith("/api/branding/logo")

        # /branding now returns a URL
        b = requests.get(f"{API}/branding", timeout=15).json()
        assert b["logo_url"] is not None
        assert "/api/branding/logo" in b["logo_url"]

        # /branding/logo returns image bytes
        r2 = requests.get(f"{API}/branding/logo", timeout=15)
        assert r2.status_code == 200
        assert r2.headers.get("content-type", "").startswith("image/")
        assert len(r2.content) > 0

        # Reset for cleanup
        rd = requests.delete(f"{API}/admin/logo", headers=admin_h, timeout=15)
        assert rd.status_code == 200
        assert requests.get(f"{API}/branding", timeout=15).json()["logo_url"] is None

    def test_prof_can_upload_logo(self, prof_h):
        png = b"\x89PNG\r\n\x1a\n" + b"\x01" * 200
        files = {"file": ("prof.png", png, "image/png")}
        r = requests.post(f"{API}/admin/logo", files=files, headers=prof_h, timeout=30)
        assert r.status_code == 200
        # cleanup
        requests.delete(f"{API}/admin/logo", headers=prof_h, timeout=15)


# ============ Rate limiting (kind-scoped) ============
class TestUploadRateLimit:
    """Uses a fresh student to isolate rate-limit counters."""

    def test_rate_limit_study_then_news_ok(self, fresh_student, admin_h):
        h = fresh_student["h"]
        # 20 successful study uploads
        ok = 0
        for i in range(20):
            files = {"file": (f"n{i}.txt", f"Contenuto numero {i} " * 20, "text/plain")}
            r = requests.post(f"{API}/study/upload", files=files, headers=h, timeout=30)
            if r.status_code == 200:
                ok += 1
            else:
                pytest.fail(f"Unexpected {r.status_code} at upload {i}: {r.text}")
        assert ok == 20

        # 21st must be 429
        files = {"file": ("n21.txt", b"Contenuto 21 " * 20, "text/plain")}
        r = requests.post(f"{API}/study/upload", files=files, headers=h, timeout=30)
        assert r.status_code == 429, r.text
        assert "20 caricamenti" in r.text or "limite" in r.text.lower()

        # Same user can still upload news (different kind) — promote to admin temporarily? No, news requires admin.
        # Instead just verify limit is per-kind by checking admin's news upload still works and student's news
        # returns 403 (auth) not 429. This confirms the rate check didn't bleed across kinds server-wide.
        files = {"file": ("a.png", b"\x89PNG\r\n\x1a\n" + b"0" * 50, "image/png")}
        r_stud = requests.post(f"{API}/news/upload", files=files, headers=h, timeout=30)
        assert r_stud.status_code == 403  # NOT 429 → rate limit scoped per kind+user

        # Admin (different user) can still upload news
        r_admin = requests.post(f"{API}/news/upload", files=files, headers=admin_h, timeout=30)
        assert r_admin.status_code == 200


# ============ Study file persistence + flashcards generation still works ============
class TestStudyFilePersistence:
    def test_uploaded_file_usable_for_flashcards(self, stud_h):
        content = ("La fotosintesi clorofilliana e il processo con cui le piante trasformano "
                   "la luce solare in energia chimica. Coinvolge clorofilla, acqua e anidride carbonica. ") * 5
        files = {"file": ("bio.txt", content.encode("utf-8"), "text/plain")}
        r = requests.post(f"{API}/study/upload", files=files, headers=stud_h, timeout=30)
        assert r.status_code == 200, r.text
        fid = r.json()["file_id"]

        # Generate flashcards from file_id (AI can be slow)
        r2 = requests.post(f"{API}/study/flashcards",
                           json={"file_id": fid, "count": 2}, headers=stud_h, timeout=90)
        # AI may fail intermittently; accept 200 with cards. If AI is misconfigured we'll accept a 5xx but flag it.
        assert r2.status_code == 200, r2.text[:400]
        cards = r2.json().get("cards", [])
        assert isinstance(cards, list) and len(cards) >= 1
