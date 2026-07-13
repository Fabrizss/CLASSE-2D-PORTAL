import { useEffect, useRef, useState } from "react";
import { Send, ShieldCheck } from "lucide-react";
import { api, errMsg } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { toast } from "sonner";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

export default function Chat() {
  const { user } = useAuth();
  const [msgs, setMsgs] = useState([]);
  const [text, setText] = useState("");
  const endRef = useRef();

  const load = () => api.get("/chat/messages").then((r) => setMsgs(r.data)).catch(() => {});
  useEffect(() => { load(); const iv = setInterval(load, 3000); return () => clearInterval(iv); }, []);
  useEffect(() => { endRef.current?.scrollIntoView({ behavior: "smooth" }); }, [msgs]);

  const send = async (e) => {
    e.preventDefault();
    const t = text.trim();
    if (!t) return;
    setText("");
    try { const { data } = await api.post("/chat/messages", { text: t }); setMsgs((m) => [...m, data]); if (data.censored) toast.info("Messaggio moderato per mantenere il canale sicuro."); }
    catch (err) { toast.error(errMsg(err)); }
  };

  return (
    <div className="max-w-3xl mx-auto space-y-6">
      <div>
        <p className="text-xs tracking-[0.25em] uppercase font-bold text-muted-foreground">Community</p>
        <h1 className="font-head text-4xl font-black tracking-tight mt-1">Canale Pubblico</h1>
        <p className="text-muted-foreground mt-2 flex items-center gap-1.5 text-sm">
          <ShieldCheck size={15} className="text-primary" /> Censura automatica attiva: un posto sicuro per tutti.
        </p>
      </div>

      <Card className="border-border overflow-hidden">
        <div className="h-[480px] overflow-y-auto p-4 space-y-3 bg-secondary/20">
          {msgs.length === 0 && <p className="text-center text-muted-foreground text-sm py-20">Nessun messaggio. Scrivi il primo!</p>}
          {msgs.map((m) => {
            const mine = m.user_id === user?.id;
            return (
              <div key={m.id} className={`flex gap-2.5 ${mine ? "flex-row-reverse" : ""}`} data-testid="chat-message">
                <div className="w-8 h-8 rounded-full grid place-items-center text-white text-xs font-bold shrink-0" style={{ background: m.avatar_color }}>
                  {m.user_name?.[0]?.toUpperCase()}
                </div>
                <div className={`max-w-[75%] ${mine ? "items-end text-right" : ""} flex flex-col`}>
                  <span className="text-xs text-muted-foreground px-1">{mine ? "Tu" : m.user_name}</span>
                  <div className={`px-4 py-2 rounded-2xl text-sm mt-0.5 ${mine ? "bg-primary text-primary-foreground rounded-br-md" : "bg-card border border-border rounded-bl-md"}`}>
                    {m.text}
                  </div>
                </div>
              </div>
            );
          })}
          <div ref={endRef} />
        </div>
        <form onSubmit={send} className="p-4 border-t border-border flex gap-2">
          <Input value={text} onChange={(e) => setText(e.target.value)} data-testid="chat-input"
            placeholder="Scrivi nel canale…" maxLength={500} className="rounded-full" />
          <Button type="submit" size="icon" data-testid="chat-send-btn" className="rounded-full shrink-0"><Send size={16} /></Button>
        </form>
      </Card>
    </div>
  );
}
