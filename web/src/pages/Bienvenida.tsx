import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { motion } from "framer-motion";
import { CheckCircle2, GraduationCap, MailWarning, Sparkles } from "lucide-react";

import ThemeToggle from "@/components/ThemeToggle";
import { Button } from "@/components/ui/button";
import { supabase } from "@/lib/supabase";

/**
 * Pantalla a la que Supabase redirige tras confirmar el correo (emailRedirectTo).
 * La VALIDACIÓN la hace Supabase; aquí solo damos la bienvenida con el estilo de
 * la app en lugar del mensaje plano por defecto.
 *
 * Estados:
 *  - éxito + sesión  → "correo verificado" con botón directo a la app.
 *  - éxito sin sesión → verificado, pero debe iniciar sesión (p. ej. abrió el
 *    enlace en otro navegador).
 *  - error → el enlace expiró o ya fue usado (Supabase lo manda en el hash).
 */
export default function Bienvenida() {
  // Captura el error del hash/query ANTES de que el SDK lo limpie.
  const [errorDesc] = useState<string | null>(() => {
    const hash = new URLSearchParams(window.location.hash.replace(/^#/, ""));
    const query = new URLSearchParams(window.location.search);
    return hash.get("error_description") ?? query.get("error_description");
  });
  const [conSesion, setConSesion] = useState<boolean | null>(null);

  useEffect(() => {
    if (!supabase) {
      setConSesion(false);
      return;
    }
    // detectSessionInUrl ya procesó los tokens del enlace: si la confirmación
    // creó sesión, entramos directo; si no, pedimos iniciar sesión.
    supabase.auth
      .getSession()
      .then(({ data }) => setConSesion(data.session !== null))
      .catch(() => setConSesion(false));
    const { data: sub } = supabase.auth.onAuthStateChange((_evt, s) => {
      if (s) setConSesion(true);
    });
    return () => sub.subscription.unsubscribe();
  }, []);

  const esError = !!errorDesc;

  return (
    <div className="min-h-screen grid place-items-center px-5 relative overflow-hidden">
      <div className="absolute top-4 right-4 z-10">
        <ThemeToggle />
      </div>

      {/* Blobs de fondo, como en Auth */}
      <motion.div
        aria-hidden
        className="absolute -top-32 -right-32 w-[30rem] h-[30rem] rounded-full bg-[#007AFF]/12 blur-3xl"
        animate={{ y: [0, 28, 0] }}
        transition={{ duration: 12, repeat: Infinity, ease: "easeInOut" }}
      />
      <motion.div
        aria-hidden
        className="absolute -bottom-40 -left-32 w-[26rem] h-[26rem] rounded-full bg-[#34C759]/10 blur-3xl"
        animate={{ y: [0, -24, 0] }}
        transition={{ duration: 14, repeat: Infinity, ease: "easeInOut" }}
      />

      <motion.div
        initial={{ opacity: 0, y: 18 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.5 }}
        className="relative w-full max-w-md"
      >
        <Link to="/" className="flex items-center justify-center gap-2 font-semibold mb-6">
          <GraduationCap className="w-6 h-6 text-primary" />
          MentorIA
        </Link>

        <div className="glass rounded-3xl p-8 text-center">
          <motion.div
            initial={{ scale: 0, rotate: -20 }}
            animate={{ scale: 1, rotate: 0 }}
            transition={{ type: "spring", stiffness: 260, damping: 16, delay: 0.15 }}
            className={`mx-auto w-20 h-20 rounded-full grid place-items-center ${
              esError ? "bg-[#FF9500]/15" : "bg-[#34C759]/15"
            }`}
          >
            {esError ? (
              <MailWarning className="w-10 h-10 text-[#FF9500]" />
            ) : (
              <CheckCircle2 className="w-10 h-10 text-[#34C759]" />
            )}
          </motion.div>

          {esError ? (
            <>
              <h1 className="mt-5 text-2xl font-semibold tracking-tight">
                Este enlace ya no es válido
              </h1>
              <p className="mt-2 text-sm text-muted-foreground leading-relaxed">
                Puede que haya expirado o que ya lo hayas usado. Si tu correo aún no está
                confirmado, regístrate de nuevo para recibir otro enlace; si ya lo
                confirmaste antes, simplemente inicia sesión.
              </p>
              <Button asChild className="mt-6 w-full rounded-xl h-11 text-base">
                <Link to="/auth">Ir a iniciar sesión</Link>
              </Button>
            </>
          ) : (
            <>
              <h1 className="mt-5 text-2xl font-semibold tracking-tight">
                ¡Correo verificado!
              </h1>
              <p className="mt-2 text-sm text-muted-foreground leading-relaxed">
                Bienvenido(a) a <span className="font-medium text-foreground">MentorIA</span>.
                Tu cuenta está lista: sube tu proyecto de tesis y deja que la red de
                agentes lo revise contigo, sección por sección.
              </p>

              <div className="mt-5 flex items-center justify-center gap-1.5 text-[12px] text-muted-foreground">
                <Sparkles className="w-3.5 h-3.5 text-primary" />
                Rúbrica oficial UPAO · agentes especializados · avances guardados en tu cuenta
              </div>

              {conSesion ? (
                <Button asChild className="mt-6 w-full rounded-xl h-11 text-base">
                  <Link to="/app">Comenzar mi asesoría</Link>
                </Button>
              ) : (
                <Button asChild className="mt-6 w-full rounded-xl h-11 text-base">
                  <Link to="/auth">Iniciar sesión para empezar</Link>
                </Button>
              )}
            </>
          )}
        </div>

        <p className="mt-5 text-center text-xs text-muted-foreground">
          Los agentes pueden equivocarse — valida las sugerencias con tu asesor.
        </p>
      </motion.div>
    </div>
  );
}
