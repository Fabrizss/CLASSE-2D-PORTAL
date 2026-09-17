# Da "sempre offline" a "sempre online con backup automatico"

## Cosa cambia
Oggi l'app ha un interruttore manuale in Dashboard con due modalità:
- **Cloud**: sempre dati live dal server, nessuna cache.
- **PWA (offline)**: salva una copia dei dati nella cache del telefono/browser, così l'app resta usabile senza internet — ma può mostrare dati vecchi se la cache non si aggiorna (è già capitato: "0 eventi" mostrati per colpa della cache non aggiornata).

La nuova modalità unica proposta:
- L'app lavora **sempre online per prima cosa**: ogni volta che apri una pagina, prova a scaricare i dati freschi dal server.
- Ogni volta che i dati freschi arrivano, l'app **salva automaticamente una copia di backup** sul dispositivo, senza che l'utente debba fare nulla.
- Se il dispositivo perde la connessione, l'app mostra automaticamente **l'ultimo backup salvato**, con un piccolo avviso in alto ("Sei offline — stai vedendo l'ultimo salvataggio") così è chiaro che non è in tempo reale.
- Appena la connessione torna, l'app **torna da sola** a mostrare i dati live e aggiorna il backup.

In pratica: non serve più scegliere una modalità a mano. L'app è online di default, e il backup offline è solo una rete di sicurezza automatica per quando manca la connessione.

## Cosa succede alle azioni quando sei offline (es. scrivere in chat, iscriverti a un evento)
Ipotesi di lavoro: mentre sei offline, queste azioni vengono **bloccate con un messaggio chiaro** ("Questa azione richiede una connessione, riprova quando sei online"), esattamente come già succede oggi in alcuni punti dell'app. Non verranno "messe in coda" per essere inviate automaticamente al ritorno della connessione — quella è una funzione più complessa che si può aggiungere in futuro se serve.
Fammi sapere se invece preferisci che alcune azioni (es. i messaggi in chat) vengano tenute in sospeso e inviate da sole quando torna la connessione.

## Interruttore manuale: resta o si elimina?
Ipotesi di lavoro: l'interruttore Cloud/PWA in Dashboard **viene tolto**, perché con il nuovo comportamento automatico non serve più — l'app si comporta sempre nel modo corretto da sola. Il pulsante "Ricarica cache dal server" resta come opzione extra per chi vuole forzare un aggiornamento immediato del backup.
Se preferisci tenere comunque l'interruttore manuale come opzione avanzata (per chi vuole restare offline anche con connessione attiva, per risparmiare dati), fammelo sapere.

## Cosa NON cambia
- Il funzionamento "installa come app" sul telefono resta identico.
- Le notifiche push non sono legate a questa modifica.
- Tutte le funzioni (eventi, chat, studio AI, messaggi, orario, news) restano le stesse: cambia solo il modo in cui l'app gestisce la connessione e la cache.

## Risultato per l'utente
- Non si vedono più dati "vecchi" per errore mentre si è online.
- L'app resta comunque consultabile (in lettura) anche senza connessione, mostrando l'ultimo backup salvato in automatico.
- Un solo comportamento, senza dover scegliere una modalità.
