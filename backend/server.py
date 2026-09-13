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
from fastapi import FastAPI, APIRouter, HTTPException, Depends, Request, UploadFile, File, Form, Header, Query, Response
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel, EmailStr, Field
from pywebpush import webpush, WebPushException
from emergentintegrations.llm.chat import LlmChat, UserMessage
from google import genai
from google.genai import types as genai_types
from pypdf import PdfReader
import io

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("noidi2d")

mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

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
    doc = await db.app_settings.find_one({"_id": "ai"})
    _google_key_cache["key"] = (doc or {}).get("google_ai_api_key") or None

def get_google_key():
    return _google_key_cache["key"]

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
    u = await db.users.find_one({"id": payload["sub"]}, {"_id": 0})
    if not u:
        raise HTTPException(status_code=401, detail="Utente non trovato")
    return u

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
    subs = await db.push_subscriptions.find({}, {"_id": 0}).to_list(1000)
    await _push(subs, title, body, url)

async def send_push_to_admins(title: str, body: str, url: str = "/"):
    admins = await db.users.find({"role": "admin"}, {"_id": 0, "id": 1}).to_list(100)
    ids = [a["id"] for a in admins]
    subs = await db.push_subscriptions.find({"user_id": {"$in": ids}}, {"_id": 0}).to_list(1000)
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
                await db.push_subscriptions.delete_one({"endpoint": s.get("endpoint")})
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
    if await db.users.find_one({"email": email}):
        raise HTTPException(status_code=400, detail="Email già registrata")
    uid = str(uuid.uuid4())
    count = await db.users.count_documents({})
    user = {
        "id": uid, "name": body.name, "email": email,
        "password_hash": hash_password(body.password),
        "role": "member", "status": "pending", "can_create_events": False,
        "avatar_color": COLORS[count % len(COLORS)],
        "created_at": now_iso(),
    }
    await db.users.insert_one(user)
    return {"message": "Registrazione ricevuta. Un admin deve approvare il tuo account prima dell'accesso."}

@api.post("/auth/login")
async def login(body: LoginIn):
    email = body.email.lower()
    u = await db.users.find_one({"email": email})
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
    users = await db.users.find({"status": "approved"}, {"_id": 0}).to_list(1000)
    return [public_user(x) for x in users if x["id"] != u["id"]]

# ---------------- admin ----------------
@api.get("/admin/users")
async def admin_users(u: dict = Depends(require_admin)):
    users = await db.users.find({}, {"_id": 0}).sort("created_at", -1).to_list(1000)
    return [public_user(x) for x in users]

@api.post("/admin/users/{uid}/approve")
async def approve_user(uid: str, u: dict = Depends(require_admin)):
    await db.users.update_one({"id": uid}, {"$set": {"status": "approved"}})
    return {"ok": True}

@api.post("/admin/users/{uid}/reject")
async def reject_user(uid: str, u: dict = Depends(require_admin)):
    await db.users.update_one({"id": uid}, {"$set": {"status": "rejected"}})
    return {"ok": True}

@api.post("/admin/users/{uid}/role/{role}")
async def set_role(uid: str, role: str, u: dict = Depends(require_admin)):
    if role not in ("admin", "member", "professore"):
        raise HTTPException(400, "Ruolo non valido")
    await db.users.update_one({"id": uid}, {"$set": {"role": role}})
    return {"ok": True}

@api.post("/admin/users/{uid}/authorize/{value}")
async def authorize_events(uid: str, value: int, u: dict = Depends(require_admin)):
    await db.users.update_one({"id": uid}, {"$set": {"can_create_events": bool(value)}})
    return {"ok": True}

@api.delete("/admin/users/{uid}")
async def delete_user(uid: str, u: dict = Depends(require_admin)):
    await db.users.delete_one({"id": uid})
    return {"ok": True}

@api.post("/admin/users/{uid}/ban")
async def ban_user(uid: str, body: BanIn, u: dict = Depends(require_admin)):
    if uid == u["id"]:
        raise HTTPException(400, "Non puoi bannare te stesso")
    if body.mode == "perm":
        await db.users.update_one({"id": uid}, {"$set": {"ban_permanent": True, "banned_until": None}})
    else:
        until = (datetime.now(timezone.utc) + timedelta(hours=max(1, body.hours))).isoformat()
        await db.users.update_one({"id": uid}, {"$set": {"ban_permanent": False, "banned_until": until}})
    return {"ok": True}

@api.post("/admin/users/{uid}/unban")
async def unban_user(uid: str, u: dict = Depends(require_admin)):
    await db.users.update_one({"id": uid}, {"$set": {"ban_permanent": False, "banned_until": None}})
    return {"ok": True}

@api.get("/admin/ai-settings")
async def get_ai_settings(u: dict = Depends(require_admin)):
    return {"google_ai_configured": bool(get_google_key())}

@api.post("/admin/ai-settings")
async def save_ai_settings(body: AISettingsIn, u: dict = Depends(require_admin)):
    key = body.api_key.strip()
    await db.app_settings.update_one({"_id": "ai"}, {"$set": {"google_ai_api_key": key or None}}, upsert=True)
    await load_ai_settings()
    return {"google_ai_configured": bool(key)}

# ---------------- events / iscrizioni ----------------
@api.get("/events")
async def get_events(u: dict = Depends(require_approved)):
    events = await db.events.find({}, {"_id": 0}).sort("created_at", -1).to_list(500)
    for e in events:
        signs = e.get("signups", [])
        mine = next((s for s in signs if s["user_id"] == u["id"]), None)
        e["signed_up"] = mine is not None
        e["my_option"] = mine.get("option") if mine else None
        e["signup_count"] = len(signs)
        e["option_counts"] = {opt: sum(1 for s in signs if s.get("option") == opt) for opt in e.get("options", [])}
        e["can_manage"] = is_staff_role(u["role"]) or e["created_by"] == u["id"]
        e.pop("signups", None)
    return events

@api.post("/events")
async def create_event(body: EventIn, u: dict = Depends(require_approved)):
    if not is_staff_role(u["role"]) and not u.get("can_create_events"):
        raise HTTPException(403, "Non autorizzato a creare iscrizioni")
    eid = str(uuid.uuid4())
    event = {
        "id": eid, "title": body.title, "description": body.description,
        "urgency": body.urgency, "deadline": body.deadline, "location": body.location,
        "options": [o.strip() for o in body.options if o.strip()],
        "capacity": body.capacity, "caps": {k: v for k, v in (body.caps or {}).items() if v},
        "created_by": u["id"], "created_by_name": u["name"],
        "signups": [], "created_at": now_iso(),
    }
    await db.events.insert_one(dict(event))
    approved = await db.users.find({"status": "approved"}, {"_id": 0, "email": 1}).to_list(1000)
    emails = [a["email"] for a in approved]
    asyncio.create_task(send_event_email(event, emails))
    asyncio.create_task(send_push_to_all(
        f"Nuova iscrizione ({body.urgency})", body.title, "/events"))
    event.pop("signups", None)
    event.pop("_id", None)
    return {**event, "signup_count": 0, "signed_up": False, "my_option": None, "can_manage": True, "option_counts": {}}

@api.post("/events/{eid}/signup")
async def signup_event(eid: str, body: SignupIn, u: dict = Depends(require_approved)):
    ev = await db.events.find_one({"id": eid})
    if not ev:
        raise HTTPException(404, "Iscrizione non trovata")
    opts = ev.get("options", [])
    option = body.option
    if opts:
        if not option:
            raise HTTPException(400, "Scegli un'opzione")
        if option not in opts:
            raise HTTPException(400, "Opzione non valida")
    else:
        option = None
    existing = next((s for s in ev.get("signups", []) if s["user_id"] == u["id"]), None)
    signs = [s for s in ev.get("signups", []) if s["user_id"] != u["id"]]
    if existing and existing.get("option") == option:
        signed = False
    else:
        cap = ev.get("capacity")
        if cap and len(signs) >= cap:
            raise HTTPException(400, "Posti esauriti per questo evento")
        ocap = (ev.get("caps") or {}).get(option) if option else None
        if ocap and sum(1 for s in signs if s.get("option") == option) >= ocap:
            raise HTTPException(400, f"Posti esauriti per «{option}»")
        signs.append({"user_id": u["id"], "name": u["name"], "avatar_color": u.get("avatar_color", "#7C3AED"), "option": option, "at": now_iso()})
        signed = True
    await db.events.update_one({"id": eid}, {"$set": {"signups": signs}})
    oc = {opt: sum(1 for s in signs if s.get("option") == opt) for opt in opts}
    return {"signed_up": signed, "signup_count": len(signs), "my_option": option if signed else None, "option_counts": oc}

@api.get("/events/{eid}/signups")
async def event_signups(eid: str, u: dict = Depends(require_approved)):
    ev = await db.events.find_one({"id": eid}, {"_id": 0})
    if not ev:
        raise HTTPException(404, "Non trovata")
    if not is_staff_role(u["role"]) and ev["created_by"] != u["id"]:
        raise HTTPException(403, "Solo admin o organizzatore")
    return {"signups": ev.get("signups", []), "options": ev.get("options", [])}

@api.delete("/events/{eid}")
async def delete_event(eid: str, u: dict = Depends(require_approved)):
    ev = await db.events.find_one({"id": eid})
    if not ev:
        raise HTTPException(404, "Non trovata")
    if not is_staff_role(u["role"]) and ev["created_by"] != u["id"]:
        raise HTTPException(403, "Non autorizzato")
    await db.events.delete_one({"id": eid})
    return {"ok": True}

# ---------------- pannello corso (rappresentante, squadre, sondaggi, chat per evento) ----------------
def event_participant_or_admin(ev: dict, u: dict) -> bool:
    if is_staff_role(u["role"]) or ev["created_by"] == u["id"]:
        return True
    return any(s["user_id"] == u["id"] for s in ev.get("signups", []))

async def get_event_or_404(eid: str) -> dict:
    ev = await db.events.find_one({"id": eid})
    if not ev:
        raise HTTPException(404, "Iscrizione non trovata")
    return ev

async def can_manage_course(eid: str, ev: dict, u: dict) -> bool:
    if is_staff_role(u["role"]) or ev["created_by"] == u["id"]:
        return True
    rep = await db.course_reps.find_one({"event_id": eid})
    return bool(rep and rep["user_id"] == u["id"])

@api.get("/events/{eid}/course")
async def get_course(eid: str, u: dict = Depends(require_approved)):
    ev = await get_event_or_404(eid)
    if not event_participant_or_admin(ev, u):
        raise HTTPException(403, "Devi essere iscritto per accedere al pannello corso")
    rep = await db.course_reps.find_one({"event_id": eid}, {"_id": 0})
    teams = await db.course_teams.find({"event_id": eid}, {"_id": 0}).to_list(100)
    polls = await db.course_polls.find({"event_id": eid}, {"_id": 0}).sort("created_at", -1).to_list(100)
    for p in polls:
        votes = p.pop("votes", [])
        p["vote_counts"] = {opt: sum(1 for v in votes if v["option"] == opt) for opt in p["options"]}
        p["total_votes"] = len(votes)
        mine = next((v for v in votes if v["user_id"] == u["id"]), None)
        p["my_vote"] = mine["option"] if mine else None
    return {
        "rep": rep, "teams": teams, "polls": polls,
        "can_manage": await can_manage_course(eid, ev, u),
        "sport_types": SPORT_TYPES, "participants": ev.get("signups", []),
        "event_title": ev.get("title"), "event_urgency": ev.get("urgency"),
    }

@api.post("/events/{eid}/course/rep")
async def set_course_rep(eid: str, body: RepIn, u: dict = Depends(require_approved)):
    ev = await get_event_or_404(eid)
    if not (is_staff_role(u["role"]) or ev["created_by"] == u["id"]):
        raise HTTPException(403, "Solo admin o organizzatore")
    target = next((s for s in ev.get("signups", []) if s["user_id"] == body.user_id), None)
    if not target:
        raise HTTPException(400, "L'utente deve essere iscritto all'evento")
    await db.course_reps.update_one(
        {"event_id": eid},
        {"$set": {"event_id": eid, "user_id": body.user_id, "name": target["name"], "set_at": now_iso()}},
        upsert=True,
    )
    return {"ok": True}

@api.delete("/events/{eid}/course/rep")
async def remove_course_rep(eid: str, u: dict = Depends(require_approved)):
    ev = await get_event_or_404(eid)
    if not (is_staff_role(u["role"]) or ev["created_by"] == u["id"]):
        raise HTTPException(403, "Solo admin o organizzatore")
    await db.course_reps.delete_one({"event_id": eid})
    return {"ok": True}

@api.post("/events/{eid}/course/teams")
async def create_team(eid: str, body: TeamIn, u: dict = Depends(require_approved)):
    ev = await get_event_or_404(eid)
    if not await can_manage_course(eid, ev, u):
        raise HTTPException(403, "Solo admin, organizzatore o capitano")
    if body.sport_type not in SPORT_TYPES:
        raise HTTPException(400, "Tipo sport non valido")
    team = {"id": str(uuid.uuid4()), "event_id": eid, "name": body.name.strip()[:60],
            "sport_type": body.sport_type, "members": [], "created_at": now_iso()}
    await db.course_teams.insert_one(dict(team))
    team.pop("_id", None)
    return team

@api.delete("/events/{eid}/course/teams/{tid}")
async def delete_team(eid: str, tid: str, u: dict = Depends(require_approved)):
    ev = await get_event_or_404(eid)
    if not await can_manage_course(eid, ev, u):
        raise HTTPException(403, "Non autorizzato")
    await db.course_teams.delete_one({"id": tid, "event_id": eid})
    return {"ok": True}

@api.post("/events/{eid}/course/teams/{tid}/members")
async def add_team_member(eid: str, tid: str, body: TeamMemberIn, u: dict = Depends(require_approved)):
    ev = await get_event_or_404(eid)
    if not await can_manage_course(eid, ev, u):
        raise HTTPException(403, "Non autorizzato")
    team = await db.course_teams.find_one({"id": tid, "event_id": eid})
    if not team:
        raise HTTPException(404, "Squadra non trovata")
    participant = next((s for s in ev.get("signups", []) if s["user_id"] == body.user_id), None)
    if not participant:
        raise HTTPException(400, "L'utente deve essere iscritto all'evento")
    if any(m["user_id"] == body.user_id for m in team.get("members", [])):
        raise HTTPException(400, "Già in squadra")
    cap = SPORT_TYPES[team["sport_type"]]["max"]
    if cap and len(team.get("members", [])) >= cap:
        raise HTTPException(400, f"Squadra piena (massimo {cap})")
    await db.course_teams.update_one({"id": tid}, {"$push": {"members": {"user_id": body.user_id, "name": participant["name"]}}})
    return {"ok": True}

@api.delete("/events/{eid}/course/teams/{tid}/members/{uid}")
async def remove_team_member(eid: str, tid: str, uid: str, u: dict = Depends(require_approved)):
    ev = await get_event_or_404(eid)
    if not await can_manage_course(eid, ev, u):
        raise HTTPException(403, "Non autorizzato")
    await db.course_teams.update_one({"id": tid}, {"$pull": {"members": {"user_id": uid}}})
    return {"ok": True}

@api.post("/events/{eid}/course/polls")
async def create_poll(eid: str, body: PollIn, u: dict = Depends(require_approved)):
    ev = await get_event_or_404(eid)
    if not await can_manage_course(eid, ev, u):
        raise HTTPException(403, "Non autorizzato")
    opts = [o.strip() for o in body.options if o.strip()]
    if len(opts) < 2:
        raise HTTPException(400, "Servono almeno 2 opzioni")
    poll = {"id": str(uuid.uuid4()), "event_id": eid, "question": body.question.strip()[:200],
            "options": opts, "votes": [], "created_by": u["id"], "created_at": now_iso()}
    await db.course_polls.insert_one(dict(poll))
    return {"ok": True}

@api.post("/events/{eid}/course/polls/{pid}/vote")
async def vote_poll(eid: str, pid: str, body: PollVoteIn, u: dict = Depends(require_approved)):
    ev = await get_event_or_404(eid)
    if not event_participant_or_admin(ev, u):
        raise HTTPException(403, "Devi essere iscritto per votare")
    poll = await db.course_polls.find_one({"id": pid, "event_id": eid})
    if not poll:
        raise HTTPException(404, "Sondaggio non trovato")
    if body.option not in poll["options"]:
        raise HTTPException(400, "Opzione non valida")
    votes = [v for v in poll.get("votes", []) if v["user_id"] != u["id"]]
    votes.append({"user_id": u["id"], "option": body.option})
    await db.course_polls.update_one({"id": pid}, {"$set": {"votes": votes}})
    return {"ok": True}

@api.delete("/events/{eid}/course/polls/{pid}")
async def delete_poll(eid: str, pid: str, u: dict = Depends(require_approved)):
    ev = await get_event_or_404(eid)
    if not await can_manage_course(eid, ev, u):
        raise HTTPException(403, "Non autorizzato")
    await db.course_polls.delete_one({"id": pid, "event_id": eid})
    return {"ok": True}

@api.get("/events/{eid}/course/chat")
async def get_course_chat(eid: str, u: dict = Depends(require_approved)):
    ev = await get_event_or_404(eid)
    if not event_participant_or_admin(ev, u):
        raise HTTPException(403, "Devi essere iscritto per vedere la chat")
    return await db.course_chat.find({"event_id": eid}, {"_id": 0}).sort("created_at", 1).to_list(300)

@api.post("/events/{eid}/course/chat")
async def post_course_chat(eid: str, body: CourseMessageIn, u: dict = Depends(require_approved)):
    ev = await get_event_or_404(eid)
    if not event_participant_or_admin(ev, u):
        raise HTTPException(403, "Devi essere iscritto per scrivere")
    text = body.text.strip()[:500]
    if not text:
        raise HTTPException(400, "Messaggio vuoto")
    clean = censor(text)
    blocked = await moderate_text(clean)
    if blocked:
        clean = "*" * len(clean)
    msg = {"id": str(uuid.uuid4()), "event_id": eid, "user_id": u["id"], "user_name": u["name"],
           "avatar_color": u.get("avatar_color", "#7C3AED"), "text": clean, "created_at": now_iso()}
    await db.course_chat.insert_one(dict(msg))
    return msg

# ---------------- public chat ----------------
@api.get("/chat/messages")
async def get_messages(u: dict = Depends(require_approved)):
    msgs = await db.chat_messages.find({}, {"_id": 0}).sort("created_at", -1).limit(80).to_list(80)
    return list(reversed(msgs))

@api.post("/chat/messages")
async def post_message(body: MessageIn, u: dict = Depends(require_approved)):
    text = body.text.strip()[:500]
    if not text:
        raise HTTPException(400, "Messaggio vuoto")
    clean = censor(text)
    blocked = await moderate_text(clean)
    if blocked:
        clean = "*" * len(clean)
    msg = {
        "id": str(uuid.uuid4()), "user_id": u["id"], "user_name": u["name"],
        "avatar_color": u.get("avatar_color", "#7C3AED"),
        "text": clean, "censored": clean != text or blocked, "created_at": now_iso(),
    }
    await db.chat_messages.insert_one(dict(msg))
    return msg

@api.delete("/chat/messages/{mid}")
async def delete_message(mid: str, u: dict = Depends(require_admin)):
    await db.chat_messages.delete_one({"id": mid})
    return {"ok": True}

class BulkDeleteIn(BaseModel):
    ids: List[str]

@api.post("/chat/messages/delete")
async def bulk_delete_messages(body: BulkDeleteIn, u: dict = Depends(require_admin)):
    await db.chat_messages.delete_many({"id": {"$in": body.ids}})
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
    data = await file.read()
    ext = file.filename.split(".")[-1] if "." in (file.filename or "") else "bin"
    path = f"{APP_NAME}/news/{uuid.uuid4()}.{ext}"
    ct = file.content_type or "application/octet-stream"
    result = await asyncio.to_thread(put_object, path, data, ct)
    return {"path": result["path"], "filename": file.filename, "content_type": ct, "size": result.get("size", len(data))}

@api.get("/news")
async def list_news(u: dict = Depends(require_approved)):
    return await db.news.find({}, {"_id": 0}).sort("created_at", -1).to_list(200)

@api.post("/news")
async def create_news(body: NewsIn, u: dict = Depends(require_admin)):
    item = {"id": str(uuid.uuid4()), "title": body.title, "body": body.body,
            "attachments": body.attachments, "author_name": u["name"], "created_at": now_iso()}
    await db.news.insert_one(dict(item))
    asyncio.create_task(send_push_to_all("Nuova news · NOI DI 2D", body.title, "/news"))
    item.pop("_id", None)
    return item

@api.delete("/news/{nid}")
async def delete_news(nid: str, u: dict = Depends(require_admin)):
    await db.news.delete_one({"id": nid})
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
    return await db.interrogazioni.find({"user_id": u["id"]}, {"_id": 0}).sort("created_at", -1).to_list(200)

@api.post("/interrogazioni")
async def create_interrogazione(body: InterrogazioneIn, u: dict = Depends(require_approved)):
    item = {"id": str(uuid.uuid4()), "user_id": u["id"], "subject": body.subject,
            "tipo": body.tipo, "num_domande": body.num_domande, "voto": body.voto, "created_at": now_iso()}
    await db.interrogazioni.insert_one(dict(item))
    item.pop("_id", None)
    return item

@api.patch("/interrogazioni/{iid}")
async def update_interrogazione(iid: str, body: VotoIn, u: dict = Depends(require_approved)):
    await db.interrogazioni.update_one({"id": iid, "user_id": u["id"]}, {"$set": {"voto": body.voto}})
    return {"ok": True}

@api.delete("/interrogazioni/{iid}")
async def delete_interrogazione(iid: str, u: dict = Depends(require_approved)):
    await db.interrogazioni.delete_one({"id": iid, "user_id": u["id"]})
    return {"ok": True}

# ---------------- reminders ----------------
@api.get("/reminders")
async def list_reminders(u: dict = Depends(require_approved)):
    items = await db.reminders.find(
        {"$or": [{"is_public": True}, {"user_id": u["id"]}]}, {"_id": 0}
    ).sort("created_at", -1).to_list(300)
    for r in items:
        r["mine"] = r["user_id"] == u["id"]
    return items

@api.post("/reminders")
async def create_reminder(body: ReminderIn, u: dict = Depends(require_approved)):
    text = body.text.strip()[:500]
    if not text:
        raise HTTPException(400, "Testo vuoto")
    item = {"id": str(uuid.uuid4()), "user_id": u["id"], "author_name": u["name"],
            "avatar_color": u.get("avatar_color", "#7C3AED"), "text": text,
            "is_public": body.is_public, "created_at": now_iso()}
    await db.reminders.insert_one(dict(item))
    item.pop("_id", None)
    return {**item, "mine": True}

@api.delete("/reminders/{rid}")
async def delete_reminder(rid: str, u: dict = Depends(require_approved)):
    r = await db.reminders.find_one({"id": rid})
    if not r:
        raise HTTPException(404, "Non trovato")
    if r["user_id"] != u["id"] and not is_staff_role(u["role"]):
        raise HTTPException(403, "Non autorizzato")
    await db.reminders.delete_one({"id": rid})
    return {"ok": True}

@api.post("/reminders/{rid}/report")
async def report_reminder(rid: str, u: dict = Depends(require_approved)):
    r = await db.reminders.find_one({"id": rid})
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
    item = {"id": str(uuid.uuid4()), "user_id": body.user_id, "from_name": u["name"],
            "text": body.text.strip()[:500], "read": False, "created_at": now_iso()}
    await db.avvisi.insert_one(dict(item))
    subs = await db.push_subscriptions.find({"user_id": body.user_id}, {"_id": 0}).to_list(100)
    asyncio.create_task(_push(subs, "Avviso dall'admin", item["text"], "/"))
    return {"ok": True}

@api.get("/avvisi")
async def my_avvisi(u: dict = Depends(require_approved)):
    items = await db.avvisi.find({"user_id": u["id"]}, {"_id": 0}).sort("created_at", -1).to_list(100)
    await db.avvisi.update_many({"user_id": u["id"], "read": False}, {"$set": {"read": True}})
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
    meta = await db.orario_meta.find_one({"_id": "meta"}) or {}
    active = meta.get("active_type", "definitivo")
    doc = await db.orario_settings.find_one({"_id": active}) or {}
    personal = await db.orario_personal.find_one({"_id": u["id"]}) or {}
    return {
        "active_type": active, "week_label": doc.get("week_label"),
        "grid": doc.get("grid", {}), "days": ORARIO_DAYS, "hours": ORARIO_HOURS,
        "my_overrides": personal.get("cells", {}),
    }

@api.get("/admin/orario")
async def get_admin_orario(u: dict = Depends(require_admin)):
    meta = await db.orario_meta.find_one({"_id": "meta"}) or {}
    grids = {}
    for t in ORARIO_TYPES:
        doc = await db.orario_settings.find_one({"_id": t}) or {}
        grids[t] = {"grid": doc.get("grid", {}), "week_label": doc.get("week_label")}
    return {"active_type": meta.get("active_type", "definitivo"), "grids": grids, "days": ORARIO_DAYS, "hours": ORARIO_HOURS}

@api.post("/admin/orario")
async def save_orario(body: OrarioIn, u: dict = Depends(require_admin)):
    if body.type not in ORARIO_TYPES:
        raise HTTPException(400, "Tipo orario non valido")
    await db.orario_settings.update_one(
        {"_id": body.type},
        {"$set": {"grid": body.grid, "week_label": body.week_label, "updated_at": now_iso()}},
        upsert=True,
    )
    return {"ok": True}

@api.post("/admin/orario/active")
async def set_active_orario(body: OrarioActiveIn, u: dict = Depends(require_admin)):
    if body.type not in ORARIO_TYPES:
        raise HTTPException(400, "Tipo orario non valido")
    await db.orario_meta.update_one({"_id": "meta"}, {"$set": {"active_type": body.type}}, upsert=True)
    return {"ok": True}

@api.post("/orario/personal")
async def save_personal_orario(body: OrarioPersonalIn, u: dict = Depends(require_approved)):
    subject = (body.subject or "").strip()
    note = (body.note or "").strip()
    doc = await db.orario_personal.find_one({"_id": u["id"]}) or {}
    cells = doc.get("cells", {})
    if not subject and not note:
        cells.pop(body.cell, None)
    else:
        cells[body.cell] = {"subject": subject or None, "note": note or None}
    await db.orario_personal.update_one({"_id": u["id"]}, {"$set": {"cells": cells}}, upsert=True)
    return {"ok": True, "cells": cells}

# ---------------- messaggi privati staff <-> studenti ----------------
class DMIn(BaseModel):
    text: str

def dm_thread_id(a: str, b: str) -> str:
    return "_".join(sorted([a, b]))

async def dm_last_and_unread(me_id: str, other_id: str):
    tid = dm_thread_id(me_id, other_id)
    last = await db.private_messages.find_one({"thread_id": tid}, {"_id": 0}, sort=[("created_at", -1)])
    unread = await db.private_messages.count_documents({"thread_id": tid, "to_id": me_id, "read": False})
    return last, unread

@api.get("/dm/contacts")
async def dm_contacts(u: dict = Depends(require_approved)):
    if is_staff_role(u["role"]):
        others = await db.users.find({"status": "approved", "role": "member"}, {"_id": 0}).to_list(1000)
    else:
        staff_from = await db.private_messages.distinct("from_id", {"to_id": u["id"]})
        staff_to = await db.private_messages.distinct("to_id", {"from_id": u["id"]})
        ids = list(set(staff_from + staff_to))
        others = await db.users.find({"id": {"$in": ids}}, {"_id": 0}).to_list(200)
    contacts = []
    for x in others:
        last, unread = await dm_last_and_unread(u["id"], x["id"])
        contacts.append({**public_user(x), "last_text": last["text"] if last else None, "unread": unread})
    contacts.sort(key=lambda c: (c["unread"] == 0, c["name"]))
    return contacts

@api.get("/dm/messages/{other_id}")
async def dm_messages(other_id: str, u: dict = Depends(require_approved)):
    other = await db.users.find_one({"id": other_id})
    if not other:
        raise HTTPException(404, "Utente non trovato")
    if is_staff_role(u["role"]) == is_staff_role(other["role"]):
        raise HTTPException(403, "Chat privata consentita solo tra staff e studenti")
    tid = dm_thread_id(u["id"], other_id)
    msgs = await db.private_messages.find({"thread_id": tid}, {"_id": 0}).sort("created_at", 1).to_list(500)
    await db.private_messages.update_many({"thread_id": tid, "to_id": u["id"], "read": False}, {"$set": {"read": True}})
    return msgs

@api.post("/dm/messages/{other_id}")
async def dm_send(other_id: str, body: DMIn, u: dict = Depends(require_approved)):
    other = await db.users.find_one({"id": other_id})
    if not other:
        raise HTTPException(404, "Utente non trovato")
    if is_staff_role(u["role"]) == is_staff_role(other["role"]):
        raise HTTPException(403, "Chat privata consentita solo tra staff e studenti")
    text = body.text.strip()[:1000]
    if not text:
        raise HTTPException(400, "Messaggio vuoto")
    msg = {"id": str(uuid.uuid4()), "thread_id": dm_thread_id(u["id"], other_id), "from_id": u["id"], "from_name": u["name"],
           "to_id": other_id, "text": text, "read": False, "created_at": now_iso()}
    await db.private_messages.insert_one(dict(msg))
    subs = await db.push_subscriptions.find({"user_id": other_id}, {"_id": 0}).to_list(50)
    asyncio.create_task(_push(subs, f"Messaggio privato da {u['name']}", text[:100], "/messaggi"))
    return msg

# ---------------- P2P actions ----------------
@api.post("/actions")
async def send_action(body: ActionIn, u: dict = Depends(require_approved)):
    if body.type not in ("foglietto", "secchio", "pizza", "cuore", "high_five"):
        raise HTTPException(400, "Azione non valida")
    # anti-spam: max 1 action to same target per 4 seconds
    recent = await db.actions.find_one({
        "from_user_id": u["id"], "to_user_id": body.to_user_id,
        "created_at": {"$gt": (datetime.now(timezone.utc) - timedelta(seconds=4)).isoformat()}
    })
    if recent:
        raise HTTPException(429, "Aspetta un attimo prima di rilanciare!")
    action = {
        "id": str(uuid.uuid4()), "from_user_id": u["id"], "from_user_name": u["name"],
        "to_user_id": body.to_user_id, "type": body.type,
        "seen": False, "created_at": now_iso(),
    }
    await db.actions.insert_one(dict(action))
    labels = {"foglietto": "ti ha lanciato un foglietto", "secchio": "ti ha rovesciato un secchio d'acqua",
              "pizza": "ti ha lanciato una pizza", "cuore": "ti ha mandato un cuore", "high_five": "ti ha dato il cinque"}
    asyncio.create_task(send_push_to_all(f"{u['name']} {labels[body.type]}!", "Apri NOI DI 2D per vedere!", "/"))
    return {"ok": True}

@api.get("/actions/inbox")
async def action_inbox(u: dict = Depends(require_approved)):
    actions = await db.actions.find({"to_user_id": u["id"], "seen": False}, {"_id": 0}).to_list(50)
    if actions:
        ids = [a["id"] for a in actions]
        await db.actions.update_many({"id": {"$in": ids}}, {"$set": {"seen": True}})
    return actions

# ---------------- study ai ----------------
def make_chat(session_id: str, system: str) -> LlmChat:
    return LlmChat(api_key=EMERGENT_LLM_KEY, session_id=session_id, system_message=system)\
        .with_model("gemini", "gemini-3.1-pro-preview")

@api.post("/study/upload")
async def study_upload(file: UploadFile = File(...), u: dict = Depends(require_approved)):
    data = await file.read()
    text = ""
    fname = (file.filename or "file").lower()
    try:
        if fname.endswith(".pdf"):
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
    await db.study_files.insert_one({
        "id": fid, "user_id": u["id"], "filename": file.filename,
        "text": text, "created_at": now_iso(),
    })
    return {"file_id": fid, "filename": file.filename, "chars": len(text)}

@api.post("/study/flashcards")
async def gen_flashcards(body: FlashcardIn, u: dict = Depends(require_approved)):
    if body.file_id:
        f = await db.study_files.find_one({"id": body.file_id, "user_id": u["id"]})
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
        session = await db.study_sessions.find_one({"session_id": body.session_id}) or {"messages": []}
        try:
            reply = await google_chat_reply(system, session["messages"], body.message)
        except Exception as e:
            raise HTTPException(500, f"Errore AI: {e}")
        new_messages = (session["messages"] + [{"role": "user", "text": body.message}, {"role": "model", "text": reply}])[-20:]
        await db.study_sessions.update_one({"session_id": body.session_id}, {"$set": {"messages": new_messages}}, upsert=True)
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
    await db.push_subscriptions.update_one(
        {"endpoint": endpoint},
        {"$set": {"endpoint": endpoint, "subscription": sub, "user_id": u["id"], "created_at": now_iso()}},
        upsert=True,
    )
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
    await db.users.create_index("email", unique=True)
    await db.users.create_index("id")
    await db.push_subscriptions.create_index("endpoint", unique=True)
    try:
        await asyncio.to_thread(init_storage)
        logger.info("Storage initialized")
    except Exception as e:
        logger.warning(f"Storage init failed: {e}")
    await load_ai_settings()
    admin_email = os.environ.get("ADMIN_EMAIL", "admin@noidi2d.it").lower()
    admin_pw = os.environ.get("ADMIN_PASSWORD", "AdminNoi2D!")
    existing = await db.users.find_one({"email": admin_email})
    if not existing:
        await db.users.insert_one({
            "id": str(uuid.uuid4()), "name": "Admin", "email": admin_email,
            "password_hash": hash_password(admin_pw), "role": "admin",
            "status": "approved", "can_create_events": True,
            "avatar_color": "#7C3AED", "created_at": now_iso(),
        })
        logger.info("Admin seeded")
    elif not verify_password(admin_pw, existing["password_hash"]):
        await db.users.update_one({"email": admin_email}, {"$set": {"password_hash": hash_password(admin_pw)}})

@app.on_event("shutdown")
async def shutdown():
    client.close()
