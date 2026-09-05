import { FormEvent, useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { motion } from "framer-motion";
import { Eye, EyeOff, GraduationCap, KeyRound, Loader2, MailWarning } from "lucide-react";

import ThemeToggle from "@/components/ThemeToggle";
import { Button } from "@/components/ui/button";
import { supabase } from "@/lib/supabase";

/**
 * Destino del enlace de recuperación de contraseña (resetPasswordForEmail →
 * redirectTo). Supabase procesa el token del enlace (detectSessionInUrl) y crea
 * una sesión temporal de recuperación; aquí el usuario define su nueva
 * contraseña con supabase.auth.updateUser({ password }).
 */
export default function Recuperar() {
  const navigate = useNavigate();

  // Captura el error del hash/query ANTES de que el SDK lo limpie (enlace
  // expirado o ya usado).
  const [errorEnlace] = useState<string | null>(() => {
    const hash = new URLSearchParams(window.location.hash.replace(/^#/, ""));
    const query = new URLSearchParams(window.location.search);
    return hash.get("error_description") ?? query.get("error_description");
  });

  const [listo, setListo] = useState(false);
  const [password, setPassword] = useState("");
  const [confirmar, setConfirmar] = useState("");
  const [verPassword, setVerPassword] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [ok, setOk] = useState(false);
  const [cargando, setCargando] = useState(false);

  useEffect(() => {
    if (!supabase) return;
    // Si el enlace trajo una sesión de recuperación válida, habilitamos el form.
    supabase.auth.getSession().then(({ data }) => {
      if (data.session) setListo(true);
    });
    const { data: sub } = supabase.auth.onAuthStateChange((evt, s) => {
      if (evt === "PASSWORD_RECOVERY" || s) setListo(true);
    });
    return () => sub.subscription.unsubscribe();
  }, []);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    if (!supabase) return;
    setError(null);
    if (password !== confirmar) {
      setError("Las contraseñas no coinciden.");
      return;
    }
    setCargando(true);
    try {
      const { error } = await supabase.auth.updateUser({ password });
      if (error) throw error;
      setOk(true);
      setTimeout(() => navigate("/app"), 1500);
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "No se pudo actualizar la contraseña");
    } finally {
      setCargando(false);
    }
  }

  return (
    <div className="min-h-screen grid place-items-center px-5 relative overflow-hidden">
      <div className="absolute top-4 right-4 z-10">
        <ThemeToggle />
      </div>
      <motion.div
        aria-hidden
        className="absolute -top-32 -right-32 w-[30rem] h-[30rem] rounded-full bg-[#007AFF]/12 blur-3xl"
        animate={{ y: [0, 28, 0] }}
        transition={{ duration: 12, repeat: Infinity, ease: "easeInOut" }}
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

        <div className="glass rounded-3xl p-8">
          {errorEnlace ? (
            <div className="text-center">
              <div className="mx-auto w-16 h-16 rounded-full grid place-items-center bg-[#FF9500]/15">
                <MailWarning className="w-8 h-8 text-[#FF9500]" />
              </div>
              <h1 className="mt-5 text-xl font-semibold tracking-tight">
                Este enlace ya no es válido
              </h1>
              <p className="mt-2 text-sm text-muted-foreground leading-relaxed">
                Puede que haya expirado o que ya lo hayas usado. Vuelve a solicitar un
                enlace de recuperación desde la pantalla de inicio de sesión.
              </p>
              <Button asChild className="mt-6 w-full rounded-xl h-11 text-base">
                <Link to="/auth">Ir a iniciar sesión</Link>
              </Button>
            </div>
          ) : ok ? (
            <div className="text-center">
              <div className="mx-auto w-16 h-16 rounded-full grid place-items-center bg-[#34C759]/15">
                <KeyRound className="w-8 h-8 text-[#34C759]" />
              </div>
              <h1 className="mt-5 text-xl font-semibold tracking-tight">
                Contraseña actualizada
              </h1>
              <p className="mt-2 text-sm text-muted-foreground leading-relaxed">
                Te llevamos a tu espacio de trabajo…
              </p>
            </div>
          ) : (
            <>
              <div className="text-center">
                <h1 className="text-xl font-semibold tracking-tight">Nueva contraseña</h1>
                <p className="mt-1.5 text-sm text-muted-foreground">
                  Elige una contraseña para tu cuenta.
                </p>
              </div>

              <form onSubmit={onSubmit} className="mt-6 space-y-4">
                <div>
                  <label className="text-sm font-medium">Nueva contraseña</label>
                  <div className="relative mt-1.5">
                    <input
                      type={verPassword ? "text" : "password"}
                      required
                      minLength={6}
                      value={password}
                      onChange={(e) => setPassword(e.target.value)}
                      placeholder="Mínimo 6 caracteres"
                      className="w-full rounded-xl border border-input bg-card pl-3.5 pr-11 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
                    />
                    <button
                      type="button"
                      onClick={() => setVerPassword((v) => !v)}
                      title={verPassword ? "Ocultar contraseña" : "Mostrar contraseña"}
                      aria-label={verPassword ? "Ocultar contraseña" : "Mostrar contraseña"}
                      className="absolute right-1.5 top-1/2 -translate-y-1/2 w-8 h-8 grid place-items-center rounded-lg text-muted-foreground hover:text-foreground hover:bg-muted transition-colors"
                    >
                      {verPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                    </button>
                  </div>
                </div>
                <div>
                  <label className="text-sm font-medium">Confirmar contraseña</label>
                  <input
                    type={verPassword ? "text" : "password"}
                    required
                    minLength={6}
                    value={confirmar}
                    onChange={(e) => setConfirmar(e.target.value)}
                    placeholder="Repite la contraseña"
                    className="mt-1.5 w-full rounded-xl border border-input bg-card px-3.5 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
                  />
                </div>

                {error && (
                  <p className="text-sm text-destructive bg-destructive/10 rounded-xl px-3.5 py-2.5">{error}</p>
                )}
                {!listo && !error && (
                  <p className="text-sm text-muted-foreground bg-muted rounded-xl px-3.5 py-2.5">
                    Validando el enlace de recuperación…
                  </p>
                )}

                <Button
                  type="submit"
                  disabled={cargando || !listo}
                  className="w-full rounded-xl h-11 text-base"
                >
                  {cargando && <Loader2 className="w-4 h-4 mr-2 animate-spin" />}
                  Guardar contraseña
                </Button>
              </form>
            </>
          )}
        </div>
      </motion.div>
    </div>
  );
}
