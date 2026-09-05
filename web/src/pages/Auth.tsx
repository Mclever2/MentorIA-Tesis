import { FormEvent, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { motion } from "framer-motion";
import { Eye, EyeOff, GraduationCap, Loader2 } from "lucide-react";

import ThemeToggle from "@/components/ThemeToggle";
import { Button } from "@/components/ui/button";
import { supabase } from "@/lib/supabase";

export default function Auth() {
  const navigate = useNavigate();
  // Solo dos modos: iniciar sesión y recuperar contraseña. El registro está
  // deshabilitado: las cuentas las crea el administrador desde Supabase.
  const [modo, setModo] = useState<"login" | "recuperar">("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [verPassword, setVerPassword] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [aviso, setAviso] = useState<string | null>(null);
  const [cargando, setCargando] = useState(false);

  function cambiarModo(m: "login" | "recuperar") {
    setModo(m);
    setError(null);
    setAviso(null);
  }

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    if (!supabase) return;
    setError(null);
    setAviso(null);
    setCargando(true);
    try {
      if (modo === "recuperar") {
        const { error } = await supabase.auth.resetPasswordForEmail(email, {
          // Supabase envía un correo con un enlace que apunta AQUÍ. La URL debe
          // estar en la allowlist de Supabase → Authentication → URL Configuration
          // → Redirect URLs.
          redirectTo: `${window.location.origin}/recuperar`,
        });
        if (error) throw error;
        setAviso(
          "Si ese correo tiene una cuenta, te enviamos un enlace para restablecer tu contraseña. Revisa tu bandeja de entrada (y spam).",
        );
      } else {
        const { error } = await supabase.auth.signInWithPassword({ email, password });
        if (error) throw error;
        navigate("/app");
      }
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "Error de autenticación");
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
          <div className="text-center">
            <h1 className="text-xl font-semibold tracking-tight">
              {modo === "login" ? "Iniciar sesión" : "Recuperar contraseña"}
            </h1>
            <p className="mt-1.5 text-sm text-muted-foreground">
              {modo === "login"
                ? "Ingresa con la cuenta que te asignaron."
                : "Te enviaremos un enlace para crear una nueva contraseña."}
            </p>
          </div>

          <form onSubmit={onSubmit} className="mt-6 space-y-4">
            <div>
              <label className="text-sm font-medium">Correo</label>
              <input
                type="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="tu@correo.com"
                className="mt-1.5 w-full rounded-xl border border-input bg-card px-3.5 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
              />
            </div>

            {modo === "login" && (
              <div>
                <div className="flex items-center justify-between">
                  <label className="text-sm font-medium">Contraseña</label>
                  <button
                    type="button"
                    onClick={() => cambiarModo("recuperar")}
                    className="text-xs font-medium text-primary hover:underline"
                  >
                    ¿Olvidaste tu contraseña?
                  </button>
                </div>
                <div className="relative mt-1.5">
                  <input
                    type={verPassword ? "text" : "password"}
                    required
                    minLength={6}
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    placeholder="Tu contraseña"
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
            )}

            {error && (
              <p className="text-sm text-destructive bg-destructive/10 rounded-xl px-3.5 py-2.5">{error}</p>
            )}
            {aviso && (
              <p className="text-sm text-accent-foreground bg-accent rounded-xl px-3.5 py-2.5">{aviso}</p>
            )}

            <Button type="submit" disabled={cargando} className="w-full rounded-xl h-11 text-base">
              {cargando && <Loader2 className="w-4 h-4 mr-2 animate-spin" />}
              {modo === "login" ? "Entrar" : "Enviar enlace de recuperación"}
            </Button>

            {modo === "recuperar" && (
              <button
                type="button"
                onClick={() => cambiarModo("login")}
                className="w-full text-center text-sm text-muted-foreground hover:text-foreground transition-colors"
              >
                Volver a iniciar sesión
              </button>
            )}
          </form>
        </div>

        <p className="mt-5 text-center text-xs text-muted-foreground">
          Tus asesorías se guardan en tu cuenta y solo tú puedes verlas.
        </p>
      </motion.div>
    </div>
  );
}
