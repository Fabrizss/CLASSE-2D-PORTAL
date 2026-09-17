import { useRef, useState } from "react";
import { toast } from "sonner";
import { ImageUp, RotateCcw } from "lucide-react";
import { api, errMsg } from "@/lib/api";
import { useBranding } from "@/context/BrandingContext";
import { LOGO } from "@/App";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";

export function BrandingAdmin() {
  const { logoUrl, refresh } = useBranding();
  const [uploading, setUploading] = useState(false);
  const inputRef = useRef(null);

  const onFile = async (e) => {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!file) return;
    if (file.size > 5 * 1024 * 1024) return toast.error("Immagine troppo grande (max 5MB)");
    const fd = new FormData();
    fd.append("file", file);
    setUploading(true);
    try {
      await api.post("/admin/logo", fd, { headers: { "Content-Type": "multipart/form-data" } });
      await refresh();
      toast.success("Logo aggiornato in tutta l'app");
    } catch (err) {
      toast.error(errMsg(err));
    } finally {
      setUploading(false);
    }
  };

  const reset = async () => {
    setUploading(true);
    try {
      await api.delete("/admin/logo");
      await refresh();
      toast.success("Logo predefinito ripristinato");
    } catch (err) {
      toast.error(errMsg(err));
    } finally {
      setUploading(false);
    }
  };

  return (
    <Card className="p-6 border-border" data-testid="branding-admin-section">
      <h3 className="font-head text-lg font-semibold mb-1">Logo dell'app</h3>
      <p className="text-xs text-muted-foreground mb-4">Carica un'immagine (PNG/JPG/WEBP, max 5MB): sostituisce il logo in tutta l'app, anche nella schermata di accesso.</p>
      <div className="flex items-center gap-4">
        <img src={logoUrl || LOGO} alt="Logo attuale" className="w-16 h-16 rounded-full object-cover ring-1 ring-border" data-testid="branding-logo-preview" />
        <div className="flex gap-2">
          <input ref={inputRef} type="file" accept=".png,.jpg,.jpeg,.webp" className="hidden" onChange={onFile} data-testid="branding-logo-input" />
          <Button onClick={() => inputRef.current?.click()} disabled={uploading} data-testid="branding-logo-upload-btn" className="rounded-full gap-2">
            <ImageUp size={15} /> Carica nuovo logo
          </Button>
          {logoUrl && (
            <Button variant="outline" onClick={reset} disabled={uploading} data-testid="branding-logo-reset-btn" className="rounded-full gap-2">
              <RotateCcw size={15} /> Ripristina predefinito
            </Button>
          )}
        </div>
      </div>
    </Card>
  );
}
