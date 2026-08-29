# PRD — NOI DI 2D (Portale della classe)

## Problem statement
Portale gestione classe "NOI DI 2D" (scuola, italiano), design moderno/minimalista Liquid Glass viola. Iscrizioni eventi con urgenza + notifiche push (Web Push PWA) + email, aiuto studio AI (interrogazioni, upload file, flashcards), canale pubblico censurato, azioni divertenti tra compagni in tempo reale, canale news con allegati, pannello admin con approvazione membri e ban.

## Stack
React + FastAPI + MongoDB. Auth JWT (localStorage Bearer). AI: Gemini 3.1 Pro via Emergent LLM key. Email: Resend (opzionale). Web Push: pywebpush/VAPID. Object storage: Emergent objstore per allegati news.

## Personas
- Admin: gestisce membri (approva/ban/ruoli/autorizzazioni), crea eventi/news, modera chat.
- Membro autorizzato: può creare iscrizioni.
- Membro: iscrizioni, studio AI, chat, azioni, news.

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
- P1: Realtime via WebSocket al posto del polling (chat/azioni/news).
- P2: Edit eventi/news; reazioni ai messaggi; notifiche push mirate per utente.
- P2: Ricerca/paginazione news e chat.

## Credentials
Admin: admin@noidi2d.it / AdminNoi2D! (vedi /app/memory/test_credentials.md)
