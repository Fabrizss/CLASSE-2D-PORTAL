import { useEffect, useRef, useState } from "react";
import { Send, ShieldCheck, Trash2, CheckSquare } from "lucide-react";
import { api, errMsg, requireOnline } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { useOnline } from "@/hooks/useOnline";
import { isStaff } from "@/lib/roles";
import { toast } from "sonner";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

export default function Chat() {
  const { user } = useAuth();
  const [msgs, setMsgs] = useState([]);
  const [text, setText] = useState("");
  const [selMode, setSelMode] = useState(false);
  const [selected, setSelected] = useState(new Set());
  const endRef = useRef();
  const isAdmin = isStaff(user?.role);
  const online = useOnline();

  const load = () => { if (!navigator.onLine) return; api.get("/chat/messages").then((r) => setMsgs(r.data)).catch(() => {}); };
  useEffect(() => { load(); const iv = setInterval(load, 3000); return () => clearInterval(iv); }, []);
  useEffect(() => { endRef.current?.scrollIntoView({ behavior: "smooth" }); }, [msgs]);

  const send = async (e) => {
    e.preventDefault();
    const t = text.trim();
    if (!t) return;
    try { requireOnline(); } catch (err) { return toast.error(err.message); }
    setText("");
    try { const { data } = await api.post("/chat/messages", { text: t }); setMsgs((m) => [...m, data]); if (data.censored) toast.info("Messaggio moderato per mantenere il canale sicuro."); }
    catch (err) { toast.error(errMsg(err)); }
  };

  const del = async (id) => {
    try { await api.delete(`/chat/messages/${id}`); setMsgs((m) => m.filter((x) => x.id !== id)); toast.success("Messaggio rimosso"); }
    catch (err) { toast.error(errMsg(err)); }
  };

  const toggleSel = (id) => setSelected((s) => { const n = new Set(s); n.has(id) ? n.delete(id) : n.add(id); return n; });

  const bulkDelete = async () => {
    const ids = [...selected];
    if (ids.length === 0) return;
    try {
      await api.post("/chat/messages/delete", { ids });
      setMsgs((m) => m.filter((x) => !selected.has(x.id)));
      setSelected(new Set()); setSelMode(false);
      toast.success(`${ids.length} messaggi eliminati`);
    } catch (err) { toast.error(errMsg(err)); }
  };

  return (
    <div className="max-w-3xl mx-auto space-y-6">
      <div className="flex items-end justify-between gap-3 flex-wrap">
        <div>
          <p className="text-xs tracking-[0.25em] uppercase font-bold text-muted-foreground">Community</p>
          <h1 className="font-head text-4xl font-black tracking-tight mt-1">Canale Pubblico</h1>
          <p className="text-muted-foreground mt-2 flex items-center gap-1.5 text-sm">
            <ShieldCheck size={15} className="text-primary" /> Censura automatica attiva: un posto sicuro per tutti.
          </p>
        </div>
        {isAdmin && (
          <div className="flex gap-2">
            {selMode && (
              <Button variant="destructive" size="sm" onClick={bulkDelete} disabled={selected.size === 0} data-testid="bulk-delete-btn" className="rounded-full gap-1.5">
                <Trash2 size={15} /> Elimina ({selected.size})
              </Button>
            )}
            <Button variant={selMode ? "secondary" : "outline"} size="sm" data-testid="select-mode-btn"
              onClick={() => { setSelMode((s) => !s); setSelected(new Set()); }} className="rounded-full gap-1.5">
              <CheckSquare size={15} /> {selMode ? "Annulla" : "Seleziona"}
            </Button>
          </div>
        )}
      </div>

      <Card className="border-border overflow-hidden">
        <div className="h-[480px] overflow-y-auto p-4 space-y-3 bg-secondary/20">
          {msgs.length === 0 && <p className="text-center text-muted-foreground text-sm py-20">Nessun messaggio. Scrivi il primo!</p>}
          {msgs.map((m) => {
            const mine = m.user_id === user?.id;
            const sel = selected.has(m.id);
            return (
              <div key={m.id} onClick={() => selMode && toggleSel(m.id)}
                className={`flex gap-2.5 ${mine ? "flex-row-reverse" : ""} ${selMode ? "cursor-pointer rounded-xl -mx-1 px-1 py-1 transition-colors " + (sel ? "bg-primary/10" : "hover:bg-secondary/60") : ""}`}
                data-testid="chat-message">
                {selMode && <div className={`w-5 h-5 rounded-md border-2 shrink-0 self-center grid place-items-center ${sel ? "bg-primary border-primary" : "border-muted-foreground/40"}`} data-testid={`select-msg-${m.id}`}>{sel && <CheckSquare size={12} className="text-white" />}</div>}
                <div className="w-8 h-8 rounded-full grid place-items-center text-white text-xs font-bold shrink-0" style={{ background: m.avatar_color }}>
                  {m.user_name?.[0]?.toUpperCase()}
                </div>
                <div className={`max-w-[75%] ${mine ? "items-end text-right" : ""} flex flex-col`}>
                  <span className="text-xs text-muted-foreground px-1">{mine ? "Tu" : m.user_name}</span>
                  <div className="group flex items-center gap-1.5">
                    <div className={`px-4 py-2 rounded-2xl text-sm mt-0.5 ${mine ? "bg-primary text-primary-foreground rounded-br-md" : "bg-card border border-border rounded-bl-md"}`}>
                      {m.text}
                    </div>
                    {isAdmin && !selMode && (
                      <button onClick={(ev) => { ev.stopPropagation(); del(m.id); }} data-testid={`delete-msg-${m.id}`}
                        className="opacity-0 group-hover:opacity-100 transition-opacity text-muted-foreground hover:text-destructive">
                        <Trash2 size={14} />
                      </button>
                    )}
                  </div>
                </div>
              </div>
            );
          })}
          <div ref={endRef} />
        </div>
        <form onSubmit={send} className="p-4 border-t border-border flex gap-2">
          <Input value={text} onChange={(e) => setText(e.target.value)} data-testid="chat-input"
            placeholder={online ? "Scrivi nel canale…" : "Non disponibile offline"} disabled={!online} maxLength={500} className="rounded-full" />
          <Button type="submit" size="icon" data-testid="chat-send-btn" disabled={!online} className="rounded-full shrink-0"><Send size={16} /></Button>
        </form>
      </Card>
    </div>
  );
}
