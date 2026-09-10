# PRD — NOI DI 2D (Portale della classe)

## Problem statement
Portale gestione classe "NOI DI 2D" (scuola, italiano), design moderno/minimalista Liquid Glass viola. Iscrizioni eventi con urgenza + notifiche push (Web Push PWA) + email, aiuto studio AI (interrogazioni, upload file, flashcards), canale pubblico censurato, azioni divertenti tra compagni in tempo reale, canale news con allegati, pannello admin con approvazione membri e ban.

## Stack
React + FastAPI + MongoDB. Auth JWT (localStorage Bearer). AI: Gemini 3.1 Pro via Emergent LLM key. Email: Resend (opzionale). Web Push: pywebpush/VAPID. Object storage: Emergent objstore per allegati news.

## Personas
- Admin: gestisce membri (approva/ban/ruoli/autorizzazioni), crea eventi/news, modera chat.
- Membro autorizzato: può creare iscrizioni.
- Membro: iscrizioni, studio AI, chat, azioni, news.

## Implemented (2026-09)
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
