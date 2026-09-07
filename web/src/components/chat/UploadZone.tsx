import { useRef, useState } from "react";
import { motion } from "framer-motion";
import { FileUp, Link2, Loader2 } from "lucide-react";

import { FORMATOS_ACEPTADOS } from "@/components/chat/ChatInput";
import { cn } from "@/lib/utils";

interface UploadZoneProps {
  subiendo: boolean;
  etapa: string;
  onArchivo: (archivo: File) => void;
  onEnlace?: (url: string) => void;
}

/** Extensiones que el backend indexa; el resto se rechaza antes de subir. */
const EXTENSIONES = [".pdf", ".docx", ".txt", ".md", ".markdown"];

const esAceptado = (archivo: File) =>
  EXTENSIONES.some((ext) => archivo.name.toLowerCase().endsWith(ext));

export default function UploadZone({ subiendo, etapa, onArchivo, onEnlace }: UploadZoneProps) {
  const [arrastrando, setArrastrando] = useState(false);
  const [modoEnlace, setModoEnlace] = useState(false);
  const [enlace, setEnlace] = useState("");
  const [error, setError] = useState("");
  const fileRef = useRef<HTMLInputElement>(null);

  function elegir(archivo: File | undefined) {
    if (!archivo) return;
    if (!esAceptado(archivo)) {
      setError(
        "Ese formato no lo puedo leer. Sube tu proyecto en PDF, Word (.docx) o texto (.txt/.md).",
      );
      return;
    }
    setError("");
    onArchivo(archivo);
  }

  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.45 }}
    >
      <input
        ref={fileRef}
        type="file"
        accept={FORMATOS_ACEPTADOS}
        className="hidden"
        onChange={(e) => {
          elegir(e.target.files?.[0]);
          e.target.value = "";
        }}
      />
      <button
        disabled={subiendo}
        onClick={() => fileRef.current?.click()}
        onDragOver={(e) => {
          e.preventDefault();
          setArrastrando(true);
        }}
        onDragLeave={() => setArrastrando(false)}
        onDrop={(e) => {
          e.preventDefault();
          setArrastrando(false);
          elegir(e.dataTransfer.files?.[0]);
        }}
        className={cn(
          "w-full glass rounded-3xl px-8 py-10 text-center transition-all",
          arrastrando && "ring-2 ring-primary scale-[1.01]",
          subiendo && "cursor-wait",
        )}
      >
        {subiendo ? (
          <>
            <Loader2 className="w-7 h-7 text-primary mx-auto animate-spin" />
            <p className="mt-3 font-medium">{etapa}</p>
            <div className="mt-3 mx-auto max-w-xs h-1.5 rounded-full bg-muted overflow-hidden">
              <div className="h-full w-full bg-gradient-to-r from-primary/30 via-primary to-primary/30 bg-[length:200%_100%] animate-shimmer rounded-full" />
            </div>
            <p className="mt-2 text-xs text-muted-foreground">
              Los embeddings se generan en el servidor — tu documento no se envía a terceros.
            </p>
          </>
        ) : (
          <>
            <FileUp className="w-7 h-7 text-primary mx-auto" />
            <p className="mt-3 font-medium">Arrastra tu proyecto de tesis</p>
            <p className="mt-1 text-sm text-muted-foreground">
              PDF, Word (.docx) o texto — detectaré su estructura automáticamente
            </p>
            <p className="mt-1 text-xs text-muted-foreground">
              También puedes pegar el texto directamente en el chat, aunque sea solo un avance.
            </p>
          </>
        )}
      </button>

      {!subiendo && onEnlace && (
        <div className="mt-2 text-center">
          {modoEnlace ? (
            <div className="flex items-center gap-2 glass rounded-2xl px-3 py-2">
              <Link2 className="w-4 h-4 text-muted-foreground shrink-0" />
              <input
                autoFocus
                value={enlace}
                onChange={(e) => setEnlace(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && enlace.trim()) onEnlace(enlace.trim());
                  if (e.key === "Escape") setModoEnlace(false);
                }}
                placeholder="Pega el enlace de tu Google Doc (compartido como «cualquiera con el enlace»)"
                className="flex-1 bg-transparent text-sm outline-none placeholder:text-muted-foreground"
              />
              <button
                disabled={!enlace.trim()}
                onClick={() => onEnlace(enlace.trim())}
                className="text-sm font-medium text-primary disabled:opacity-40"
              >
                Importar
              </button>
            </div>
          ) : (
            <button
              onClick={() => setModoEnlace(true)}
              className="text-xs text-muted-foreground hover:text-foreground inline-flex items-center gap-1.5"
            >
              <Link2 className="w-3.5 h-3.5" />
              o importa desde un enlace de Google Docs
            </button>
          )}
        </div>
      )}

      {error && <p className="mt-2 text-center text-xs text-destructive">{error}</p>}
    </motion.div>
  );
}
