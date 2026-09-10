import { useState, useRef, useEffect } from "react";
import { motion } from "framer-motion";
import { toast } from "sonner";
import { Upload, Send, Sparkles, RotateCw, GraduationCap, Layers, Loader2, Save, Trash2, ClipboardList } from "lucide-react";
import { api, errMsg } from "@/lib/api";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { Select, SelectTrigger, SelectValue, SelectContent, SelectItem } from "@/components/ui/select";

const BANNER = "https://images.unsplash.com/photo-1501504905252-473c47e087f8?crop=entropy&cs=srgb&fm=jpg&q=85&w=1600";

export default function Study() {
  const [file, setFile] = useState(null);
  const [uploading, setUploading] = useState(false);
  const fileRef = useRef();

  // interrogazione
  const [subject, setSubject] = useState("");
  const [sessionId] = useState(() => Math.random().toString(36).slice(2));
  const [msgs, setMsgs] = useState([]);
  const [input, setInput] = useState("");
  const [thinking, setThinking] = useState(false);

  // flashcards
  const [topic, setTopic] = useState("");
  const [cards, setCards] = useState([]);
  const [genLoading, setGenLoading] = useState(false);
  const [flipped, setFlipped] = useState({});

  // registro interrogazioni
  const [regs, setRegs] = useState([]);
  const [regForm, setRegForm] = useState({ tipo: "orale", num_domande: "", voto: "" });
  const loadRegs = () => api.get("/interrogazioni").then((r) => setRegs(r.data)).catch(() => {});
  useEffect(() => { loadRegs(); }, []);

  const saveReg = async () => {
    try {
      await api.post("/interrogazioni", {
        subject: subject || null, tipo: regForm.tipo,
        num_domande: parseInt(regForm.num_domande || 0, 10),
        voto: regForm.voto === "" ? null : parseFloat(regForm.voto),
      });
      toast.success("Interrogazione salvata");
      setRegForm({ tipo: "orale", num_domande: "", voto: "" });
      loadRegs();
    } catch (e) { toast.error(errMsg(e)); }
  };
  const setVoto = async (id, voto) => {
    setRegs((rs) => rs.map((r) => r.id === id ? { ...r, voto } : r));
    try { await api.patch(`/interrogazioni/${id}`, { voto: voto === "" ? null : parseFloat(voto) }); } catch (e) { toast.error(errMsg(e)); }
  };
  const delReg = async (id) => {
    try { await api.delete(`/interrogazioni/${id}`); setRegs((rs) => rs.filter((r) => r.id !== id)); } catch (e) { toast.error(errMsg(e)); }
  };

  const upload = async (e) => {
    const f = e.target.files?.[0];
    if (!f) return;
    setUploading(true);
    const fd = new FormData();
    fd.append("file", f);
    try {
      const { data } = await api.post("/study/upload", fd, { headers: { "Content-Type": "multipart/form-data" } });
      setFile(data);
      toast.success(`Caricato: ${data.filename}`);
    } catch (err) { toast.error(errMsg(err)); }
    finally { setUploading(false); }
  };

  const sendMsg = async (e) => {
    e.preventDefault();
    const text = input.trim();
    if (!text) return;
    setMsgs((m) => [...m, { role: "user", text }]);
    setInput("");
    setThinking(true);
    try {
      const { data } = await api.post("/study/chat", { session_id: sessionId, message: text, subject: subject || file?.filename });
      setMsgs((m) => [...m, { role: "ai", text: data.reply }]);
    } catch (err) { toast.error(errMsg(err)); }
    finally { setThinking(false); }
  };

  const startQuiz = async () => {
    setMsgs([]);
    setThinking(true);
    try {
      const { data } = await api.post("/study/chat", {
        session_id: sessionId,
        message: `Iniziamo l'interrogazione${subject ? " su " + subject : ""}. Fammi la prima domanda.`,
        subject: subject || file?.filename,
      });
      setMsgs([{ role: "ai", text: data.reply }]);
    } catch (err) { toast.error(errMsg(err)); }
    finally { setThinking(false); }
  };

  const genCards = async () => {
    if (!topic && !file) return toast.error("Scrivi un argomento o carica un file");
    setGenLoading(true);
    setFlipped({});
    try {
      const { data } = await api.post("/study/flashcards", { topic: topic || null, file_id: file?.file_id || null, count: 8 });
      setCards(data.cards);
      toast.success(`${data.cards.length} flashcard generate!`);
    } catch (err) { toast.error(errMsg(err)); }
    finally { setGenLoading(false); }
  };

  return (
    <div className="space-y-8">
      <div className="relative rounded-3xl overflow-hidden h-60 sm:h-72">
        <img src={BANNER} alt="Scrivania di studio con libro aperto e laptop" className="w-full h-full object-cover" />
        <div className="absolute inset-0 bg-gradient-to-tr from-primary/80 via-primary/40 to-transparent" />
        <div className="absolute inset-0 bg-gradient-to-t from-black/70 to-transparent" />
        <div className="absolute inset-0 p-6 sm:p-10 flex flex-col justify-end text-white">
          <p className="text-xs tracking-[0.25em] uppercase font-bold opacity-90 flex items-center gap-1.5"><Sparkles size={14} /> Il tuo tutor personale · Gemini AI</p>
          <h1 className="font-head text-4xl sm:text-5xl font-black tracking-tight mt-1">Aiuto Studio</h1>
          <p className="text-white/85 mt-2 max-w-lg text-sm sm:text-base">Fatti interrogare come in classe, trasforma i tuoi appunti in flashcard e arriva preparato a ogni verifica.</p>
        </div>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        {[
          { icon: GraduationCap, t: "Interrogazione AI", d: "Domande una alla volta, con voto e feedback." },
          { icon: Layers, t: "Flashcard smart", d: "Generate dai tuoi file o da un argomento." },
          { icon: Upload, t: "Carica appunti", d: "PDF o testo: l'AI studia con te." },
        ].map((f, i) => (
          <Card key={i} className="p-5 flex items-start gap-3 hover:-translate-y-1 transition-all">
            <div className="w-10 h-10 rounded-xl bg-primary/10 text-primary grid place-items-center shrink-0"><f.icon size={20} /></div>
            <div><h3 className="font-head font-semibold">{f.t}</h3><p className="text-xs text-muted-foreground mt-0.5">{f.d}</p></div>
          </Card>
        ))}
      </div>

      <Card className="p-4 border-border flex flex-col sm:flex-row items-center gap-3">
        <input ref={fileRef} type="file" accept=".pdf,.txt,.md,.csv" onChange={upload} className="hidden" data-testid="file-input" />
        <Button variant="outline" onClick={() => fileRef.current?.click()} disabled={uploading} data-testid="upload-btn" className="rounded-full gap-2">
          {uploading ? <Loader2 size={16} className="animate-spin" /> : <Upload size={16} />} Carica materiale
        </Button>
        <p className="text-sm text-muted-foreground">{file ? `📄 ${file.filename} (${file.chars} caratteri)`.replace("📄 ", "") : "PDF o testo: l'AI lo userà per quiz e flashcard."}</p>
      </Card>

      <Tabs defaultValue="quiz">
        <TabsList className="grid grid-cols-2 w-full max-w-md">
          <TabsTrigger value="quiz" data-testid="tab-quiz" className="gap-2"><GraduationCap size={16} /> Interrogami</TabsTrigger>
          <TabsTrigger value="cards" data-testid="tab-cards" className="gap-2"><Layers size={16} /> Flashcard</TabsTrigger>
        </TabsList>

        <TabsContent value="quiz" className="mt-6">
          <Card className="border-border overflow-hidden">
            <div className="p-4 border-b border-border flex flex-col sm:flex-row gap-3">
              <Input value={subject} onChange={(e) => setSubject(e.target.value)} data-testid="subject-input"
                placeholder="Argomento (es. Rivoluzione Francese)" className="rounded-full" />
              <Button onClick={startQuiz} disabled={thinking} data-testid="start-quiz-btn" className="rounded-full gap-2 whitespace-nowrap">
                <Sparkles size={16} /> Inizia interrogazione
              </Button>
            </div>
            <div className="p-4 h-[380px] overflow-y-auto space-y-3 bg-secondary/30">
              {msgs.length === 0 && <p className="text-center text-muted-foreground text-sm py-16">Il professore AI ti interrogherà qui.</p>}
              {msgs.map((m, i) => (
                <div key={i} className={`flex ${m.role === "user" ? "justify-end" : "justify-start"}`}>
                  <div className={`max-w-[80%] px-4 py-2.5 rounded-2xl text-sm whitespace-pre-wrap ${
                    m.role === "user" ? "bg-primary text-primary-foreground rounded-br-md" : "bg-card border border-border rounded-bl-md"}`}>
                    {m.text}
                  </div>
                </div>
              ))}
              {thinking && <div className="flex justify-start"><div className="bg-card border border-border px-4 py-2.5 rounded-2xl"><Loader2 size={16} className="animate-spin text-primary" /></div></div>}
            </div>
            <form onSubmit={sendMsg} className="p-4 border-t border-border flex gap-2">
              <Input value={input} onChange={(e) => setInput(e.target.value)} data-testid="quiz-input"
                placeholder="Scrivi la tua risposta…" className="rounded-full" />
              <Button type="submit" disabled={thinking} data-testid="quiz-send-btn" size="icon" className="rounded-full shrink-0"><Send size={16} /></Button>
            </form>
          </Card>

          <Card className="p-5 sm:p-6 border-border mt-6">
            <div className="flex items-center gap-2 mb-1">
              <ClipboardList size={18} className="text-primary" />
              <h3 className="font-head text-xl font-semibold">Registro interrogazioni</h3>
            </div>
            <p className="text-muted-foreground text-sm mb-4">Salva le tue interrogazioni e aggiungi il voto quando lo ricevi.</p>
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 items-end">
              <div>
                <label className="text-xs font-semibold text-muted-foreground">Tipo</label>
                <Select value={regForm.tipo} onValueChange={(v) => setRegForm({ ...regForm, tipo: v })}>
                  <SelectTrigger className="mt-1" data-testid="reg-tipo-select"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="orale">Orale</SelectItem>
                    <SelectItem value="scritta">Scritta</SelectItem>
                    <SelectItem value="pratica">Pratica</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div>
                <label className="text-xs font-semibold text-muted-foreground">N. domande</label>
                <Input type="number" min="0" value={regForm.num_domande} data-testid="reg-num-input"
                  onChange={(e) => setRegForm({ ...regForm, num_domande: e.target.value })} className="mt-1" placeholder="0" />
              </div>
              <div>
                <label className="text-xs font-semibold text-muted-foreground">Voto (opz.)</label>
                <Input type="number" step="0.25" value={regForm.voto} data-testid="reg-voto-input"
                  onChange={(e) => setRegForm({ ...regForm, voto: e.target.value })} className="mt-1" placeholder="—" />
              </div>
              <Button onClick={saveReg} data-testid="reg-save-btn" className="rounded-full gap-2"><Save size={16} /> Salva</Button>
            </div>
            <div className="mt-5 space-y-2">
              {regs.length === 0 && <p className="text-sm text-muted-foreground text-center py-4">Nessuna interrogazione salvata.</p>}
              {regs.map((r) => (
                <div key={r.id} className="flex items-center gap-3 p-3 rounded-xl border border-border" data-testid={`reg-row-${r.id}`}>
                  <div className="flex-1 min-w-0">
                    <p className="font-medium truncate">{r.subject || "Senza argomento"}</p>
                    <p className="text-xs text-muted-foreground capitalize">{r.tipo} · {r.num_domande} domande · {new Date(r.created_at).toLocaleDateString("it-IT")}</p>
                  </div>
                  <Input type="number" step="0.25" value={r.voto ?? ""} data-testid={`reg-voto-edit-${r.id}`}
                    onChange={(e) => setVoto(r.id, e.target.value)} placeholder="voto" className="w-20 h-9 text-center" />
                  <button onClick={() => delReg(r.id)} data-testid={`reg-del-${r.id}`} className="text-muted-foreground hover:text-destructive"><Trash2 size={16} /></button>
                </div>
              ))}
            </div>
          </Card>
        </TabsContent>

        <TabsContent value="cards" className="mt-6 space-y-6">
          <div className="flex flex-col sm:flex-row gap-3">
            <Input value={topic} onChange={(e) => setTopic(e.target.value)} data-testid="topic-input"
              placeholder={file ? `Usa il file "${file.filename}" o scrivi un argomento` : "Argomento delle flashcard"} className="rounded-full" />
            <Button onClick={genCards} disabled={genLoading} data-testid="gen-cards-btn" className="rounded-full gap-2 whitespace-nowrap">
              {genLoading ? <Loader2 size={16} className="animate-spin" /> : <Sparkles size={16} />} Genera flashcard
            </Button>
          </div>
          {cards.length === 0 && !genLoading && <p className="text-muted-foreground text-center py-12 text-sm">Genera flashcard da un argomento o dal file caricato, poi clicca per girarle.</p>}
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
            {cards.map((c, i) => (
              <motion.button key={i} initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.04 }}
                onClick={() => setFlipped((f) => ({ ...f, [i]: !f[i] }))} data-testid={`flashcard-${i}`}
                className="text-left h-40 relative [transform-style:preserve-3d] transition-transform duration-500"
                style={{ transform: flipped[i] ? "rotateY(180deg)" : "none" }}>
                <Card className="absolute inset-0 p-5 flex flex-col justify-between [backface-visibility:hidden] border-primary/30">
                  <span className="text-xs tracking-widest uppercase font-bold text-primary">Domanda {i + 1}</span>
                  <p className="font-head font-semibold">{c.q}</p>
                  <span className="text-xs text-muted-foreground flex items-center gap-1"><RotateCw size={12} /> gira</span>
                </Card>
                <Card className="absolute inset-0 p-5 flex flex-col justify-between [backface-visibility:hidden] bg-primary text-primary-foreground" style={{ transform: "rotateY(180deg)" }}>
                  <span className="text-xs tracking-widest uppercase font-bold opacity-80">Risposta</span>
                  <p className="text-sm">{c.a}</p>
                </Card>
              </motion.button>
            ))}
          </div>
        </TabsContent>
      </Tabs>
    </div>
  );
}
