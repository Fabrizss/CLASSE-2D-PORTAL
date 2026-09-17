from dotenv import load_dotenv
from pathlib import Path
ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

import os
import uuid
import json
import asyncio
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, List

import jwt
import bcrypt
import resend
import requests
import asyncpg
from fastapi import FastAPI, APIRouter, HTTPException, Depends, Request, UploadFile, File, Form, Header, Query, Response
from starlette.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr, Field
from pywebpush import webpush, WebPushException
from emergentintegrations.llm.chat import LlmChat, UserMessage
from google import genai
from google.genai import types as genai_types
from pypdf import PdfReader
import io

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("noidi2d")

# ---------------- database (Supabase / Postgres) ----------------
DATABASE_URL = os.environ['DATABASE_URL']
pg_pool: asyncpg.Pool = None

async def _init_conn(conn):
    await conn.set_type_codec('jsonb', encoder=json.dumps, decoder=json.loads, schema='pg_catalog', format='text')
    await conn.set_type_codec('json', encoder=json.dumps, decoder=json.loads, schema='pg_catalog', format='text')

def clean(row):
    """Converte un Record asyncpg in un dict JSON-friendly (uuid->str, datetime->isoformat)."""
    if row is None:
        return None
    d = dict(row)
    for k, v in d.items():
        if isinstance(v, uuid.UUID):
            d[k] = str(v)
        elif isinstance(v, datetime):
            d[k] = v.isoformat()
    return d

def clean_many(rows):
    return [clean(r) for r in rows]

JWT_SECRET = os.environ['JWT_SECRET']
JWT_ALGO = "HS256"
EMERGENT_LLM_KEY = os.environ.get('EMERGENT_LLM_KEY')
VAPID_PRIVATE_KEY = os.environ.get('VAPID_PRIVATE_KEY')
VAPID_PUBLIC_KEY = os.environ.get('VAPID_PUBLIC_KEY')
VAPID_CLAIM_EMAIL = os.environ.get('VAPID_CLAIM_EMAIL', 'mailto:admin@noidi2d.it')
resend.api_key = os.environ.get('RESEND_API_KEY') or None
SENDER_EMAIL = os.environ.get('SENDER_EMAIL', 'onboarding@resend.dev')

# ---------------- google ai / gemini (AI configurabile da admin) ----------------
GOOGLE_CHAT_MODEL = "gemini-2.5-flash"
GOOGLE_FLASHCARD_MODEL = "gemini-2.5-flash"
GOOGLE_MODERATION_MODEL = "gemini-2.5-flash-lite"
_google_key_cache = {"key": None}

async def load_ai_settings():
    row = await pg_pool.fetchrow("SELECT google_ai_api_key FROM app_settings WHERE id='ai'")
    _google_key_cache["key"] = (row["google_ai_api_key"] if row else None) or None

def get_google_key():
    return _google_key_cache["key"]

# ---------------- upload limits ----------------
MAX_UPLOAD_SIZE = 10 * 1024 * 1024  # 10MB
MAX_UPLOADS_PER_DAY = 20
NEWS_ALLOWED_EXT = {"png", "jpg", "jpeg", "gif", "webp", "pdf"}
STUDY_ALLOWED_EXT = {"pdf", "txt", "md"}
LOGO_ALLOWED_EXT = {"png", "jpg", "jpeg", "webp"}
MAX_LOGO_SIZE = 5 * 1024 * 1024  # 5MB
STUDY_FILE_MAX_AGE_DAYS = 3

def file_ext(filename: str) -> str:
    return (filename or "").rsplit(".", 1)[-1].lower() if "." in (filename or "") else ""

async def check_upload_limit(user_id: str, kind: str):
    since = datetime.now(timezone.utc) - timedelta(days=1)
    count = await pg_pool.fetchval(
        "SELECT count(*) FROM uploads_log WHERE user_id=$1::uuid AND kind=$2 AND created_at > $3",
        user_id, kind, since)
    if count >= MAX_UPLOADS_PER_DAY:
        raise HTTPException(429, f"Hai raggiunto il limite di {MAX_UPLOADS_PER_DAY} caricamenti al giorno. Riprova domani.")

async def log_upload(user_id: str, kind: str, size: int):
    await pg_pool.execute(
        "INSERT INTO uploads_log (id,user_id,kind,size,created_at) VALUES ($1::uuid,$2::uuid,$3,$4,$5)",
        str(uuid.uuid4()), user_id, kind, size, datetime.now(timezone.utc))

async def study_files_cleanup_loop():
    while True:
        try:
            cutoff = datetime.now(timezone.utc) - timedelta(days=STUDY_FILE_MAX_AGE_DAYS)
            deleted = await pg_pool.fetch("DELETE FROM study_files WHERE created_at < $1 RETURNING id", cutoff)
            if deleted:
                logger.info(f"Puliti {len(deleted)} file di Studio AI più vecchi di {STUDY_FILE_MAX_AGE_DAYS} giorni")
        except Exception as e:
            logger.warning(f"Cleanup study_files fallito: {e}")
        await asyncio.sleep(3600)

async def google_chat_reply(system: str, history: list, message: str) -> str:
    client = genai.Client(api_key=get_google_key())
    contents = [{"role": h["role"], "parts": [{"text": h["text"]}]} for h in history]
    contents.append({"role": "user", "parts": [{"text": message}]})
    resp = await client.aio.models.generate_content(
        model=GOOGLE_CHAT_MODEL, contents=contents,
        config=genai_types.GenerateContentConfig(system_instruction=system, temperature=0.4, max_output_tokens=800),
    )
    return resp.text or ""

async def google_json_reply(system: str, prompt: str, model: str = GOOGLE_FLASHCARD_MODEL) -> str:
    client = genai.Client(api_key=get_google_key())
    resp = await client.aio.models.generate_content(
        model=model, contents=prompt,
        config=genai_types.GenerateContentConfig(
            system_instruction=system, temperature=0.2, max_output_tokens=2000,
            response_mime_type="application/json",
        ),
    )
    return resp.text or "{}"

async def moderate_text(text: str) -> bool:
    """Ritorna True se il messaggio va bloccato dalla moderazione AI (Google AI). Fail-open se non configurata/non risponde."""
    key = get_google_key()
    if not key:
        return False
    policy = ("Sei un moderatore per una chat di studenti di una scuola superiore italiana. "
              'Classifica il messaggio. Rispondi SOLO con JSON: {"allowed": true} oppure {"allowed": false}. '
              "Blocca solo contenuti gravi: minacce, bullismo, contenuti sessuali, odio, autolesionismo, istigazione a reati. "
              "Linguaggio scolastico normale, sfoghi leggeri o ironia vanno sempre permessi (allowed=true).")
    try:
        client = genai.Client(api_key=key)
        resp = await asyncio.wait_for(client.aio.models.generate_content(
            model=GOOGLE_MODERATION_MODEL, contents=text[:1000],
            config=genai_types.GenerateContentConfig(
                system_instruction=policy, temperature=0, max_output_tokens=50,
                response_mime_type="application/json",
            ),
        ), timeout=6)
        data = json.loads(resp.text or "{}")
        return not data.get("allowed", True)
    except Exception as e:
        logger.warning(f"moderazione AI fallita: {e}")
        return False

app = FastAPI()
api = APIRouter(prefix="/api")

# ---------------- helpers ----------------
def now_iso():
    return datetime.now(timezone.utc).isoformat()

def hash_password(p: str) -> str:
    return bcrypt.hashpw(p.encode(), bcrypt.gensalt()).decode()

def verify_password(p: str, h: str) -> bool:
    try:
        return bcrypt.checkpw(p.encode(), h.encode())
    except Exception:
        return False

def create_token(user_id: str) -> str:
    payload = {"sub": user_id, "exp": datetime.now(timezone.utc) + timedelta(days=7), "type": "access"}
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGO)

def public_user(u: dict) -> dict:
    return {
        "id": u["id"], "name": u["name"], "email": u["email"], "role": u["role"],
        "status": u["status"], "can_create_events": u.get("can_create_events", False),
        "avatar_color": u.get("avatar_color", "#7C3AED"),
        "ban_permanent": u.get("ban_permanent", False),
        "banned_until": u.get("banned_until"),
    }

def ban_active(u: dict):
    if u.get("ban_permanent"):
        return True, "Il tuo account è stato bannato permanentemente."
    bu = u.get("banned_until")
    if bu and bu > now_iso():
        return True, f"Sei sospeso fino al {bu[:16].replace('T', ' ')} (UTC)."
    return False, ""

async def get_current_user(request: Request) -> dict:
    token = None
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        token = auth[7:]
    if not token:
        raise HTTPException(status_code=401, detail="Non autenticato")
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGO])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Sessione scaduta")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Token non valido")
    row = await pg_pool.fetchrow("SELECT * FROM users WHERE id=$1::uuid", payload["sub"])
    if not row:
        raise HTTPException(status_code=401, detail="Utente non trovato")
    return clean(row)

async def require_approved(request: Request) -> dict:
    u = await get_current_user(request)
    if u["status"] != "approved":
        raise HTTPException(status_code=403, detail="Account in attesa di approvazione")
    active, msg = ban_active(u)
    if active:
        raise HTTPException(status_code=403, detail=msg)
    return u

async def require_admin(request: Request) -> dict:
    u = await require_approved(request)
    if u["role"] not in ("admin", "professore"):
        raise HTTPException(status_code=403, detail="Solo staff (admin o professore)")
    return u

def is_staff_role(role: str) -> bool:
    return role in ("admin", "professore")

# ---------------- models ----------------
class RegisterIn(BaseModel):
    name: str
    email: EmailStr
    password: str

class LoginIn(BaseModel):
    email: EmailStr
    password: str

class EventIn(BaseModel):
    title: str
    description: str
    urgency: str = "normale"  # bassa, normale, alta, urgente
    deadline: Optional[str] = None
    location: Optional[str] = None
    options: List[str] = []  # gruppi/opzioni di iscrizione
    capacity: Optional[int] = None  # posti massimi totali
    caps: dict = {}  # {opzione: max}

class NewsIn(BaseModel):
    title: str
    body: str
    attachments: List[dict] = []

class InterrogazioneIn(BaseModel):
    subject: Optional[str] = None
    tipo: str = "orale"  # orale / scritta / pratica
    num_domande: int = 0
    voto: Optional[float] = None

class VotoIn(BaseModel):
    voto: Optional[float] = None

class ReminderIn(BaseModel):
    text: str
    is_public: bool = False

class SignupIn(BaseModel):
    option: Optional[str] = None

class BanIn(BaseModel):
    mode: str = "temp"  # perm / temp
    hours: int = 24

class MessageIn(BaseModel):
    text: str

class ActionIn(BaseModel):
    to_user_id: str
    type: str  # foglietto, secchio, pizza, cuore, high_five

class StudyChatIn(BaseModel):
    session_id: str
    message: str
    subject: Optional[str] = None

class FlashcardIn(BaseModel):
    topic: Optional[str] = None
    file_id: Optional[str] = None
    count: int = 8

class SubscribeIn(BaseModel):
    subscription: dict

class AISettingsIn(BaseModel):
    api_key: str = ""

class RepIn(BaseModel):
    user_id: str

class TeamIn(BaseModel):
    name: str
    sport_type: str

class TeamMemberIn(BaseModel):
    user_id: str

class PositionIn(BaseModel):
    position: Optional[str] = None

class PollIn(BaseModel):
    question: str
    options: List[str]

class PollVoteIn(BaseModel):
    option: str

class CourseMessageIn(BaseModel):
    text: str

SPORT_TYPES = {
    "calcio7": {"label": "Calcio a 7", "max": 7},
    "calcio11": {"label": "Calcio a 11", "max": 11},
    "basket": {"label": "Basket", "max": 5},
    "volley3": {"label": "Volley 3x3", "max": 3},
    "pallavolo": {"label": "Pallavolo", "max": 6},
    "generico": {"label": "Sport generico", "max": None},
}

# ---------------- censorship ----------------
BAD_WORDS = [
    "cazzo","merda","stronzo","stronza","puttana","troia","bastardo","coglione","vaffanculo",
    "fanculo","porco","porca","frocio","negro","ritardato","idiota","cretino","imbecille",
    "fuck","shit","bitch","asshole","dick","cunt","bastard","retard","nigger",
]
import re
def censor(text: str) -> str:
    def repl(m):
        return "*" * len(m.group(0))
    for w in BAD_WORDS:
        text = re.sub(rf"(?i)\b{re.escape(w)}\w*", repl, text)
    return text

# ---------------- push ----------------
async def send_push_to_all(title: str, body: str, url: str = "/"):
    subs = clean_many(await pg_pool.fetch("SELECT * FROM push_subscriptions"))
    await _push(subs, title, body, url)

async def send_push_to_admins(title: str, body: str, url: str = "/"):
    rows = await pg_pool.fetch("SELECT id FROM users WHERE role='admin'")
    ids = [str(r["id"]) for r in rows]
    subs = clean_many(await pg_pool.fetch("SELECT * FROM push_subscriptions WHERE user_id = ANY($1::uuid[])", ids)) if ids else []
    await _push(subs, title, body, url)

async def _push(subs, title, body, url):
    payload = json.dumps({"title": title, "body": body, "url": url})
    for s in subs:
        try:
            await asyncio.to_thread(
                webpush,
                subscription_info=s["subscription"],
                data=payload,
                vapid_private_key=VAPID_PRIVATE_KEY,
                vapid_claims={"sub": VAPID_CLAIM_EMAIL},
            )
        except WebPushException as e:
            if e.response is not None and e.response.status_code in (404, 410):
                await pg_pool.execute("DELETE FROM push_subscriptions WHERE endpoint=$1", s.get("endpoint"))
        except Exception as ex:
            logger.warning(f"push fail: {ex}")

async def send_event_email(event: dict, recipients: List[str]):
    if not resend.api_key or not recipients:
        logger.info("Resend non configurato o nessun destinatario, email saltata")
        return
    urgency_color = {"urgente": "#DC2626", "alta": "#F59E0B", "normale": "#7C3AED", "bassa": "#6B7280"}.get(event["urgency"], "#7C3AED")
    html = f"""
    <table width="100%" style="font-family:Arial,sans-serif;background:#faf5ff;padding:24px">
      <tr><td align="center">
        <table width="520" style="background:#fff;border-radius:16px;overflow:hidden;border:1px solid #eee">
          <tr><td style="background:{urgency_color};padding:20px 28px;color:#fff">
            <div style="font-size:12px;letter-spacing:2px;text-transform:uppercase">NOI DI 2D · Iscrizione {event['urgency']}</div>
            <div style="font-size:24px;font-weight:bold;margin-top:6px">{event['title']}</div>
          </td></tr>
          <tr><td style="padding:24px 28px;color:#333">
            <p style="font-size:15px;line-height:1.6">{event['description']}</p>
            {f'<p style="color:#7C3AED"><b>Scadenza:</b> {event["deadline"]}</p>' if event.get('deadline') else ''}
            {f'<p style="color:#7C3AED"><b>Luogo:</b> {event["location"]}</p>' if event.get('location') else ''}
            <p style="font-size:13px;color:#888;margin-top:24px">Accedi al portale per iscriverti.</p>
          </td></tr>
        </table>
      </td></tr>
    </table>"""
    for r in recipients:
        try:
            await asyncio.to_thread(resend.Emails.send, {
                "from": SENDER_EMAIL, "to": [r],
                "subject": f"[{event['urgency'].upper()}] Nuova iscrizione: {event['title']}",
                "html": html,
            })
        except Exception as e:
            logger.warning(f"email fail {r}: {e}")

# ---------------- auth routes ----------------
COLORS = ["#7C3AED","#F472B6","#FBBF24","#34D399","#60A5FA","#F87171","#A78BFA","#FB923C"]

@api.post("/auth/register")
async def register(body: RegisterIn):
    email = body.email.lower()
    existing = await pg_pool.fetchval("SELECT 1 FROM users WHERE email=$1", email)
    if existing:
        raise HTTPException(status_code=400, detail="Email già registrata")
    uid = str(uuid.uuid4())
    count = await pg_pool.fetchval("SELECT count(*) FROM users")
    await pg_pool.execute(
        "INSERT INTO users (id,name,email,password_hash,role,status,can_create_events,avatar_color,created_at) "
        "VALUES ($1::uuid,$2,$3,$4,'member','pending',false,$5,$6)",
        uid, body.name, email, hash_password(body.password), COLORS[count % len(COLORS)], datetime.now(timezone.utc),
    )
    return {"message": "Registrazione ricevuta. Un admin deve approvare il tuo account prima dell'accesso."}

@api.post("/auth/login")
async def login(body: LoginIn):
    email = body.email.lower()
    row = await pg_pool.fetchrow("SELECT * FROM users WHERE email=$1", email)
    u = clean(row)
    if not u or not verify_password(body.password, u["password_hash"]):
        raise HTTPException(status_code=401, detail="Credenziali non valide")
    if u["status"] == "pending":
        raise HTTPException(status_code=403, detail="Account in attesa di approvazione dell'admin")
    if u["status"] == "rejected":
        raise HTTPException(status_code=403, detail="Accesso rifiutato dall'admin")
    active, msg = ban_active(u)
    if active:
        raise HTTPException(status_code=403, detail=msg)
    return {"token": create_token(u["id"]), "user": public_user(u)}

@api.get("/auth/me")
async def me(u: dict = Depends(get_current_user)):
    return public_user(u)

# ---------------- users ----------------
@api.get("/users")
async def list_users(u: dict = Depends(require_approved)):
    users = clean_many(await pg_pool.fetch("SELECT * FROM users WHERE status='approved'"))
    return [public_user(x) for x in users if x["id"] != u["id"]]

# ---------------- admin ----------------
@api.get("/admin/users")
async def admin_users(u: dict = Depends(require_admin)):
    users = clean_many(await pg_pool.fetch("SELECT * FROM users ORDER BY created_at DESC"))
    return [public_user(x) for x in users]

@api.post("/admin/users/{uid}/approve")
async def approve_user(uid: str, u: dict = Depends(require_admin)):
    await pg_pool.execute("UPDATE users SET status='approved' WHERE id=$1::uuid", uid)
    return {"ok": True}

@api.post("/admin/users/{uid}/reject")
async def reject_user(uid: str, u: dict = Depends(require_admin)):
    await pg_pool.execute("UPDATE users SET status='rejected' WHERE id=$1::uuid", uid)
    return {"ok": True}

@api.post("/admin/users/{uid}/role/{role}")
async def set_role(uid: str, role: str, u: dict = Depends(require_admin)):
    if role not in ("admin", "member", "professore"):
        raise HTTPException(400, "Ruolo non valido")
    await pg_pool.execute("UPDATE users SET role=$1 WHERE id=$2::uuid", role, uid)
    return {"ok": True}

@api.post("/admin/users/{uid}/authorize/{value}")
async def authorize_events(uid: str, value: int, u: dict = Depends(require_admin)):
    await pg_pool.execute("UPDATE users SET can_create_events=$1 WHERE id=$2::uuid", bool(value), uid)
    return {"ok": True}

@api.delete("/admin/users/{uid}")
async def delete_user(uid: str, u: dict = Depends(require_admin)):
    await pg_pool.execute("DELETE FROM users WHERE id=$1::uuid", uid)
    return {"ok": True}

@api.post("/admin/users/{uid}/ban")
async def ban_user(uid: str, body: BanIn, u: dict = Depends(require_admin)):
    if uid == u["id"]:
        raise HTTPException(400, "Non puoi bannare te stesso")
    if body.mode == "perm":
        await pg_pool.execute("UPDATE users SET ban_permanent=true, banned_until=NULL WHERE id=$1::uuid", uid)
    else:
        until = datetime.now(timezone.utc) + timedelta(hours=max(1, body.hours))
        await pg_pool.execute("UPDATE users SET ban_permanent=false, banned_until=$2 WHERE id=$1::uuid", uid, until)
    return {"ok": True}

@api.post("/admin/users/{uid}/unban")
async def unban_user(uid: str, u: dict = Depends(require_admin)):
    await pg_pool.execute("UPDATE users SET ban_permanent=false, banned_until=NULL WHERE id=$1::uuid", uid)
    return {"ok": True}

@api.get("/admin/ai-settings")
async def get_ai_settings(u: dict = Depends(require_admin)):
    return {"google_ai_configured": bool(get_google_key())}

@api.post("/admin/ai-settings")
async def save_ai_settings(body: AISettingsIn, u: dict = Depends(require_admin)):
    key = body.api_key.strip()
    await pg_pool.execute(
        "INSERT INTO app_settings (id, google_ai_api_key) VALUES ('ai',$1) "
        "ON CONFLICT (id) DO UPDATE SET google_ai_api_key=$1",
        key or None,
    )
    await load_ai_settings()
    return {"google_ai_configured": bool(key)}

# ---------------- branding / logo ----------------
@api.get("/branding")
async def get_branding():
    row = await pg_pool.fetchrow("SELECT logo_path, logo_updated_at FROM app_settings WHERE id='branding'")
    if not row or not row["logo_path"]:
        return {"logo_url": None}
    ts = row["logo_updated_at"].timestamp() if row["logo_updated_at"] else 0
    return {"logo_url": f"/api/branding/logo?v={int(ts)}"}

@api.get("/branding/logo")
async def get_branding_logo():
    row = await pg_pool.fetchrow("SELECT logo_path, logo_content_type FROM app_settings WHERE id='branding'")
    if not row or not row["logo_path"]:
        raise HTTPException(404, "Nessun logo personalizzato")
    data, ct = await asyncio.to_thread(get_object, row["logo_path"])
    return Response(content=data, media_type=row["logo_content_type"] or ct)

@api.post("/admin/logo")
async def upload_logo(file: UploadFile = File(...), u: dict = Depends(require_admin)):
    ext = file_ext(file.filename)
    if ext not in LOGO_ALLOWED_EXT:
        raise HTTPException(400, f"Formato non consentito. Usa: {', '.join(sorted(LOGO_ALLOWED_EXT))}")
    data = await file.read()
    if len(data) > MAX_LOGO_SIZE:
        raise HTTPException(400, f"Immagine troppo grande (max {MAX_LOGO_SIZE // (1024*1024)}MB)")
    path = f"{APP_NAME}/branding/logo_{uuid.uuid4()}.{ext}"
    ct = file.content_type or "image/png"
    await asyncio.to_thread(put_object, path, data, ct)
    now = datetime.now(timezone.utc)
    await pg_pool.execute(
        "INSERT INTO app_settings (id, logo_path, logo_content_type, logo_updated_at) VALUES ('branding',$1,$2,$3) "
        "ON CONFLICT (id) DO UPDATE SET logo_path=$1, logo_content_type=$2, logo_updated_at=$3",
        path, ct, now)
    return {"logo_url": f"/api/branding/logo?v={int(now.timestamp())}"}

@api.delete("/admin/logo")
async def reset_logo(u: dict = Depends(require_admin)):
    await pg_pool.execute(
        "INSERT INTO app_settings (id, logo_path, logo_content_type, logo_updated_at) VALUES ('branding',NULL,NULL,NULL) "
        "ON CONFLICT (id) DO UPDATE SET logo_path=NULL, logo_content_type=NULL, logo_updated_at=NULL")
    return {"ok": True}

# ---------------- events / iscrizioni ----------------
@api.get("/events")
async def get_events(u: dict = Depends(require_approved)):
    events = clean_many(await pg_pool.fetch("SELECT * FROM events ORDER BY created_at DESC"))
    eids = [e["id"] for e in events]
    signups_rows = clean_many(await pg_pool.fetch("SELECT * FROM event_signups WHERE event_id = ANY($1::uuid[])", eids)) if eids else []
    by_event = {}
    for s in signups_rows:
        by_event.setdefault(s["event_id"], []).append(s)
    for e in events:
        signs = by_event.get(e["id"], [])
        mine = next((s for s in signs if s["user_id"] == u["id"]), None)
        e["signed_up"] = mine is not None
        e["my_option"] = mine.get("option") if mine else None
        e["signup_count"] = len(signs)
        e["option_counts"] = {opt: sum(1 for s in signs if s.get("option") == opt) for opt in (e.get("options") or [])}
        e["can_manage"] = is_staff_role(u["role"]) or e["created_by"] == u["id"]
    return events

@api.post("/events")
async def create_event(body: EventIn, u: dict = Depends(require_approved)):
    if not is_staff_role(u["role"]) and not u.get("can_create_events"):
        raise HTTPException(403, "Non autorizzato a creare iscrizioni")
    eid = str(uuid.uuid4())
    options = [o.strip() for o in body.options if o.strip()]
    caps = {k: v for k, v in (body.caps or {}).items() if v}
    row = await pg_pool.fetchrow(
        "INSERT INTO events (id,title,description,urgency,deadline,location,options,capacity,caps,created_by,created_by_name,created_at) "
        "VALUES ($1::uuid,$2,$3,$4,$5,$6,$7,$8,$9,$10::uuid,$11,$12) RETURNING *",
        eid, body.title, body.description, body.urgency, body.deadline, body.location,
        options, body.capacity, caps, u["id"], u["name"], datetime.now(timezone.utc),
    )
    event = clean(row)
    approved = await pg_pool.fetch("SELECT email FROM users WHERE status='approved'")
    emails = [a["email"] for a in approved]
    asyncio.create_task(send_event_email(event, emails))
    asyncio.create_task(send_push_to_all(
        f"Nuova iscrizione ({body.urgency})", body.title, "/events"))
    return {**event, "signup_count": 0, "signed_up": False, "my_option": None, "can_manage": True, "option_counts": {}}

@api.post("/events/{eid}/signup")
async def signup_event(eid: str, body: SignupIn, u: dict = Depends(require_approved)):
    ev = clean(await pg_pool.fetchrow("SELECT * FROM events WHERE id=$1::uuid", eid))
    if not ev:
        raise HTTPException(404, "Iscrizione non trovata")
    opts = ev.get("options") or []
    option = body.option
    if opts:
        if not option:
            raise HTTPException(400, "Scegli un'opzione")
        if option not in opts:
            raise HTTPException(400, "Opzione non valida")
    else:
        option = None
    existing = clean(await pg_pool.fetchrow("SELECT * FROM event_signups WHERE event_id=$1::uuid AND user_id=$2::uuid", eid, u["id"]))
    if existing and existing.get("option") == option:
        await pg_pool.execute("DELETE FROM event_signups WHERE event_id=$1::uuid AND user_id=$2::uuid", eid, u["id"])
        signed = False
    else:
        other_count = await pg_pool.fetchval(
            "SELECT count(*) FROM event_signups WHERE event_id=$1::uuid AND user_id<>$2::uuid", eid, u["id"])
        cap = ev.get("capacity")
        if cap and other_count >= cap:
            raise HTTPException(400, "Posti esauriti per questo evento")
        if option:
            ocap = (ev.get("caps") or {}).get(option)
            if ocap:
                ocount = await pg_pool.fetchval(
                    "SELECT count(*) FROM event_signups WHERE event_id=$1::uuid AND option=$2 AND user_id<>$3::uuid",
                    eid, option, u["id"])
                if ocount >= ocap:
                    raise HTTPException(400, f"Posti esauriti per «{option}»")
        await pg_pool.execute(
            "INSERT INTO event_signups (event_id,user_id,name,avatar_color,option,created_at) VALUES ($1::uuid,$2::uuid,$3,$4,$5,$6) "
            "ON CONFLICT (event_id,user_id) DO UPDATE SET option=$5, name=$3, avatar_color=$4, created_at=$6",
            eid, u["id"], u["name"], u.get("avatar_color", "#7C3AED"), option, datetime.now(timezone.utc))
        signed = True
    signs = clean_many(await pg_pool.fetch("SELECT * FROM event_signups WHERE event_id=$1::uuid", eid))
    oc = {opt: sum(1 for s in signs if s.get("option") == opt) for opt in opts}
    return {"signed_up": signed, "signup_count": len(signs), "my_option": option if signed else None, "option_counts": oc}

@api.get("/events/{eid}/signups")
async def event_signups(eid: str, u: dict = Depends(require_approved)):
    ev = clean(await pg_pool.fetchrow("SELECT * FROM events WHERE id=$1::uuid", eid))
    if not ev:
        raise HTTPException(404, "Non trovata")
    if not is_staff_role(u["role"]) and ev["created_by"] != u["id"]:
        raise HTTPException(403, "Solo admin o organizzatore")
    signs = clean_many(await pg_pool.fetch("SELECT * FROM event_signups WHERE event_id=$1::uuid ORDER BY created_at", eid))
    return {"signups": signs, "options": ev.get("options") or []}

@api.delete("/events/{eid}")
async def delete_event(eid: str, u: dict = Depends(require_approved)):
    ev = clean(await pg_pool.fetchrow("SELECT * FROM events WHERE id=$1::uuid", eid))
    if not ev:
        raise HTTPException(404, "Non trovata")
    if not is_staff_role(u["role"]) and ev["created_by"] != u["id"]:
        raise HTTPException(403, "Non autorizzato")
    await pg_pool.execute("DELETE FROM events WHERE id=$1::uuid", eid)
    return {"ok": True}

# ---------------- pannello corso (rappresentante, squadre, sondaggi, chat per evento) ----------------
async def event_participant_or_admin(eid: str, ev: dict, u: dict) -> bool:
    if is_staff_role(u["role"]) or ev["created_by"] == u["id"]:
        return True
    row = await pg_pool.fetchval("SELECT 1 FROM event_signups WHERE event_id=$1::uuid AND user_id=$2::uuid", eid, u["id"])
    return bool(row)

async def get_event_or_404(eid: str) -> dict:
    ev = clean(await pg_pool.fetchrow("SELECT * FROM events WHERE id=$1::uuid", eid))
    if not ev:
        raise HTTPException(404, "Iscrizione non trovata")
    return ev

async def can_manage_course(eid: str, ev: dict, u: dict) -> bool:
    if is_staff_role(u["role"]) or ev["created_by"] == u["id"]:
        return True
    rep = await pg_pool.fetchrow("SELECT user_id FROM course_reps WHERE event_id=$1::uuid", eid)
    return bool(rep and str(rep["user_id"]) == u["id"])

@api.get("/events/{eid}/course")
async def get_course(eid: str, u: dict = Depends(require_approved)):
    ev = await get_event_or_404(eid)
    if not await event_participant_or_admin(eid, ev, u):
        raise HTTPException(403, "Devi essere iscritto per accedere al pannello corso")
    rep = clean(await pg_pool.fetchrow("SELECT * FROM course_reps WHERE event_id=$1::uuid", eid))
    teams = clean_many(await pg_pool.fetch("SELECT * FROM course_teams WHERE event_id=$1::uuid ORDER BY created_at", eid))
    tids = [t["id"] for t in teams]
    members_rows = clean_many(await pg_pool.fetch("SELECT * FROM course_team_members WHERE team_id = ANY($1::uuid[])", tids)) if tids else []
    members_by_team = {}
    for m in members_rows:
        members_by_team.setdefault(m["team_id"], []).append({"user_id": m["user_id"], "name": m["name"], "position": m.get("position")})
    for t in teams:
        t["members"] = members_by_team.get(t["id"], [])
    polls = clean_many(await pg_pool.fetch("SELECT * FROM course_polls WHERE event_id=$1::uuid ORDER BY created_at DESC", eid))
    pids = [p["id"] for p in polls]
    votes_rows = clean_many(await pg_pool.fetch("SELECT * FROM course_poll_votes WHERE poll_id = ANY($1::uuid[])", pids)) if pids else []
    votes_by_poll = {}
    for v in votes_rows:
        votes_by_poll.setdefault(v["poll_id"], []).append(v)
    for p in polls:
        votes = votes_by_poll.get(p["id"], [])
        p["vote_counts"] = {opt: sum(1 for v in votes if v["option"] == opt) for opt in p["options"]}
        p["total_votes"] = len(votes)
        mine = next((v for v in votes if v["user_id"] == u["id"]), None)
        p["my_vote"] = mine["option"] if mine else None
    participants = clean_many(await pg_pool.fetch("SELECT * FROM event_signups WHERE event_id=$1::uuid", eid))
    return {
        "rep": rep, "teams": teams, "polls": polls,
        "can_manage": await can_manage_course(eid, ev, u),
        "sport_types": SPORT_TYPES, "participants": participants,
        "event_title": ev.get("title"), "event_urgency": ev.get("urgency"),
    }

@api.post("/events/{eid}/course/rep")
async def set_course_rep(eid: str, body: RepIn, u: dict = Depends(require_approved)):
    ev = await get_event_or_404(eid)
    if not (is_staff_role(u["role"]) or ev["created_by"] == u["id"]):
        raise HTTPException(403, "Solo admin o organizzatore")
    target = await pg_pool.fetchrow("SELECT name FROM event_signups WHERE event_id=$1::uuid AND user_id=$2::uuid", eid, body.user_id)
    if not target:
        raise HTTPException(400, "L'utente deve essere iscritto all'evento")
    await pg_pool.execute(
        "INSERT INTO course_reps (event_id,user_id,name,set_at) VALUES ($1::uuid,$2::uuid,$3,$4) "
        "ON CONFLICT (event_id) DO UPDATE SET user_id=$2, name=$3, set_at=$4",
        eid, body.user_id, target["name"], datetime.now(timezone.utc))
    return {"ok": True}

@api.delete("/events/{eid}/course/rep")
async def remove_course_rep(eid: str, u: dict = Depends(require_approved)):
    ev = await get_event_or_404(eid)
    if not (is_staff_role(u["role"]) or ev["created_by"] == u["id"]):
        raise HTTPException(403, "Solo admin o organizzatore")
    await pg_pool.execute("DELETE FROM course_reps WHERE event_id=$1::uuid", eid)
    return {"ok": True}

@api.post("/events/{eid}/course/teams")
async def create_team(eid: str, body: TeamIn, u: dict = Depends(require_approved)):
    ev = await get_event_or_404(eid)
    if not await can_manage_course(eid, ev, u):
        raise HTTPException(403, "Solo admin, organizzatore o capitano")
    if body.sport_type not in SPORT_TYPES:
        raise HTTPException(400, "Tipo sport non valido")
    tid = str(uuid.uuid4())
    row = await pg_pool.fetchrow(
        "INSERT INTO course_teams (id,event_id,name,sport_type,created_at) VALUES ($1::uuid,$2::uuid,$3,$4,$5) RETURNING *",
        tid, eid, body.name.strip()[:60], body.sport_type, datetime.now(timezone.utc))
    team = clean(row)
    team["members"] = []
    return team

@api.delete("/events/{eid}/course/teams/{tid}")
async def delete_team(eid: str, tid: str, u: dict = Depends(require_approved)):
    ev = await get_event_or_404(eid)
    if not await can_manage_course(eid, ev, u):
        raise HTTPException(403, "Non autorizzato")
    await pg_pool.execute("DELETE FROM course_teams WHERE id=$1::uuid AND event_id=$2::uuid", tid, eid)
    return {"ok": True}

@api.post("/events/{eid}/course/teams/{tid}/members")
async def add_team_member(eid: str, tid: str, body: TeamMemberIn, u: dict = Depends(require_approved)):
    ev = await get_event_or_404(eid)
    if not await can_manage_course(eid, ev, u):
        raise HTTPException(403, "Non autorizzato")
    team = clean(await pg_pool.fetchrow("SELECT * FROM course_teams WHERE id=$1::uuid AND event_id=$2::uuid", tid, eid))
    if not team:
        raise HTTPException(404, "Squadra non trovata")
    participant = await pg_pool.fetchrow("SELECT name FROM event_signups WHERE event_id=$1::uuid AND user_id=$2::uuid", eid, body.user_id)
    if not participant:
        raise HTTPException(400, "L'utente deve essere iscritto all'evento")
    already = await pg_pool.fetchval("SELECT 1 FROM course_team_members WHERE team_id=$1::uuid AND user_id=$2::uuid", tid, body.user_id)
    if already:
        raise HTTPException(400, "Già in squadra")
    cap = SPORT_TYPES[team["sport_type"]]["max"]
    if cap:
        count = await pg_pool.fetchval("SELECT count(*) FROM course_team_members WHERE team_id=$1::uuid", tid)
        if count >= cap:
            raise HTTPException(400, f"Squadra piena (massimo {cap})")
    await pg_pool.execute(
        "INSERT INTO course_team_members (team_id,user_id,name,position) VALUES ($1::uuid,$2::uuid,$3,NULL)",
        tid, body.user_id, participant["name"])
    return {"ok": True}

@api.post("/events/{eid}/course/teams/{tid}/members/{uid}/position")
async def set_member_position(eid: str, tid: str, uid: str, body: PositionIn, u: dict = Depends(require_approved)):
    ev = await get_event_or_404(eid)
    if not await can_manage_course(eid, ev, u):
        raise HTTPException(403, "Non autorizzato")
    exists = await pg_pool.fetchval("SELECT 1 FROM course_team_members WHERE team_id=$1::uuid AND user_id=$2::uuid", tid, uid)
    if not exists:
        raise HTTPException(404, "Giocatore non nella squadra")
    if body.position:
        await pg_pool.execute(
            "UPDATE course_team_members SET position=NULL WHERE team_id=$1::uuid AND position=$2 AND user_id<>$3::uuid",
            tid, body.position, uid)
    await pg_pool.execute(
        "UPDATE course_team_members SET position=$1 WHERE team_id=$2::uuid AND user_id=$3::uuid",
        body.position, tid, uid)
    return {"ok": True}

@api.delete("/events/{eid}/course/teams/{tid}/members/{uid}")
async def remove_team_member(eid: str, tid: str, uid: str, u: dict = Depends(require_approved)):
    ev = await get_event_or_404(eid)
    if not await can_manage_course(eid, ev, u):
        raise HTTPException(403, "Non autorizzato")
    await pg_pool.execute("DELETE FROM course_team_members WHERE team_id=$1::uuid AND user_id=$2::uuid", tid, uid)
    return {"ok": True}

@api.post("/events/{eid}/course/polls")
async def create_poll(eid: str, body: PollIn, u: dict = Depends(require_approved)):
    ev = await get_event_or_404(eid)
    if not await can_manage_course(eid, ev, u):
        raise HTTPException(403, "Non autorizzato")
    opts = [o.strip() for o in body.options if o.strip()]
    if len(opts) < 2:
        raise HTTPException(400, "Servono almeno 2 opzioni")
    pid = str(uuid.uuid4())
    await pg_pool.execute(
        "INSERT INTO course_polls (id,event_id,question,options,created_by,created_at) VALUES ($1::uuid,$2::uuid,$3,$4,$5::uuid,$6)",
        pid, eid, body.question.strip()[:200], opts, u["id"], datetime.now(timezone.utc))
    return {"ok": True}

@api.post("/events/{eid}/course/polls/{pid}/vote")
async def vote_poll(eid: str, pid: str, body: PollVoteIn, u: dict = Depends(require_approved)):
    ev = await get_event_or_404(eid)
    if not await event_participant_or_admin(eid, ev, u):
        raise HTTPException(403, "Devi essere iscritto per votare")
    poll = clean(await pg_pool.fetchrow("SELECT * FROM course_polls WHERE id=$1::uuid AND event_id=$2::uuid", pid, eid))
    if not poll:
        raise HTTPException(404, "Sondaggio non trovato")
    if body.option not in poll["options"]:
        raise HTTPException(400, "Opzione non valida")
    await pg_pool.execute(
        "INSERT INTO course_poll_votes (poll_id,user_id,option) VALUES ($1::uuid,$2::uuid,$3) "
        "ON CONFLICT (poll_id,user_id) DO UPDATE SET option=$3",
        pid, u["id"], body.option)
    return {"ok": True}

@api.delete("/events/{eid}/course/polls/{pid}")
async def delete_poll(eid: str, pid: str, u: dict = Depends(require_approved)):
    ev = await get_event_or_404(eid)
    if not await can_manage_course(eid, ev, u):
        raise HTTPException(403, "Non autorizzato")
    await pg_pool.execute("DELETE FROM course_polls WHERE id=$1::uuid AND event_id=$2::uuid", pid, eid)
    return {"ok": True}

@api.get("/events/{eid}/course/chat")
async def get_course_chat(eid: str, u: dict = Depends(require_approved)):
    ev = await get_event_or_404(eid)
    if not await event_participant_or_admin(eid, ev, u):
        raise HTTPException(403, "Devi essere iscritto per vedere la chat")
    return clean_many(await pg_pool.fetch("SELECT * FROM course_chat WHERE event_id=$1::uuid ORDER BY created_at", eid))

@api.post("/events/{eid}/course/chat")
async def post_course_chat(eid: str, body: CourseMessageIn, u: dict = Depends(require_approved)):
    ev = await get_event_or_404(eid)
    if not await event_participant_or_admin(eid, ev, u):
        raise HTTPException(403, "Devi essere iscritto per scrivere")
    text = body.text.strip()[:500]
    if not text:
        raise HTTPException(400, "Messaggio vuoto")
    clean_text = censor(text)
    blocked = await moderate_text(clean_text)
    if blocked:
        clean_text = "*" * len(clean_text)
    mid = str(uuid.uuid4())
    row = await pg_pool.fetchrow(
        "INSERT INTO course_chat (id,event_id,user_id,user_name,avatar_color,text,created_at) VALUES ($1::uuid,$2::uuid,$3::uuid,$4,$5,$6,$7) RETURNING *",
        mid, eid, u["id"], u["name"], u.get("avatar_color", "#7C3AED"), clean_text, datetime.now(timezone.utc))
    return clean(row)

# ---------------- public chat ----------------
@api.get("/chat/messages")
async def get_messages(u: dict = Depends(require_approved)):
    rows = await pg_pool.fetch("SELECT * FROM chat_messages ORDER BY created_at DESC LIMIT 80")
    msgs = clean_many(rows)
    return list(reversed(msgs))

@api.post("/chat/messages")
async def post_message(body: MessageIn, u: dict = Depends(require_approved)):
    text = body.text.strip()[:500]
    if not text:
        raise HTTPException(400, "Messaggio vuoto")
    clean_text = censor(text)
    blocked = await moderate_text(clean_text)
    if blocked:
        clean_text = "*" * len(clean_text)
    mid = str(uuid.uuid4())
    row = await pg_pool.fetchrow(
        "INSERT INTO chat_messages (id,user_id,user_name,avatar_color,text,censored,created_at) VALUES ($1::uuid,$2::uuid,$3,$4,$5,$6,$7) RETURNING *",
        mid, u["id"], u["name"], u.get("avatar_color", "#7C3AED"), clean_text, clean_text != text or blocked, datetime.now(timezone.utc))
    return clean(row)

@api.delete("/chat/messages/{mid}")
async def delete_message(mid: str, u: dict = Depends(require_admin)):
    await pg_pool.execute("DELETE FROM chat_messages WHERE id=$1::uuid", mid)
    return {"ok": True}

class BulkDeleteIn(BaseModel):
    ids: List[str]

@api.post("/chat/messages/delete")
async def bulk_delete_messages(body: BulkDeleteIn, u: dict = Depends(require_admin)):
    if not body.ids:
        return {"ok": True, "deleted": 0}
    await pg_pool.execute("DELETE FROM chat_messages WHERE id = ANY($1::uuid[])", body.ids)
    return {"ok": True, "deleted": len(body.ids)}

# ---------------- object storage ----------------
STORAGE_URL = "https://integrations.emergentagent.com/objstore/api/v1/storage"
APP_NAME = "noidi2d"
_storage_key = None

def init_storage():
    global _storage_key
    if _storage_key:
        return _storage_key
    resp = requests.post(f"{STORAGE_URL}/init", json={"emergent_key": EMERGENT_LLM_KEY}, timeout=30)
    resp.raise_for_status()
    _storage_key = resp.json()["storage_key"]
    return _storage_key

def put_object(path: str, data: bytes, content_type: str) -> dict:
    resp = requests.put(f"{STORAGE_URL}/objects/{path}",
                        headers={"X-Storage-Key": init_storage(), "Content-Type": content_type},
                        data=data, timeout=120)
    resp.raise_for_status()
    return resp.json()

def get_object(path: str):
    resp = requests.get(f"{STORAGE_URL}/objects/{path}",
                        headers={"X-Storage-Key": init_storage()}, timeout=60)
    resp.raise_for_status()
    return resp.content, resp.headers.get("Content-Type", "application/octet-stream")

# ---------------- news ----------------
@api.post("/news/upload")
async def news_upload(file: UploadFile = File(...), u: dict = Depends(require_admin)):
    await check_upload_limit(u["id"], "news")
    ext = file_ext(file.filename)
    if ext not in NEWS_ALLOWED_EXT:
        raise HTTPException(400, f"Tipo di file non consentito. Usa: {', '.join(sorted(NEWS_ALLOWED_EXT))}")
    data = await file.read()
    if len(data) > MAX_UPLOAD_SIZE:
        raise HTTPException(400, f"File troppo grande (max {MAX_UPLOAD_SIZE // (1024*1024)}MB)")
    path = f"{APP_NAME}/news/{uuid.uuid4()}.{ext}"
    ct = file.content_type or "application/octet-stream"
    result = await asyncio.to_thread(put_object, path, data, ct)
    await log_upload(u["id"], "news", len(data))
    return {"path": result["path"], "filename": file.filename, "content_type": ct, "size": result.get("size", len(data))}

@api.get("/news")
async def list_news(u: dict = Depends(require_approved)):
    return clean_many(await pg_pool.fetch("SELECT * FROM news ORDER BY created_at DESC LIMIT 200"))

@api.post("/news")
async def create_news(body: NewsIn, u: dict = Depends(require_admin)):
    nid = str(uuid.uuid4())
    row = await pg_pool.fetchrow(
        "INSERT INTO news (id,title,body,attachments,author_name,created_at) VALUES ($1::uuid,$2,$3,$4,$5,$6) RETURNING *",
        nid, body.title, body.body, body.attachments, u["name"], datetime.now(timezone.utc))
    item = clean(row)
    asyncio.create_task(send_push_to_all("Nuova news · NOI DI 2D", body.title, "/news"))
    return item

@api.delete("/news/{nid}")
async def delete_news(nid: str, u: dict = Depends(require_admin)):
    await pg_pool.execute("DELETE FROM news WHERE id=$1::uuid", nid)
    return {"ok": True}

@api.get("/news/file/{path:path}")
async def news_file(path: str, auth: str = Query(None), authorization: str = Header(None)):
    token = auth or (authorization[7:] if authorization and authorization.startswith("Bearer ") else None)
    if not token:
        raise HTTPException(401, "Non autenticato")
    try:
        jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGO])
    except jwt.InvalidTokenError:
        raise HTTPException(401, "Token non valido")
    data, ct = await asyncio.to_thread(get_object, path)
    return Response(content=data, media_type=ct)

# ---------------- interrogazioni ----------------
@api.get("/interrogazioni")
async def list_interrogazioni(u: dict = Depends(require_approved)):
    return clean_many(await pg_pool.fetch("SELECT * FROM interrogazioni WHERE user_id=$1::uuid ORDER BY created_at DESC", u["id"]))

@api.post("/interrogazioni")
async def create_interrogazione(body: InterrogazioneIn, u: dict = Depends(require_approved)):
    iid = str(uuid.uuid4())
    row = await pg_pool.fetchrow(
        "INSERT INTO interrogazioni (id,user_id,subject,tipo,num_domande,voto,created_at) VALUES ($1::uuid,$2::uuid,$3,$4,$5,$6,$7) RETURNING *",
        iid, u["id"], body.subject, body.tipo, body.num_domande, body.voto, datetime.now(timezone.utc))
    return clean(row)

@api.patch("/interrogazioni/{iid}")
async def update_interrogazione(iid: str, body: VotoIn, u: dict = Depends(require_approved)):
    await pg_pool.execute("UPDATE interrogazioni SET voto=$1 WHERE id=$2::uuid AND user_id=$3::uuid", body.voto, iid, u["id"])
    return {"ok": True}

@api.delete("/interrogazioni/{iid}")
async def delete_interrogazione(iid: str, u: dict = Depends(require_approved)):
    await pg_pool.execute("DELETE FROM interrogazioni WHERE id=$1::uuid AND user_id=$2::uuid", iid, u["id"])
    return {"ok": True}

# ---------------- reminders ----------------
@api.get("/reminders")
async def list_reminders(u: dict = Depends(require_approved)):
    items = clean_many(await pg_pool.fetch(
        "SELECT * FROM reminders WHERE is_public=true OR user_id=$1::uuid ORDER BY created_at DESC LIMIT 300", u["id"]))
    for r in items:
        r["mine"] = r["user_id"] == u["id"]
    return items

@api.post("/reminders")
async def create_reminder(body: ReminderIn, u: dict = Depends(require_approved)):
    text = body.text.strip()[:500]
    if not text:
        raise HTTPException(400, "Testo vuoto")
    rid = str(uuid.uuid4())
    row = await pg_pool.fetchrow(
        "INSERT INTO reminders (id,user_id,author_name,avatar_color,text,is_public,created_at) VALUES ($1::uuid,$2::uuid,$3,$4,$5,$6,$7) RETURNING *",
        rid, u["id"], u["name"], u.get("avatar_color", "#7C3AED"), text, body.is_public, datetime.now(timezone.utc))
    item = clean(row)
    return {**item, "mine": True}

@api.delete("/reminders/{rid}")
async def delete_reminder(rid: str, u: dict = Depends(require_approved)):
    r = clean(await pg_pool.fetchrow("SELECT * FROM reminders WHERE id=$1::uuid", rid))
    if not r:
        raise HTTPException(404, "Non trovato")
    if r["user_id"] != u["id"] and not is_staff_role(u["role"]):
        raise HTTPException(403, "Non autorizzato")
    await pg_pool.execute("DELETE FROM reminders WHERE id=$1::uuid", rid)
    return {"ok": True}

@api.post("/reminders/{rid}/report")
async def report_reminder(rid: str, u: dict = Depends(require_approved)):
    r = clean(await pg_pool.fetchrow("SELECT * FROM reminders WHERE id=$1::uuid", rid))
    if not r or not r.get("is_public"):
        raise HTTPException(404, "Reminder pubblico non trovato")
    asyncio.create_task(send_push_to_admins(
        "Reminder segnalato", f"{u['name']} ha segnalato un reminder di {r['author_name']}", "/reminders"))
    return {"ok": True}

# ---------------- avvisi privati (admin -> utente) ----------------
class AvvisoIn(BaseModel):
    user_id: str
    text: str

@api.post("/admin/avvisi")
async def send_avviso(body: AvvisoIn, u: dict = Depends(require_admin)):
    aid = str(uuid.uuid4())
    text = body.text.strip()[:500]
    await pg_pool.execute(
        "INSERT INTO avvisi (id,user_id,from_name,text,read,created_at) VALUES ($1::uuid,$2::uuid,$3,$4,false,$5)",
        aid, body.user_id, u["name"], text, datetime.now(timezone.utc))
    subs = clean_many(await pg_pool.fetch("SELECT * FROM push_subscriptions WHERE user_id=$1::uuid", body.user_id))
    asyncio.create_task(_push(subs, "Avviso dall'admin", text, "/"))
    return {"ok": True}

@api.get("/avvisi")
async def my_avvisi(u: dict = Depends(require_approved)):
    items = clean_many(await pg_pool.fetch("SELECT * FROM avvisi WHERE user_id=$1::uuid ORDER BY created_at DESC LIMIT 100", u["id"]))
    await pg_pool.execute("UPDATE avvisi SET read=true WHERE user_id=$1::uuid AND read=false", u["id"])
    return items

# ---------------- orario (provvisorio / settimana specifica / definitivo + personalizzazioni) ----------------
ORARIO_TYPES = ("provvisorio", "settimana", "definitivo")
ORARIO_DAYS = ["Lun", "Mar", "Mer", "Gio", "Ven"]
ORARIO_HOURS = [1, 2, 3, 4, 5, 6]

class OrarioIn(BaseModel):
    type: str
    grid: dict = Field(default_factory=dict)
    week_label: Optional[str] = None

class OrarioActiveIn(BaseModel):
    type: str

class OrarioPersonalIn(BaseModel):
    cell: str
    subject: Optional[str] = None
    note: Optional[str] = None

@api.get("/orario")
async def get_orario(u: dict = Depends(require_approved)):
    meta = clean(await pg_pool.fetchrow("SELECT * FROM orario_meta WHERE id='meta'")) or {}
    active = meta.get("active_type", "definitivo")
    doc = clean(await pg_pool.fetchrow("SELECT * FROM orario_settings WHERE type=$1", active)) or {}
    personal = clean(await pg_pool.fetchrow("SELECT * FROM orario_personal WHERE user_id=$1::uuid", u["id"])) or {}
    return {
        "active_type": active, "week_label": doc.get("week_label"),
        "grid": doc.get("grid") or {}, "days": ORARIO_DAYS, "hours": ORARIO_HOURS,
        "my_overrides": personal.get("cells") or {},
    }

@api.get("/admin/orario")
async def get_admin_orario(u: dict = Depends(require_admin)):
    meta = clean(await pg_pool.fetchrow("SELECT * FROM orario_meta WHERE id='meta'")) or {}
    grids = {}
    for t in ORARIO_TYPES:
        doc = clean(await pg_pool.fetchrow("SELECT * FROM orario_settings WHERE type=$1", t)) or {}
        grids[t] = {"grid": doc.get("grid") or {}, "week_label": doc.get("week_label")}
    return {"active_type": meta.get("active_type", "definitivo"), "grids": grids, "days": ORARIO_DAYS, "hours": ORARIO_HOURS}

@api.post("/admin/orario")
async def save_orario(body: OrarioIn, u: dict = Depends(require_admin)):
    if body.type not in ORARIO_TYPES:
        raise HTTPException(400, "Tipo orario non valido")
    await pg_pool.execute(
        "INSERT INTO orario_settings (type,grid,week_label,updated_at) VALUES ($1,$2,$3,$4) "
        "ON CONFLICT (type) DO UPDATE SET grid=$2, week_label=$3, updated_at=$4",
        body.type, body.grid, body.week_label, datetime.now(timezone.utc))
    return {"ok": True}

@api.post("/admin/orario/active")
async def set_active_orario(body: OrarioActiveIn, u: dict = Depends(require_admin)):
    if body.type not in ORARIO_TYPES:
        raise HTTPException(400, "Tipo orario non valido")
    await pg_pool.execute(
        "INSERT INTO orario_meta (id,active_type) VALUES ('meta',$1) ON CONFLICT (id) DO UPDATE SET active_type=$1",
        body.type)
    return {"ok": True}

@api.post("/orario/personal")
async def save_personal_orario(body: OrarioPersonalIn, u: dict = Depends(require_approved)):
    subject = (body.subject or "").strip()
    note = (body.note or "").strip()
    doc = clean(await pg_pool.fetchrow("SELECT * FROM orario_personal WHERE user_id=$1::uuid", u["id"])) or {}
    cells = doc.get("cells") or {}
    if not subject and not note:
        cells.pop(body.cell, None)
    else:
        cells[body.cell] = {"subject": subject or None, "note": note or None}
    await pg_pool.execute(
        "INSERT INTO orario_personal (user_id,cells) VALUES ($1::uuid,$2) ON CONFLICT (user_id) DO UPDATE SET cells=$2",
        u["id"], cells)
    return {"ok": True, "cells": cells}

# ---------------- messaggi privati staff <-> studenti ----------------
class DMIn(BaseModel):
    text: str

def dm_thread_id(a: str, b: str) -> str:
    return "_".join(sorted([a, b]))

async def dm_last_and_unread(me_id: str, other_id: str):
    tid = dm_thread_id(me_id, other_id)
    last = clean(await pg_pool.fetchrow("SELECT * FROM private_messages WHERE thread_id=$1 ORDER BY created_at DESC LIMIT 1", tid))
    unread = await pg_pool.fetchval("SELECT count(*) FROM private_messages WHERE thread_id=$1 AND to_id=$2::uuid AND read=false", tid, me_id)
    return last, unread

@api.get("/dm/contacts")
async def dm_contacts(u: dict = Depends(require_approved)):
    if is_staff_role(u["role"]):
        others = clean_many(await pg_pool.fetch("SELECT * FROM users WHERE status='approved' AND role='member'"))
    else:
        rows_from = await pg_pool.fetch("SELECT DISTINCT from_id FROM private_messages WHERE to_id=$1::uuid", u["id"])
        rows_to = await pg_pool.fetch("SELECT DISTINCT to_id FROM private_messages WHERE from_id=$1::uuid", u["id"])
        ids = list({str(r["from_id"]) for r in rows_from} | {str(r["to_id"]) for r in rows_to})
        others = clean_many(await pg_pool.fetch("SELECT * FROM users WHERE id = ANY($1::uuid[])", ids)) if ids else []
    contacts = []
    for x in others:
        last, unread = await dm_last_and_unread(u["id"], x["id"])
        contacts.append({**public_user(x), "last_text": last["text"] if last else None, "unread": unread})
    contacts.sort(key=lambda c: (c["unread"] == 0, c["name"]))
    return contacts

@api.get("/dm/messages/{other_id}")
async def dm_messages(other_id: str, u: dict = Depends(require_approved)):
    other = clean(await pg_pool.fetchrow("SELECT * FROM users WHERE id=$1::uuid", other_id))
    if not other:
        raise HTTPException(404, "Utente non trovato")
    if is_staff_role(u["role"]) == is_staff_role(other["role"]):
        raise HTTPException(403, "Chat privata consentita solo tra staff e studenti")
    tid = dm_thread_id(u["id"], other_id)
    msgs = clean_many(await pg_pool.fetch("SELECT * FROM private_messages WHERE thread_id=$1 ORDER BY created_at", tid))
    await pg_pool.execute("UPDATE private_messages SET read=true WHERE thread_id=$1 AND to_id=$2::uuid AND read=false", tid, u["id"])
    return msgs

@api.post("/dm/messages/{other_id}")
async def dm_send(other_id: str, body: DMIn, u: dict = Depends(require_approved)):
    other = clean(await pg_pool.fetchrow("SELECT * FROM users WHERE id=$1::uuid", other_id))
    if not other:
        raise HTTPException(404, "Utente non trovato")
    if is_staff_role(u["role"]) == is_staff_role(other["role"]):
        raise HTTPException(403, "Chat privata consentita solo tra staff e studenti")
    text = body.text.strip()[:1000]
    if not text:
        raise HTTPException(400, "Messaggio vuoto")
    mid = str(uuid.uuid4())
    row = await pg_pool.fetchrow(
        "INSERT INTO private_messages (id,thread_id,from_id,from_name,to_id,text,read,created_at) VALUES ($1::uuid,$2,$3::uuid,$4,$5::uuid,$6,false,$7) RETURNING *",
        mid, dm_thread_id(u["id"], other_id), u["id"], u["name"], other_id, text, datetime.now(timezone.utc))
    msg = clean(row)
    subs = clean_many(await pg_pool.fetch("SELECT * FROM push_subscriptions WHERE user_id=$1::uuid", other_id))
    asyncio.create_task(_push(subs, f"Messaggio privato da {u['name']}", text[:100], "/messaggi"))
    return msg

# ---------------- P2P actions ----------------
@api.post("/actions")
async def send_action(body: ActionIn, u: dict = Depends(require_approved)):
    if body.type not in ("foglietto", "secchio", "pizza", "cuore", "high_five"):
        raise HTTPException(400, "Azione non valida")
    # anti-spam: max 1 action to same target per 4 seconds
    cutoff = datetime.now(timezone.utc) - timedelta(seconds=4)
    recent = await pg_pool.fetchval(
        "SELECT 1 FROM actions WHERE from_user_id=$1::uuid AND to_user_id=$2::uuid AND created_at > $3",
        u["id"], body.to_user_id, cutoff)
    if recent:
        raise HTTPException(429, "Aspetta un attimo prima di rilanciare!")
    aid = str(uuid.uuid4())
    await pg_pool.execute(
        "INSERT INTO actions (id,from_user_id,from_user_name,to_user_id,type,seen,created_at) VALUES ($1::uuid,$2::uuid,$3,$4::uuid,$5,false,$6)",
        aid, u["id"], u["name"], body.to_user_id, body.type, datetime.now(timezone.utc))
    labels = {"foglietto": "ti ha lanciato un foglietto", "secchio": "ti ha rovesciato un secchio d'acqua",
              "pizza": "ti ha lanciato una pizza", "cuore": "ti ha mandato un cuore", "high_five": "ti ha dato il cinque"}
    asyncio.create_task(send_push_to_all(f"{u['name']} {labels[body.type]}!", "Apri NOI DI 2D per vedere!", "/"))
    return {"ok": True}

@api.get("/actions/inbox")
async def action_inbox(u: dict = Depends(require_approved)):
    actions = clean_many(await pg_pool.fetch("SELECT * FROM actions WHERE to_user_id=$1::uuid AND seen=false", u["id"]))
    if actions:
        ids = [a["id"] for a in actions]
        await pg_pool.execute("UPDATE actions SET seen=true WHERE id = ANY($1::uuid[])", ids)
    return actions

# ---------------- study ai ----------------
def make_chat(session_id: str, system: str) -> LlmChat:
    return LlmChat(api_key=EMERGENT_LLM_KEY, session_id=session_id, system_message=system)\
        .with_model("gemini", "gemini-3.1-pro-preview")

@api.post("/study/upload")
async def study_upload(file: UploadFile = File(...), u: dict = Depends(require_approved)):
    await check_upload_limit(u["id"], "study")
    fname = (file.filename or "file").lower()
    ext = file_ext(fname)
    if ext not in STUDY_ALLOWED_EXT:
        raise HTTPException(400, f"Tipo di file non supportato. Usa: {', '.join(sorted(STUDY_ALLOWED_EXT))}")
    data = await file.read()
    if len(data) > MAX_UPLOAD_SIZE:
        raise HTTPException(400, f"File troppo grande (max {MAX_UPLOAD_SIZE // (1024*1024)}MB)")
    text = ""
    try:
        if ext == "pdf":
            reader = PdfReader(io.BytesIO(data))
            text = "\n".join((p.extract_text() or "") for p in reader.pages)
        else:
            text = data.decode("utf-8", errors="ignore")
    except Exception as e:
        raise HTTPException(400, f"Impossibile leggere il file: {e}")
    text = text.strip()[:12000]
    if not text:
        raise HTTPException(400, "Nessun testo estratto dal file")
    fid = str(uuid.uuid4())
    await pg_pool.execute(
        "INSERT INTO study_files (id,user_id,filename,text,created_at) VALUES ($1::uuid,$2::uuid,$3,$4,$5)",
        fid, u["id"], file.filename, text, datetime.now(timezone.utc))
    await log_upload(u["id"], "study", len(data))
    return {"file_id": fid, "filename": file.filename, "chars": len(text)}

@api.post("/study/flashcards")
async def gen_flashcards(body: FlashcardIn, u: dict = Depends(require_approved)):
    if body.file_id:
        f = await pg_pool.fetchrow("SELECT text FROM study_files WHERE id=$1::uuid AND user_id=$2::uuid", body.file_id, u["id"])
        if not f:
            raise HTTPException(404, "File non trovato")
        source = f["text"]
    elif body.topic:
        source = f"Argomento: {body.topic}"
    else:
        raise HTTPException(400, "Fornisci un argomento o un file")
    sys_prompt = 'Sei un tutor italiano. Genera flashcard di studio. Rispondi SOLO con JSON valido: {"cards": [{"q":"domanda","a":"risposta"}]}.'
    prompt = (f"Crea {body.count} flashcard dallo studio seguente. "
              f'Rispondi SOLO con un oggetto JSON: {{"cards": [{{"q":"domanda","a":"risposta"}}]}}. '
              f"Domande brevi e chiare in italiano.\n\nMATERIALE:\n{source}")
    if get_google_key():
        try:
            raw = await google_json_reply(sys_prompt, prompt)
        except Exception as e:
            raise HTTPException(500, f"Errore AI: {e}")
        try:
            cards = json.loads(raw).get("cards", [])
        except Exception:
            raise HTTPException(500, "AI non ha restituito flashcard valide, riprova")
    else:
        chat = make_chat(f"fc-{uuid.uuid4()}", sys_prompt)
        try:
            resp = await chat.send_message(UserMessage(text=prompt))
        except Exception as e:
            raise HTTPException(500, f"Errore AI: {e}")
        raw = resp.strip()
        m = re.search(r"\[.*\]|\{.*\}", raw, re.DOTALL)
        if m:
            raw = m.group(0)
        try:
            parsed = json.loads(raw)
            cards = parsed if isinstance(parsed, list) else parsed.get("cards", [])
        except Exception:
            raise HTTPException(500, "AI non ha restituito flashcard valide, riprova")
    return {"cards": cards[:body.count]}

@api.post("/study/chat")
async def study_chat(body: StudyChatIn, u: dict = Depends(require_approved)):
    subj = body.subject or "argomenti scolastici"
    system = (f"Sei un professore italiano severo ma incoraggiante che interroga uno studente su {subj}. "
              "Fai UNA domanda alla volta, valuta la risposta precedente in modo costruttivo con un voto da 1 a 10, "
              "poi poni la domanda successiva. Sii conciso e parla in italiano.")
    if get_google_key():
        session = clean(await pg_pool.fetchrow("SELECT * FROM study_sessions WHERE session_id=$1", body.session_id)) or {"messages": []}
        messages = session.get("messages") or []
        try:
            reply = await google_chat_reply(system, messages, body.message)
        except Exception as e:
            raise HTTPException(500, f"Errore AI: {e}")
        new_messages = (messages + [{"role": "user", "text": body.message}, {"role": "model", "text": reply}])[-20:]
        await pg_pool.execute(
            "INSERT INTO study_sessions (session_id,messages,updated_at) VALUES ($1,$2,$3) "
            "ON CONFLICT (session_id) DO UPDATE SET messages=$2, updated_at=$3",
            body.session_id, new_messages, datetime.now(timezone.utc))
    else:
        chat = make_chat(f"study-{body.session_id}", system)
        try:
            reply = await chat.send_message(UserMessage(text=body.message))
        except Exception as e:
            raise HTTPException(500, f"Errore AI: {e}")
    return {"reply": reply}

# ---------------- push ----------------
@api.get("/push/vapid-public")
async def vapid_public():
    return {"key": VAPID_PUBLIC_KEY}

@api.post("/push/subscribe")
async def push_subscribe(body: SubscribeIn, u: dict = Depends(require_approved)):
    sub = body.subscription
    endpoint = sub.get("endpoint")
    await pg_pool.execute(
        "INSERT INTO push_subscriptions (id,endpoint,subscription,user_id,created_at) VALUES ($1::uuid,$2,$3,$4::uuid,$5) "
        "ON CONFLICT (endpoint) DO UPDATE SET subscription=$3, user_id=$4, created_at=$5",
        str(uuid.uuid4()), endpoint, sub, u["id"], datetime.now(timezone.utc))
    return {"ok": True}

@api.get("/")
async def root():
    return {"message": "NOI DI 2D API"}

app.include_router(api)
app.add_middleware(
    CORSMiddleware, allow_credentials=True,
    allow_origins=os.environ.get('CORS_ORIGINS', '*').split(','),
    allow_methods=["*"], allow_headers=["*"],
)

@app.on_event("startup")
async def startup():
    global pg_pool
    pg_pool = await asyncpg.create_pool(DATABASE_URL, statement_cache_size=0, min_size=1, max_size=10, init=_init_conn)
    try:
        await asyncio.to_thread(init_storage)
        logger.info("Storage initialized")
    except Exception as e:
        logger.warning(f"Storage init failed: {e}")
    await load_ai_settings()
    asyncio.create_task(study_files_cleanup_loop())
    admin_email = os.environ.get("ADMIN_EMAIL", "admin@noidi2d.it").lower()
    admin_pw = os.environ.get("ADMIN_PASSWORD", "AdminNoi2D!")
    existing = await pg_pool.fetchrow("SELECT * FROM users WHERE email=$1", admin_email)
    if not existing:
        await pg_pool.execute(
            "INSERT INTO users (id,name,email,password_hash,role,status,can_create_events,avatar_color,created_at) "
            "VALUES ($1::uuid,'Admin',$2,$3,'admin','approved',true,'#7C3AED',$4)",
            str(uuid.uuid4()), admin_email, hash_password(admin_pw), datetime.now(timezone.utc))
        logger.info("Admin seeded")
    elif not verify_password(admin_pw, existing["password_hash"]):
        await pg_pool.execute("UPDATE users SET password_hash=$1 WHERE email=$2", hash_password(admin_pw), admin_email)

@app.on_event("shutdown")
async def shutdown():
    if pg_pool:
        await pg_pool.close()
