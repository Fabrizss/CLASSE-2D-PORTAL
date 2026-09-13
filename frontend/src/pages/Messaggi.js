import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import { Send, Mail, UserCircle2 } from "lucide-react";
import { api, errMsg, requireOnline } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { isStaff } from "@/lib/roles";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";

export default function Messaggi() {
  const { user } = useAuth();
  const staff = isStaff(user?.role);
  const [contacts, setContacts] = useState([]);
  const [active, setActive] = useState(null);
  const [msgs, setMsgs] = useState([]);
  const [text, setText] = useState("");
  const endRef = useRef();

  const loadContacts = () => api.get("/dm/contacts").then((r) => setContacts(r.data)).catch(() => {});
  const loadMsgs = (id) => api.get(`/dm/messages/${id}`).then((r) => setMsgs(r.data)).catch(() => {});

  useEffect(() => { loadContacts(); const iv = setInterval(loadContacts, 5000); return () => clearInterval(iv); }, []);
  useEffect(() => {
    if (!active) return;
    loadMsgs(active.id);
    const iv = setInterval(() => loadMsgs(active.id), 3000);
    return () => clearInterval(iv);
  }, [active?.id]);
  useEffect(() => { endRef.current?.scrollIntoView({ behavior: "smooth" }); }, [msgs]);

  const send = async (e) => {
    e.preventDefault();
    const t = text.trim();
    if (!t || !active) return;
    try { requireOnline(); } catch (err) { return toast.error(err.message); }
    setText("");
    try { const { data } = await api.post(`/dm/messages/${active.id}`, { text: t }); setMsgs((m) => [...m, data]); }
    catch (err) { toast.error(errMsg(err)); }
  };

  return (
    <div className="max-w-5xl mx-auto space-y-6" data-testid="messaggi-page">
      <div>
        <p className="text-xs tracking-[0.25em] uppercase font-bold text-muted-foreground">Comunicazioni</p>
        <h1 className="font-head text-4xl font-black tracking-tight mt-1">Messaggi Privati</h1>
        <p className="text-muted-foreground mt-2 text-sm">
          {staff ? "Scrivi in privato a uno studente." : "Qui trovi le conversazioni private con i professori."}
        </p>
      </div>

      <Card className="border-border overflow-hidden grid grid-cols-1 sm:grid-cols-[260px_1fr] h-[520px]">
        <div className="border-r border-border overflow-y-auto bg-secondary/20">
          {contacts.length === 0 && (
            <p className="text-center text-muted-foreground text-sm py-10 px-4">
              {staff ? "Nessuno studente approvato ancora." : "Nessun messaggio: aspetta che un professore ti scriva."}
            </p>
          )}
          {contacts.map((c) => (
            <button key={c.id} onClick={() => setActive(c)} data-testid={`dm-contact-${c.id}`}
              className={`w-full flex items-center gap-2.5 p-3 text-left border-b border-border/60 transition-colors ${active?.id === c.id ? "bg-primary/10" : "hover:bg-secondary/60"}`}>
              <div className="w-8 h-8 rounded-full grid place-items-center text-white text-xs font-bold shrink-0" style={{ background: c.avatar_color }}>
                {c.name?.[0]?.toUpperCase()}
              </div>
              <div className="flex-1 min-w-0">
                <p className="text-sm font-semibold truncate">{c.name}</p>
                <p className="text-xs text-muted-foreground truncate">{c.last_text || "Nessun messaggio"}</p>
              </div>
              {c.unread > 0 && <Badge className="rounded-full bg-primary text-primary-foreground text-xs h-5 min-w-5 grid place-items-center px-1.5">{c.unread}</Badge>}
            </button>
          ))}
        </div>
        <div className="flex flex-col">
          {!active ? (
            <div className="flex-1 grid place-items-center text-muted-foreground text-sm gap-2 flex-col">
              <UserCircle2 size={32} className="opacity-40" />
              Seleziona una conversazione
            </div>
          ) : (
            <>
              <div className="p-3 border-b border-border flex items-center gap-2">
                <Mail size={15} className="text-primary" />
                <span className="font-semibold text-sm">{active.name}</span>
              </div>
              <div className="flex-1 overflow-y-auto p-4 space-y-3">
                {msgs.length === 0 && <p className="text-center text-muted-foreground text-sm py-16">Nessun messaggio. Scrivi il primo!</p>}
                {msgs.map((m) => {
                  const mine = m.from_id === user?.id;
                  return (
                    <div key={m.id} className={`flex ${mine ? "justify-end" : "justify-start"}`} data-testid="dm-message">
                      <div className={`max-w-[75%] px-4 py-2 rounded-2xl text-sm ${mine ? "bg-primary text-primary-foreground rounded-br-md" : "bg-card border border-border rounded-bl-md"}`}>
                        {m.text}
                      </div>
                    </div>
                  );
                })}
                <div ref={endRef} />
              </div>
              <form onSubmit={send} className="p-3 border-t border-border flex gap-2">
                <Input value={text} onChange={(e) => setText(e.target.value)} data-testid="dm-input" placeholder="Scrivi un messaggio privato…" maxLength={1000} className="rounded-full" />
                <Button type="submit" size="icon" data-testid="dm-send-btn" className="rounded-full shrink-0"><Send size={16} /></Button>
              </form>
            </>
          )}
        </div>
      </Card>
    </div>
  );
}
