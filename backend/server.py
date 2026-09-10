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
from pydantic import BaseModel, EmailStr
from pywebpush import webpush, WebPushException
from emergentintegrations.llm.chat import LlmChat, UserMessage
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
    if u["role"] != "admin":
        raise HTTPException(status_code=403, detail="Solo gli admin")
    return u

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
    if role not in ("admin", "member"):
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
        e["can_manage"] = u["role"] == "admin" or e["created_by"] == u["id"]
        e.pop("signups", None)
    return events

@api.post("/events")
async def create_event(body: EventIn, u: dict = Depends(require_approved)):
    if u["role"] != "admin" and not u.get("can_create_events"):
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
    if u["role"] != "admin" and ev["created_by"] != u["id"]:
        raise HTTPException(403, "Solo admin o organizzatore")
    return {"signups": ev.get("signups", []), "options": ev.get("options", [])}

@api.delete("/events/{eid}")
async def delete_event(eid: str, u: dict = Depends(require_approved)):
    ev = await db.events.find_one({"id": eid})
    if not ev:
        raise HTTPException(404, "Non trovata")
    if u["role"] != "admin" and ev["created_by"] != u["id"]:
        raise HTTPException(403, "Non autorizzato")
    await db.events.delete_one({"id": eid})
    return {"ok": True}

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
    msg = {
        "id": str(uuid.uuid4()), "user_id": u["id"], "user_name": u["name"],
        "avatar_color": u.get("avatar_color", "#7C3AED"),
        "text": clean, "censored": clean != text, "created_at": now_iso(),
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
    if r["user_id"] != u["id"] and u["role"] != "admin":
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
    chat = make_chat(f"fc-{uuid.uuid4()}",
        "Sei un tutor italiano. Genera flashcard di studio. Rispondi SOLO con JSON valido.")
    prompt = (f"Crea {body.count} flashcard dallo studio seguente. "
              f'Rispondi SOLO con un array JSON: [{{"q":"domanda","a":"risposta"}}]. '
              f"Domande brevi e chiare in italiano.\n\nMATERIALE:\n{source}")
    try:
        resp = await chat.send_message(UserMessage(text=prompt))
    except Exception as e:
        raise HTTPException(500, f"Errore AI: {e}")
    raw = resp.strip()
    m = re.search(r"\[.*\]", raw, re.DOTALL)
    if m:
        raw = m.group(0)
    try:
        cards = json.loads(raw)
    except Exception:
        raise HTTPException(500, "AI non ha restituito flashcard valide, riprova")
    return {"cards": cards[:body.count]}

@api.post("/study/chat")
async def study_chat(body: StudyChatIn, u: dict = Depends(require_approved)):
    subj = body.subject or "argomenti scolastici"
    system = (f"Sei un professore italiano severo ma incoraggiante che interroga uno studente su {subj}. "
              "Fai UNA domanda alla volta, valuta la risposta precedente in modo costruttivo con un voto da 1 a 10, "
              "poi poni la domanda successiva. Sii conciso e parla in italiano.")
    chat = make_chat(f"study-{body.session_id}", system)
    try:
        resp = await chat.send_message(UserMessage(text=body.message))
    except Exception as e:
        raise HTTPException(500, f"Errore AI: {e}")
    return {"reply": resp}

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
