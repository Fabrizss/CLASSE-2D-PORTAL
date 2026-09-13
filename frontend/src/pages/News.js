import { useEffect, useRef, useState } from "react";
import { motion } from "framer-motion";
import { toast } from "sonner";
import { Plus, Paperclip, Trash2, Newspaper, Loader2, Download, X } from "lucide-react";
import { api, errMsg, API, requireOnline } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { isStaff } from "@/lib/roles";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogTrigger, DialogFooter } from "@/components/ui/dialog";

export default function News() {
  const { user } = useAuth();
  const isAdmin = isStaff(user?.role);
  const [news, setNews] = useState([]);
  const [open, setOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const [form, setForm] = useState({ title: "", body: "" });
  const [attachments, setAttachments] = useState([]);
  const [uploading, setUploading] = useState(false);
  const fileRef = useRef();
  const token = localStorage.getItem("noi_token");

  const load = () => api.get("/news").then((r) => setNews(r.data)).catch(() => {});
  useEffect(() => { load(); }, []);

  const addFile = async (e) => {
    const f = e.target.files?.[0];
    if (!f) return;
    try { requireOnline(); } catch (err) { return toast.error(err.message); }
    setUploading(true);
    const fd = new FormData();
    fd.append("file", f);
    try {
      const { data } = await api.post("/news/upload", fd, { headers: { "Content-Type": "multipart/form-data" } });
      setAttachments((a) => [...a, data]);
    } catch (err) { toast.error(errMsg(err)); }
    finally { setUploading(false); if (fileRef.current) fileRef.current.value = ""; }
  };

  const create = async (e) => {
    e.preventDefault();
    try { requireOnline(); } catch (err) { return toast.error(err.message); }
    setSaving(true);
    try {
      await api.post("/news", { ...form, attachments });
      toast.success("News pubblicata!");
      setOpen(false); setForm({ title: "", body: "" }); setAttachments([]);
      load();
    } catch (err) { toast.error(errMsg(err)); }
    finally { setSaving(false); }
  };

  const remove = async (id) => {
    try { await api.delete(`/news/${id}`); setNews((n) => n.filter((x) => x.id !== id)); toast.success("Eliminata"); }
    catch (err) { toast.error(errMsg(err)); }
  };

  return (
    <div className="space-y-8">
      <div className="flex items-end justify-between gap-4 flex-wrap">
        <div>
          <p className="text-xs tracking-[0.25em] uppercase font-bold text-muted-foreground flex items-center gap-1.5"><Newspaper size={14} /> Bacheca</p>
          <h1 className="font-head text-4xl font-black tracking-tight mt-1">News della 2D</h1>
        </div>
        {isAdmin && (
          <Dialog open={open} onOpenChange={setOpen}>
            <DialogTrigger asChild>
              <Button data-testid="new-news-btn" className="rounded-full gap-2 active:scale-95 transition-transform"><Plus size={18} /> Pubblica news</Button>
            </DialogTrigger>
            <DialogContent className="max-w-md">
              <DialogHeader>
                <DialogTitle className="font-head">Nuova news</DialogTitle>
                <DialogDescription>Verrà notificata a tutti i membri.</DialogDescription>
              </DialogHeader>
              <form onSubmit={create} className="space-y-4">
                <div><Label>Titolo</Label><Input required value={form.title} data-testid="news-title-input"
                  onChange={(e) => setForm({ ...form, title: e.target.value })} className="mt-1.5" placeholder="Gita a Roma confermata!" /></div>
                <div><Label>Testo</Label><Textarea required value={form.body} data-testid="news-body-input"
                  onChange={(e) => setForm({ ...form, body: e.target.value })} className="mt-1.5 min-h-28" placeholder="Scrivi la news…" /></div>
                <div>
                  <input ref={fileRef} type="file" onChange={addFile} className="hidden" data-testid="news-file-input" />
                  <Button type="button" variant="outline" onClick={() => fileRef.current?.click()} disabled={uploading} className="rounded-full gap-2" data-testid="news-attach-btn">
                    {uploading ? <Loader2 size={15} className="animate-spin" /> : <Paperclip size={15} />} Allega file
                  </Button>
                  <div className="flex flex-wrap gap-2 mt-2">
                    {attachments.map((a, i) => (
                      <span key={i} className="text-xs bg-secondary rounded-full pl-3 pr-1.5 py-1 flex items-center gap-1">
                        {a.filename}
                        <button type="button" onClick={() => setAttachments((x) => x.filter((_, j) => j !== i))} className="hover:text-destructive"><X size={13} /></button>
                      </span>
                    ))}
                  </div>
                </div>
                <DialogFooter><Button type="submit" disabled={saving} data-testid="submit-news-btn" className="rounded-full w-full">{saving ? "Pubblico…" : "Pubblica"}</Button></DialogFooter>
              </form>
            </DialogContent>
          </Dialog>
        )}
      </div>

      {news.length === 0 && <p className="text-muted-foreground text-center py-16">Nessuna news al momento.</p>}
      <div className="space-y-5">
        {news.map((n, i) => (
          <motion.div key={n.id} initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.05 }}>
            <Card className="p-6 border-border">
              <div className="flex items-start justify-between gap-3">
                <h3 className="font-head text-2xl font-bold tracking-tight">{n.title}</h3>
                {isAdmin && <button onClick={() => remove(n.id)} data-testid={`delete-news-${n.id}`} className="text-muted-foreground hover:text-destructive"><Trash2 size={17} /></button>}
              </div>
              <p className="text-muted-foreground text-xs mt-1">di {n.author_name} · {new Date(n.created_at).toLocaleDateString("it-IT")}</p>
              <p className="mt-3 whitespace-pre-wrap leading-relaxed">{n.body}</p>
              {n.attachments?.length > 0 && (
                <div className="flex flex-wrap gap-2 mt-4">
                  {n.attachments.map((a, j) => (
                    <a key={j} href={`${API}/news/file/${a.path}?auth=${token}`} target="_blank" rel="noreferrer"
                      data-testid={`news-attachment-${n.id}-${j}`}
                      className="text-sm bg-primary/10 text-primary rounded-full px-3.5 py-1.5 flex items-center gap-1.5 hover:bg-primary/20 transition-colors">
                      <Download size={14} /> {a.filename}
                    </a>
                  ))}
                </div>
              )}
            </Card>
          </motion.div>
        ))}
      </div>
    </div>
  );
}
