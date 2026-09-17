# PRD — NOI DI 2D (Portale della classe)

## Problem statement
Portale gestione classe "NOI DI 2D" (scuola, italiano), design moderno/minimalista Liquid Glass viola. Iscrizioni eventi con urgenza + notifiche push (Web Push PWA) + email, aiuto studio AI (interrogazioni, upload file, flashcards), canale pubblico censurato, azioni divertenti tra compagni in tempo reale, canale news con allegati, pannello admin con approvazione membri e ban.

## Stack
React + FastAPI + PostgreSQL (Supabase, via asyncpg — migrato da MongoDB il 2026-09-17). Auth JWT (localStorage Bearer). AI: Google Gemini (admin-configurabile) con fallback Emergent LLM key. Email: Resend (opzionale). Web Push: pywebpush/VAPID. Object storage: Emergent objstore per allegati news.

## Implemented (2026-09-17, migrazione DB)
- Backend riscritto completamente da MongoDB/Motor a PostgreSQL/asyncpg (Supabase). `DATABASE_URL` in backend/.env. Pool asyncpg con `_init_conn` per codec jsonb, helper `clean()`/`clean_many()` per serializzare UUID/datetime nelle risposte JSON.
- Tutti gli endpoint verificati (27/27 test pytest in `/app/backend/tests/test_postgres_migration.py`): auth, admin/users, eventi+iscrizioni, pannello corso (squadre/formazioni/posizioni/sondaggi/chat), chat pubblica, messaggi privati, orario, news, reminder, interrogazioni, azioni P2P, AI settings, study.
- Account prof@noidi2d.it / ProfNoi2D! ricreato manualmente sul nuovo DB (dati Mongo precedenti non migrati, solo Admin auto-seed da .env).
- Fix cosmetico: pluralizzazione "1 evento" vs "N eventi" in Dashboard.js.
- Nota nota in test: il servizio mongodb resta avviato in supervisor ma non più usato dal backend (leftover innocuo).
- Nota UX: se la Dashboard mostra un conteggio eventi non aggiornato, è la cache PWA offline stantia — usare toggle "Cloud" o "Ricarica cache dal server".

## Personas
- Admin: gestisce membri (approva/ban/ruoli/autorizzazioni), crea eventi/news, modera chat.
- Membro autorizzato: può creare iscrizioni.
- Membro: iscrizioni, studio AI, chat, azioni, news.

## Implemented (2026-09, round 3)
- Squadre calcio (7/11) e pallavolo (6/3): campo stilizzato interattivo per posizionare le formazioni (portiere/difesa/centrocampo/attacco per il calcio, zone 1-6 per la pallavolo) invece della semplice lista. Cliccando uno slot vuoto si assegna un giocatore dalla rosa già iscritta alla squadra; i non posizionati restano in "panchina". Basket e sport generico restano a lista semplice.
- Nuovo endpoint POST /events/{eid}/course/teams/{tid}/members/{uid}/position per assegnare/spostare/rimuovere una posizione.

## Implemented (2026-09, round 2)
- AI ora usa Google AI (Gemini) con chiave admin-configurabile invece di Groq (Groq rimosso). Endpoint /api/admin/ai-settings ora usa `google_ai_configured`. Fallback a Gemini via Emergent Universal Key se nessuna chiave impostata (invariato).
- Widget "Orario" in Dashboard + tab "Orario" in Admin: 3 versioni (provvisorio/settimana/definitivo), una attiva mostrata a tutti, overlay personale (materia+appunto) per singolo utente senza toccare l'orario ufficiale.
- Ruolo "Professore": permessi admin-equivalenti su tutto il backend (require_admin accetta admin o professore) + funzione esclusiva Messaggi Privati con gli studenti. Assegnabile ciclando l'icona ruolo in Admin (Admin→Professore→Membro).
- Pagina "/messaggi" (Direct Messages staff↔studenti): staff vede tutti gli studenti approvati e scrive per primo; lo studente vede solo lo staff che gli ha scritto. Bloccato staff↔staff e studente↔studente (403). Notifica push al destinatario.
- Guide Admin aggiornate: sezione AI rinominata Google AI, nuovo accordion "Ruoli, Orario e Messaggi privati", script SQL Supabase aggiornato con le nuove tabelle.
- Account test: prof@noidi2d.it / ProfNoi2D! (ruolo professore) creato per i test.

## Implemented (2026-09)
- Dashboard: card "Modalità app" con switch Cloud (nessuna cache, sempre dati live) / PWA (offline, comportamento precedente), preferenza salvata in localStorage e sempre modificabile. Pulsante "Ricarica cache dal server" che disinstalla il service worker e svuota tutte le cache per risolvere versioni bloccate/stantie nel browser. Bump versione cache SW (v3) per invalidare le cache precedenti già installate sui dispositivi.
- Chiave Groq configurabile da admin (tab "Guide e Sistemi"): se impostata, sostituisce Gemini in Studio AI (interrogazioni multi-turno con storico in `study_sessions`), flashcard (JSON mode) e moderazione AI della chat pubblica + chat corso. Senza chiave, fallback automatico a Gemini/censura a parole (comportamento invariato). Chiave mai restituita al frontend dopo il salvataggio.
- Pannello Corso per ogni Iscrizione/Evento (`/events/{id}/corso`): rappresentante/capitano (assegnato da admin/organizzatore tra gli iscritti), formazioni sportive (calcio7/11, basket, volley3, pallavolo, generico) con roster manuale e limite massimo per formato, sondaggi (creabili da admin/organizzatore/capitano, votabili dagli iscritti), chat dedicata al corso (solo iscritti+admin). Icona trofeo su Events.js visibile solo a iscritti/organizzatore/admin.
- Sezione Admin "Guide e Sistemi": guida a fisarmonica con export GitHub, deploy esterno (Vercel/Railway) e script SQL Supabase completo (copiabile) per chi vuole replicare lo schema su un altro server.

## Implemented (2026-06)
- Auth email/password JWT, registrazione con stato pending → approvazione admin. Primo admin auto-seed da backend/.env.
- Pannello Admin: approva/rifiuta, ruoli, autorizza eventi, ban temp/perm + unban, elimina.
- Iscrizioni: urgenza, deadline, luogo, gruppi/opzioni con capienza per gruppo e capienza totale, notifiche push + email, vista iscritti (nomi) per admin/organizzatore.
- Aiuto Studio AI: upload PDF/testo, interrogazione (chat Gemini con voto), flashcard da argomento o file.
- Canale pubblico: chat con censura automatica; admin elimina singolo msg o multi-selezione.
- News: admin pubblica news con allegati (object storage), download autenticato, push a tutti.
- Azioni P2P: foglietto/secchio/pizza/cuore/cinque con animazioni su entrambi i lati (polling 2s) + anti-spam 4s.
- PWA installabile (manifest, service worker) con guida iPad; Web Push ad app chiusa.
- Design Liquid Glass (glass utils, blob background), tema chiaro/scuro, font Outfit/Manrope.

## Backlog
- P1: Email dominio @noidi2d.it (richiede possesso dominio + verifica DNS su Resend; non fattibile senza dominio).
- P1: Realtime via WebSocket al posto del polling (chat/azioni/news/chat corso).
- P1: Video popup dashboard caricato dall'admin (richiesto, non ancora implementato).
- P2: Edit eventi/news; reazioni ai messaggi; notifiche push mirate per utente.
- P2: Ricerca/paginazione news e chat.
- P2: Cifratura at-rest della chiave Groq in Mongo (oggi plaintext, mai esposta al frontend — osservazione da code review, non bloccante per un portale di classe).

## Credentials
Admin: admin@noidi2d.it / AdminNoi2D! (vedi /app/memory/test_credentials.md)
