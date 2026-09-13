import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Bot, Copy, Check, KeyRound, Github, Rocket, Database, Users } from "lucide-react";
import { api, errMsg } from "@/lib/api";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Accordion, AccordionItem, AccordionTrigger, AccordionContent } from "@/components/ui/accordion";

const SUPABASE_SQL = `-- NOI DI 2D — schema Supabase (Postgres) di riferimento
-- Replica le collection MongoDB in tabelle relazionali equivalenti.

create table users (
  id uuid primary key default gen_random_uuid(),
  name text not null,
  email text unique not null,
  password_hash text not null,
  role text not null default 'member' check (role in ('member','admin','professore')),
  status text not null default 'pending' check (status in ('pending','approved','rejected')),
  can_create_events boolean default false,
  avatar_color text default '#7C3AED',
  ban_permanent boolean default false,
  banned_until timestamptz,
  created_at timestamptz default now()
);

create table events (
  id uuid primary key default gen_random_uuid(),
  title text not null,
  description text not null,
  urgency text default 'normale',
  deadline text,
  location text,
  options jsonb default '[]',
  capacity integer,
  caps jsonb default '{}',
  created_by uuid references users(id),
  created_by_name text,
  created_at timestamptz default now()
);

create table event_signups (
  id uuid primary key default gen_random_uuid(),
  event_id uuid references events(id) on delete cascade,
  user_id uuid references users(id) on delete cascade,
  name text,
  avatar_color text,
  option text,
  created_at timestamptz default now(),
  unique (event_id, user_id)
);

create table chat_messages (
  id uuid primary key default gen_random_uuid(),
  user_id uuid references users(id),
  user_name text,
  avatar_color text,
  text text not null,
  censored boolean default false,
  created_at timestamptz default now()
);

create table news (
  id uuid primary key default gen_random_uuid(),
  title text not null,
  body text not null,
  attachments jsonb default '[]',
  author_name text,
  created_at timestamptz default now()
);

create table interrogazioni (
  id uuid primary key default gen_random_uuid(),
  user_id uuid references users(id) on delete cascade,
  subject text,
  tipo text default 'orale',
  num_domande integer default 0,
  voto numeric,
  created_at timestamptz default now()
);

create table reminders (
  id uuid primary key default gen_random_uuid(),
  user_id uuid references users(id) on delete cascade,
  author_name text,
  avatar_color text,
  text text not null,
  is_public boolean default false,
  created_at timestamptz default now()
);

create table avvisi (
  id uuid primary key default gen_random_uuid(),
  user_id uuid references users(id) on delete cascade,
  from_name text,
  text text not null,
  read boolean default false,
  created_at timestamptz default now()
);

create table push_subscriptions (
  id uuid primary key default gen_random_uuid(),
  endpoint text unique not null,
  subscription jsonb not null,
  user_id uuid references users(id) on delete cascade,
  created_at timestamptz default now()
);

create table course_reps (
  event_id uuid primary key references events(id) on delete cascade,
  user_id uuid references users(id),
  name text,
  set_at timestamptz default now()
);

create table course_teams (
  id uuid primary key default gen_random_uuid(),
  event_id uuid references events(id) on delete cascade,
  name text not null,
  sport_type text not null,
  created_at timestamptz default now()
);

create table course_team_members (
  team_id uuid references course_teams(id) on delete cascade,
  user_id uuid references users(id) on delete cascade,
  name text,
  position text,
  primary key (team_id, user_id)
);

create table course_polls (
  id uuid primary key default gen_random_uuid(),
  event_id uuid references events(id) on delete cascade,
  question text not null,
  options jsonb not null,
  created_by uuid references users(id),
  created_at timestamptz default now()
);

create table course_poll_votes (
  poll_id uuid references course_polls(id) on delete cascade,
  user_id uuid references users(id) on delete cascade,
  option text not null,
  primary key (poll_id, user_id)
);

create table course_chat (
  id uuid primary key default gen_random_uuid(),
  event_id uuid references events(id) on delete cascade,
  user_id uuid references users(id),
  user_name text,
  avatar_color text,
  text text not null,
  created_at timestamptz default now()
);

create table app_settings (
  id text primary key,
  google_ai_api_key text
);
insert into app_settings (id, google_ai_api_key) values ('ai', null) on conflict (id) do nothing;

create table orario_settings (
  type text primary key check (type in ('provvisorio','settimana','definitivo')),
  grid jsonb default '{}',
  week_label text,
  updated_at timestamptz default now()
);

create table orario_meta (
  id text primary key default 'meta',
  active_type text default 'definitivo'
);

create table orario_personal (
  user_id uuid primary key references users(id) on delete cascade,
  cells jsonb default '{}'
);

create table private_messages (
  id uuid primary key default gen_random_uuid(),
  thread_id text not null,
  from_id uuid references users(id),
  from_name text,
  to_id uuid references users(id),
  text text not null,
  read boolean default false,
  created_at timestamptz default now()
);

-- Abilita RLS su tutte le tabelle (le policy vanno scritte in base al tuo sistema di login,
-- perché questa app usa JWT custom e non Supabase Auth: senza policy dedicate,
-- l'accesso ai dati deve passare dal service role lato server, non dal client).
alter table users enable row level security;
alter table events enable row level security;
alter table event_signups enable row level security;
alter table chat_messages enable row level security;
alter table news enable row level security;
alter table interrogazioni enable row level security;
alter table reminders enable row level security;
alter table avvisi enable row level security;
alter table push_subscriptions enable row level security;
alter table course_reps enable row level security;
alter table course_teams enable row level security;
alter table course_team_members enable row level security;
alter table course_polls enable row level security;
alter table course_poll_votes enable row level security;
alter table course_chat enable row level security;
alter table app_settings enable row level security;
alter table orario_settings enable row level security;
alter table orario_meta enable row level security;
alter table orario_personal enable row level security;
alter table private_messages enable row level security;`;

function CopyBlock({ text, testId }) {
  const [copied, setCopied] = useState(false);
  const copy = async () => {
    try { await navigator.clipboard.writeText(text); setCopied(true); toast.success("Copiato negli appunti"); setTimeout(() => setCopied(false), 2000); }
    catch { toast.error("Copia non riuscita"); }
  };
  return (
    <div className="relative mt-2">
      <Button size="sm" variant="secondary" onClick={copy} data-testid={testId}
        className="absolute top-2 right-2 rounded-full gap-1.5 h-7 text-xs z-10">
        {copied ? <Check size={13} /> : <Copy size={13} />} {copied ? "Copiato" : "Copia script"}
      </Button>
      <pre className="bg-secondary/60 border border-border rounded-xl p-4 pt-10 text-xs overflow-x-auto max-h-96 whitespace-pre">{text}</pre>
    </div>
  );
}

export function GuideSistemi() {
  const [configured, setConfigured] = useState(false);
  const [key, setKey] = useState("");
  const [saving, setSaving] = useState(false);

  const load = () => api.get("/admin/ai-settings").then((r) => setConfigured(r.data.google_ai_configured)).catch(() => {});
  useEffect(() => { load(); }, []);

  const save = async () => {
    if (!key.trim()) return toast.error("Inserisci la chiave Google AI");
    setSaving(true);
    try { const { data } = await api.post("/admin/ai-settings", { api_key: key.trim() }); setConfigured(data.google_ai_configured); setKey(""); toast.success("Chiave Google AI salvata: ora l'AI la usa in tutta l'app"); }
    catch (e) { toast.error(errMsg(e)); }
    finally { setSaving(false); }
  };
  const remove = async () => {
    setSaving(true);
    try { const { data } = await api.post("/admin/ai-settings", { api_key: "" }); setConfigured(data.google_ai_configured); toast.success("Chiave rimossa, torni a usare il motore Gemini predefinito"); }
    catch (e) { toast.error(errMsg(e)); }
    finally { setSaving(false); }
  };

  return (
    <div className="space-y-6" data-testid="guide-sistemi-section">
      <Card className="p-6 border-border">
        <div className="flex items-center gap-2.5">
          <div className="w-10 h-10 rounded-xl bg-primary/10 text-primary grid place-items-center"><Bot size={20} /></div>
          <div className="flex-1">
            <h3 className="font-head text-lg font-semibold">Motore AI · Google AI (Gemini)</h3>
            <p className="text-xs text-muted-foreground">Collega la tua chiave Google AI Studio per usarla in Studio AI, flashcard e moderazione della chat.</p>
          </div>
          <Badge variant="outline" className={`rounded-full ${configured ? "bg-emerald-500/15 text-emerald-600 border-emerald-500/30" : "bg-secondary text-muted-foreground"}`} data-testid="ai-status-badge">
            {configured ? "Google AI attivo" : "Gemini (predefinito)"}
          </Badge>
        </div>
        <div className="mt-4 flex flex-col sm:flex-row gap-2">
          <Input type="password" value={key} onChange={(e) => setKey(e.target.value)} placeholder="AIza..." data-testid="groq-key-input" className="flex-1" autoComplete="off" />
          <Button onClick={save} disabled={saving} data-testid="save-groq-key-btn" className="rounded-full gap-2 whitespace-nowrap"><KeyRound size={15} /> Salva chiave</Button>
          {configured && <Button variant="outline" onClick={remove} disabled={saving} data-testid="remove-groq-key-btn" className="rounded-full whitespace-nowrap">Rimuovi</Button>}
        </div>
        <p className="text-xs text-muted-foreground mt-2">Ottieni la chiave su <a href="https://aistudio.google.com/api-keys" target="_blank" rel="noreferrer" className="text-primary underline">aistudio.google.com/api-keys</a>. Non viene mai mostrata di nuovo dopo il salvataggio.</p>
      </Card>

      <Card className="p-6 border-border">
        <h3 className="font-head text-lg font-semibold mb-1">Guide e Sistemi</h3>
        <p className="text-xs text-muted-foreground mb-2">Tutto quello che serve per esportare, deployare altrove e replicare il database su un altro server.</p>
        <Accordion type="single" collapsible className="w-full" data-testid="guide-accordion">
          <AccordionItem value="ruoli">
            <AccordionTrigger data-testid="guide-ruoli-trigger" className="gap-2"><Users size={16} className="text-primary shrink-0" /> Ruoli, Orario e Messaggi privati</AccordionTrigger>
            <AccordionContent className="text-sm text-muted-foreground space-y-2">
              <p><b>Ruoli:</b> Admin (controllo completo), Professore (stessi permessi di un admin: eventi, news, moderazione, orario, chiave AI, più la possibilità di scrivere in privato agli studenti), Studente (membro). Cambia ruolo scegliendolo dal menu a tendina accanto a ogni utente nella tab "Tutti i membri".</p>
              <p><b>Orario:</b> nella tab "Orario" gestisci tre versioni (Provvisorio, Settimana specifica, Definitivo) e scegli quale è "attiva": quella appare nel widget Orario della Dashboard di tutti. Ogni studente può aggiungere sopra un appunto o una materia personale, visibile solo a lui.</p>
              <p><b>Messaggi privati:</b> Admin e Professori trovano in "Messaggi" l'elenco degli studenti approvati e possono scrivere in privato; lo studente riceve una notifica push e trova la chat nella sua pagina "Messaggi".</p>
              <p><b>Squadre e formazioni:</b> nel Pannello Corso di ogni iscrizione, le squadre di calcio e pallavolo mostrano un campo stilizzato dove assegnare ogni giocatore a una posizione (portiere/difesa/centrocampo/attacco o zone 1-6); basket e sport generico restano a lista semplice.</p>
            </AccordionContent>
          </AccordionItem>
          <AccordionItem value="github">
            <AccordionTrigger data-testid="guide-github-trigger" className="gap-2"><Github size={16} className="text-primary shrink-0" /> Come salvare il codice su GitHub</AccordionTrigger>
            <AccordionContent className="text-sm text-muted-foreground space-y-2">
              <p>1. Nella chat di Emergent (dove parli con l'agente), trova il pulsante <b>"Salva su GitHub"</b> nella barra di input.</p>
              <p>2. Collega il tuo account GitHub la prima volta: ti verrà chiesto di autorizzare l'accesso.</p>
              <p>3. Scegli il repository (nuovo o esistente): il codice completo (frontend + backend) viene esportato lì, versione dopo versione.</p>
              <p>4. Da GitHub puoi clonare il progetto in locale con <code>git clone</code> oppure collegarlo direttamente a un servizio di hosting.</p>
            </AccordionContent>
          </AccordionItem>
          <AccordionItem value="deploy">
            <AccordionTrigger data-testid="guide-deploy-trigger" className="gap-2"><Rocket size={16} className="text-primary shrink-0" /> Come deployare l'app su un altro sito</AccordionTrigger>
            <AccordionContent className="text-sm text-muted-foreground space-y-2">
              <p>1. Esporta il codice su GitHub (guida sopra).</p>
              <p>2. <b>Frontend (React)</b>: collega il repo a Vercel o Netlify, imposta come cartella <code>/frontend</code> e la variabile <code>REACT_APP_BACKEND_URL</code> con l'URL pubblico del backend.</p>
              <p>3. <b>Backend (FastAPI)</b>: collega il repo a Railway o Render, cartella <code>/backend</code>, comando di avvio <code>uvicorn server:app --host 0.0.0.0 --port $PORT</code>, e configura le variabili d'ambiente (<code>MONGO_URL</code> o le credenziali Supabase, <code>JWT_SECRET</code>, chiavi VAPID, ecc.).</p>
              <p>4. Aggiorna <code>CORS_ORIGINS</code> nel backend con il dominio del frontend pubblicato.</p>
              <p>5. Collega un dominio personalizzato dalle impostazioni del servizio di hosting scelto, se lo possiedi.</p>
            </AccordionContent>
          </AccordionItem>
          <AccordionItem value="supabase">
            <AccordionTrigger data-testid="guide-supabase-trigger" className="gap-2"><Database size={16} className="text-primary shrink-0" /> Come replicare il server su Supabase</AccordionTrigger>
            <AccordionContent className="text-sm text-muted-foreground space-y-2">
              <p>Supabase è un database Postgres gestito con API integrate: puoi usarlo come server esterno alternativo, se un giorno vuoi lasciare l'infrastruttura attuale.</p>
              <p>1. Crea un progetto gratuito su <a href="https://supabase.com" target="_blank" rel="noreferrer" className="text-primary underline">supabase.com</a>.</p>
              <p>2. Vai su <b>SQL Editor</b> → <b>New query</b>, incolla lo script qui sotto e premi <b>Run</b>: crea tutte le tabelle equivalenti a quelle usate oggi (utenti, iscrizioni, chat, news, ecc.).</p>
              <p>3. Copia <b>Project URL</b> e <b>API Key</b> da Project Settings → API: serviranno al backend per collegarsi.</p>
              <p>4. Nota: questa app oggi usa un login JWT personalizzato (non l'Auth di Supabase), quindi le query vanno fatte lato server con la <i>service role key</i>, non direttamente dal browser.</p>
              <CopyBlock text={SUPABASE_SQL} testId="copy-supabase-sql" />
            </AccordionContent>
          </AccordionItem>
        </Accordion>
      </Card>
    </div>
  );
}
