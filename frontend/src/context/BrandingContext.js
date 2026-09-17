import { createContext, useContext, useEffect, useState, useCallback } from "react";
import { api, BACKEND_URL } from "@/lib/api";

const BrandingCtx = createContext({ logoUrl: null, refresh: () => {} });
export const useBranding = () => useContext(BrandingCtx);

export function BrandingProvider({ children }) {
  const [logoUrl, setLogoUrl] = useState(null);

  const refresh = useCallback(async () => {
    try {
      const { data } = await api.get("/branding");
      setLogoUrl(data.logo_url ? `${BACKEND_URL}${data.logo_url}` : null);
    } catch {
      setLogoUrl(null);
    }
  }, []);

  useEffect(() => { refresh(); }, [refresh]);

  return <BrandingCtx.Provider value={{ logoUrl, refresh }}>{children}</BrandingCtx.Provider>;
}
