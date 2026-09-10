import { useEffect, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { toast } from "sonner";
import { ArrowLeft, Crown, Trophy, Vote, MessagesSquare, Plus, X, Send, Trash2 } from "lucide-react";
import { api, errMsg, requireOnline } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogTrigger, DialogFooter } from "@/components/ui/dialog";
import { Select, SelectTrigger, SelectValue, SelectContent, SelectItem } from "@/components/ui/select";
import { Label } from "@/components/ui/label";

export default function CoursePanel() {
  const { id } = useParams();
  const { user } = useAuth();
  const [data, setData] = useState(null);
  const [newTeam, setNewTeam] = useState({ name: "", sport_type: "generico" });
  const [teamDialog, setTeamDialog] = useState(false);
  const [pollDialog, setPollDialog] = useState(false);
  const [newPoll, setNewPoll] = useState({ question: "", options: "" });
  const [msgs, setMsgs] = useState([]);
  const [text, setText] = useState("");
  const endRef = useRef();

  const load = () => api.get(`/events/${id}/course`).then((r) => setData(r.data)).catch((e) => toast.error(errMsg(e)));
  const loadChat = () => api.get(`/events/${id}/course/chat`).then((r) => setMsgs(r.data)).catch(() => {});

  useEffect(() => {
    load(); loadChat();
    const iv = setInterval(loadChat, 3000);
    return () => clearInterval(iv);
  }, [id]);
  useEffect(() => { endRef.current?.scrollIntoView({ behavior: "smooth" }); }, [msgs]);

  const act = async (fn, ok) => { try { await fn(); toast.success(ok); load(); } catch (e) { toast.error(errMsg(e)); } };

  const setRep = (userId) => act(() => api.post(`/events/${id}/course/rep`, { user_id: userId }), "Rappresentante assegnato");
  const removeRep = () => act(() => api.delete(`/events/${id}/course/rep`), "Rappresentante rimosso");

  const createTeam = async () => {
    if (!newTeam.name.trim()) return toast.error("Scegli un nome per la squadra");
    try {
      await api.post(`/events/${id}/course/teams`, newTeam);
      toast.success("Squadra creata"); setTeamDialog(false); setNewTeam({ name: "", sport_type: "generico" }); load();
    } catch (e) { toast.error(errMsg(e)); }
  };
  const deleteTeam = (tid) => act(() => api.delete(`/events/${id}/course/teams/${tid}`), "Squadra eliminata");
  const addMember = (tid, userId) => act(() => api.post(`/events/${id}/course/teams/${tid}/members`, { user_id: userId }), "Giocatore aggiunto");
  const removeMember = (tid, uid) => act(() => api.delete(`/events/${id}/course/teams/${tid}/members/${uid}`), "Giocatore rimosso");

  const createPoll = async () => {
    const options = newPoll.options.split(",").map((s) => s.trim()).filter(Boolean);
    if (!newPoll.question.trim() || options.length < 2) return toast.error("Domanda e almeno 2 opzioni richieste");
    try {
      await api.post(`/events/${id}/course/polls`, { question: newPoll.question, options });
      toast.success("Sondaggio creato"); setPollDialog(false); setNewPoll({ question: "", options: "" }); load();
    } catch (e) { toast.error(errMsg(e)); }
  };
  const vote = (pid, option) => act(() => api.post(`/events/${id}/course/polls/${pid}/vote`, { option }), "Voto registrato");
  const deletePoll = (pid) => act(() => api.delete(`/events/${id}/course/polls/${pid}`), "Sondaggio eliminato");

  const send = async (e) => {
    e.preventDefault();
    const t = text.trim();
    if (!t) return;
    try { requireOnline(); } catch (err) { return toast.error(err.message); }
    setText("");
    try { const { data: m } = await api.post(`/events/${id}/course/chat`, { text: t }); setMsgs((ms) => [...ms, m]); }
    catch (err) { toast.error(errMsg(err)); }
  };

  if (!data) return <p className="text-center text-muted-foreground py-16">Caricamento pannello corso…</p>;

  const availableFor = (team) => data.participants.filter((p) => !team.members.some((m) => m.user_id === p.user_id));

  return (
    <div className="max-w-4xl mx-auto space-y-6" data-testid="course-panel-page">
      <div>
        <Link to="/events" data-testid="back-to-events" className="text-sm text-muted-foreground hover:text-primary flex items-center gap-1.5 mb-2">
          <ArrowLeft size={14} /> Torna alle iscrizioni
        </Link>
        <p className="text-xs tracking-[0.25em] uppercase font-bold text-muted-foreground">Pannello Corso</p>
        <h1 className="font-head text-3xl sm:text-4xl font-black tracking-tight mt-1">{data.event_title}</h1>
      </div>

      <Tabs defaultValue="rep">
        <TabsList className="flex-wrap">
          <TabsTrigger value="rep" data-testid="tab-rep" className="gap-1.5"><Crown size={15} /> Rappresentante</TabsTrigger>
          <TabsTrigger value="teams" data-testid="tab-teams" className="gap-1.5"><Trophy size={15} /> Squadre</TabsTrigger>
          <TabsTrigger value="polls" data-testid="tab-polls" className="gap-1.5"><Vote size={15} /> Sondaggi</TabsTrigger>
          <TabsTrigger value="chat" data-testid="tab-course-chat" className="gap-1.5"><MessagesSquare size={15} /> Chat</TabsTrigger>
        </TabsList>

        <TabsContent value="rep" className="mt-6">
          <Card className="p-6 border-border">
            {data.rep ? (
              <div className="flex items-center gap-3" data-testid="course-rep-info">
                <div className="w-11 h-11 rounded-full grid place-items-center text-white font-bold bg-primary shrink-0">
                  {data.rep.name?.[0]?.toUpperCase()}
                </div>
                <div className="flex-1">
                  <p className="font-semibold">{data.rep.name}</p>
                  <p className="text-xs text-muted-foreground">Rappresentante / capitano del corso</p>
                </div>
                {data.can_manage && (
                  <Button variant="ghost" size="sm" onClick={removeRep} data-testid="remove-rep-btn" className="text-destructive rounded-full">Rimuovi</Button>
                )}
              </div>
            ) : (
              <p className="text-muted-foreground text-sm" data-testid="no-rep-msg">Nessun rappresentante assegnato per questo corso.</p>
            )}
            {data.can_manage && (
              <div className="mt-4 flex gap-2 flex-wrap">
                <Select onValueChange={setRep}>
                  <SelectTrigger className="max-w-xs" data-testid="rep-select"><SelectValue placeholder="Assegna rappresentante…" /></SelectTrigger>
                  <SelectContent>
                    {data.participants.map((p) => <SelectItem key={p.user_id} value={p.user_id}>{p.name}</SelectItem>)}
                  </SelectContent>
                </Select>
              </div>
            )}
          </Card>
        </TabsContent>

        <TabsContent value="teams" className="mt-6 space-y-4">
          {data.can_manage && (
            <Dialog open={teamDialog} onOpenChange={setTeamDialog}>
              <DialogTrigger asChild>
                <Button data-testid="new-team-btn" className="rounded-full gap-2"><Plus size={16} /> Nuova squadra</Button>
              </DialogTrigger>
              <DialogContent className="max-w-sm">
                <DialogHeader><DialogTitle className="font-head">Nuova squadra</DialogTitle>
                  <DialogDescription>Crea una formazione per questo corso.</DialogDescription></DialogHeader>
                <div className="space-y-3">
                  <div><Label>Nome squadra</Label>
                    <Input value={newTeam.name} data-testid="team-name-input" onChange={(e) => setNewTeam({ ...newTeam, name: e.target.value })} className="mt-1.5" placeholder="Squadra A" /></div>
                  <div><Label>Sport / formato</Label>
                    <Select value={newTeam.sport_type} onValueChange={(v) => setNewTeam({ ...newTeam, sport_type: v })}>
                      <SelectTrigger className="mt-1.5" data-testid="team-sport-select"><SelectValue /></SelectTrigger>
                      <SelectContent>
                        {Object.entries(data.sport_types).map(([k, v]) => <SelectItem key={k} value={k}>{v.label}{v.max ? ` (max ${v.max})` : ""}</SelectItem>)}
                      </SelectContent>
                    </Select>
                  </div>
                </div>
                <DialogFooter><Button onClick={createTeam} data-testid="create-team-submit" className="rounded-full w-full">Crea squadra</Button></DialogFooter>
              </DialogContent>
            </Dialog>
          )}
          {data.teams.length === 0 && <p className="text-muted-foreground text-center py-10 text-sm">Nessuna squadra creata ancora.</p>}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            {data.teams.map((t) => {
              const sport = data.sport_types[t.sport_type];
              return (
                <Card key={t.id} className="p-5 border-border" data-testid={`team-card-${t.id}`}>
                  <div className="flex items-start justify-between gap-2">
                    <div>
                      <h3 className="font-head font-semibold">{t.name}</h3>
                      <Badge variant="outline" className="rounded-full mt-1">{sport?.label} · {t.members.length}{sport?.max ? `/${sport.max}` : ""}</Badge>
                    </div>
                    {data.can_manage && (
                      <button onClick={() => deleteTeam(t.id)} data-testid={`delete-team-${t.id}`} className="text-muted-foreground hover:text-destructive"><Trash2 size={15} /></button>
                    )}
                  </div>
                  <div className="mt-3 space-y-1.5">
                    {t.members.length === 0 && <p className="text-xs text-muted-foreground">Nessun giocatore inserito.</p>}
                    {t.members.map((m) => (
                      <div key={m.user_id} className="flex items-center justify-between text-sm px-2.5 py-1.5 rounded-lg bg-secondary/50" data-testid={`team-member-${t.id}-${m.user_id}`}>
                        <span>{m.name}</span>
                        {data.can_manage && <button onClick={() => removeMember(t.id, m.user_id)}><X size={13} className="text-muted-foreground hover:text-destructive" /></button>}
                      </div>
                    ))}
                  </div>
                  {data.can_manage && (!sport?.max || t.members.length < sport.max) && availableFor(t).length > 0 && (
                    <Select onValueChange={(v) => addMember(t.id, v)}>
                      <SelectTrigger className="mt-3" data-testid={`add-member-select-${t.id}`}><SelectValue placeholder="+ Aggiungi giocatore" /></SelectTrigger>
                      <SelectContent>
                        {availableFor(t).map((p) => <SelectItem key={p.user_id} value={p.user_id}>{p.name}</SelectItem>)}
                      </SelectContent>
                    </Select>
                  )}
                </Card>
              );
            })}
          </div>
        </TabsContent>

        <TabsContent value="polls" className="mt-6 space-y-4">
          {data.can_manage && (
            <Dialog open={pollDialog} onOpenChange={setPollDialog}>
              <DialogTrigger asChild>
                <Button data-testid="new-poll-btn" className="rounded-full gap-2"><Plus size={16} /> Nuovo sondaggio</Button>
              </DialogTrigger>
              <DialogContent className="max-w-sm">
                <DialogHeader><DialogTitle className="font-head">Nuovo sondaggio</DialogTitle>
                  <DialogDescription>I partecipanti al corso potranno votare.</DialogDescription></DialogHeader>
                <div className="space-y-3">
                  <div><Label>Domanda</Label>
                    <Input value={newPoll.question} data-testid="poll-question-input" onChange={(e) => setNewPoll({ ...newPoll, question: e.target.value })} className="mt-1.5" placeholder="Chi sarà il portiere?" /></div>
                  <div><Label>Opzioni</Label>
                    <Input value={newPoll.options} data-testid="poll-options-input" onChange={(e) => setNewPoll({ ...newPoll, options: e.target.value })} className="mt-1.5" placeholder="separa con virgola" /></div>
                </div>
                <DialogFooter><Button onClick={createPoll} data-testid="create-poll-submit" className="rounded-full w-full">Crea sondaggio</Button></DialogFooter>
              </DialogContent>
            </Dialog>
          )}
          {data.polls.length === 0 && <p className="text-muted-foreground text-center py-10 text-sm">Nessun sondaggio ancora.</p>}
          {data.polls.map((p) => (
            <Card key={p.id} className="p-5 border-border" data-testid={`poll-card-${p.id}`}>
              <div className="flex items-start justify-between gap-2">
                <h3 className="font-head font-semibold">{p.question}</h3>
                {data.can_manage && <button onClick={() => deletePoll(p.id)} data-testid={`delete-poll-${p.id}`} className="text-muted-foreground hover:text-destructive"><Trash2 size={15} /></button>}
              </div>
              <div className="mt-3 space-y-2">
                {p.options.map((opt) => {
                  const cnt = p.vote_counts[opt] || 0;
                  const pct = p.total_votes ? Math.round((cnt / p.total_votes) * 100) : 0;
                  const mine = p.my_vote === opt;
                  return (
                    <button key={opt} onClick={() => vote(p.id, opt)} data-testid={`vote-${p.id}-${opt}`}
                      className={`w-full text-left relative overflow-hidden rounded-xl border px-3.5 py-2 text-sm transition-colors ${mine ? "border-primary bg-primary/10" : "border-border hover:bg-secondary/50"}`}>
                      <div className="absolute inset-y-0 left-0 bg-primary/10" style={{ width: `${pct}%` }} />
                      <span className="relative z-10 flex justify-between font-medium">{opt} {mine && "✓"} <span className="text-muted-foreground">{cnt} · {pct}%</span></span>
                    </button>
                  );
                })}
              </div>
            </Card>
          ))}
        </TabsContent>

        <TabsContent value="chat" className="mt-6">
          <Card className="border-border overflow-hidden">
            <div className="h-[420px] overflow-y-auto p-4 space-y-3 bg-secondary/20">
              {msgs.length === 0 && <p className="text-center text-muted-foreground text-sm py-16">Nessun messaggio nella chat del corso. Scrivi il primo!</p>}
              {msgs.map((m) => {
                const mine = m.user_id === user?.id;
                return (
                  <div key={m.id} className={`flex gap-2.5 ${mine ? "flex-row-reverse" : ""}`} data-testid="course-chat-message">
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
              <Input value={text} onChange={(e) => setText(e.target.value)} data-testid="course-chat-input" placeholder="Scrivi nella chat del corso…" maxLength={500} className="rounded-full" />
              <Button type="submit" size="icon" data-testid="course-chat-send-btn" className="rounded-full shrink-0"><Send size={16} /></Button>
            </form>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  );
}
