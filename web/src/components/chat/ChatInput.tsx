import { useRef, useState } from "react";
import {
  ArrowUpIcon,
  Check,
  ChevronDown,
  Gauge,
  Paperclip,
  Square,
} from "lucide-react";

import AdjuntoChip from "@/components/chat/AdjuntoChip";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { useAutoResizeTextarea } from "@/hooks/use-auto-resize-textarea";
import { cn } from "@/lib/utils";
import type { AdjuntoTexto } from "@/types";

/** Formatos que el backend sabe indexar (ver backend/ingesta). */
export const FORMATOS_ACEPTADOS =
  ".pdf,.docx,.txt,.md,.markdown,application/pdf," +
  "application/vnd.openxmlformats-officedocument.wordprocessingml.document,text/plain,text/markdown";

// A partir de aquí un pegado deja de ser un mensaje y pasa a ser un documento:
// volcarlo en la burbuja hacía ilegible el chat. Se adjunta como TXT.
const UMBRAL_PEGADO_CHARS = 1500;
const UMBRAL_PEGADO_LINEAS = 15;

let _idAdjunto = 0;
const nuevoIdAdjunto = () => `adj${Date.now()}_${_idAdjunto++}`;

export const NIVELES_ITERACION = [
  { valor: 1, nombre: "Rápido", detalle: "1 iteración · ~3 min" },
  { valor: 2, nombre: "Equilibrado", detalle: "2 iteraciones · ~7 min" },
  { valor: 3, nombre: "Profundo", detalle: "3 iteraciones · ~12 min" },
] as const;

interface ChatInputProps {
  ejecutando: boolean;
  deshabilitado?: boolean;
  iteraciones: number;
  onIteraciones: (n: number) => void;
  onEnviar: (texto: string, adjuntos: AdjuntoTexto[]) => void;
  onDetener: () => void;
  onArchivo: (archivo: File) => void;
}

export default function ChatInput({
  ejecutando,
  deshabilitado,
  iteraciones,
  onIteraciones,
  onEnviar,
  onDetener,
  onArchivo,
}: ChatInputProps) {
  const [mensaje, setMensaje] = useState("");
  const [adjuntos, setAdjuntos] = useState<AdjuntoTexto[]>([]);
  const [menuAbierto, setMenuAbierto] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);
  const { textareaRef, adjustHeight } = useAutoResizeTextarea({
    minHeight: 48,
    maxHeight: 160,
  });

  const nivel = NIVELES_ITERACION.find((n) => n.valor === iteraciones) ?? NIVELES_ITERACION[1];
  const puedeEnviar =
    (mensaje.trim().length > 0 || adjuntos.length > 0) && !ejecutando && !deshabilitado;

  function enviar() {
    if (!puedeEnviar) return;
    onEnviar(mensaje.trim(), adjuntos);
    setMensaje("");
    setAdjuntos([]);
    adjustHeight(true);
  }

  /**
   * Un pegado grande se convierte en adjunto en vez de entrar al textarea.
   * Así el estudiante puede pegar una sección entera para que se indexe sin
   * dejar un muro de texto en la conversación.
   */
  function alPegar(e: React.ClipboardEvent<HTMLTextAreaElement>) {
    const pegado = e.clipboardData.getData("text");
    if (!pegado) return;
    const lineas = pegado.split(/\r\n|\r|\n/).length;
    if (pegado.length < UMBRAL_PEGADO_CHARS && lineas < UMBRAL_PEGADO_LINEAS) return;

    e.preventDefault();
    setAdjuntos((prev) => [
      ...prev,
      {
        id: nuevoIdAdjunto(),
        nombre: `Texto pegado ${prev.length + 1}`,
        texto: pegado,
        lineas,
        chars: pegado.length,
      },
    ]);
  }

  return (
    <div className="relative glass rounded-3xl">
      {adjuntos.length > 0 && (
        <div className="flex flex-wrap gap-2 px-4 pt-3">
          {adjuntos.map((a) => (
            <AdjuntoChip
              key={a.id}
              adjunto={a}
              onQuitar={() => setAdjuntos((prev) => prev.filter((x) => x.id !== a.id))}
            />
          ))}
        </div>
      )}
      <Textarea
        ref={textareaRef}
        value={mensaje}
        disabled={deshabilitado}
        onChange={(e) => {
          setMensaje(e.target.value);
          adjustHeight();
        }}
        onPaste={alPegar}
        onKeyDown={(e) => {
          if (e.key === "Enter" && !e.shiftKey) {
            e.preventDefault();
            enviar();
          }
        }}
        placeholder={
          ejecutando
            ? "Los agentes están trabajando…"
            : adjuntos.length
              ? "Añade una instrucción para tu texto adjunto (o envíalo tal cual)…"
              : "Pide una revisión, o pega el texto de tu proyecto para indexarlo…"
        }
        className={cn(
          "w-full px-5 py-3.5 resize-none border-none rounded-3xl",
          "bg-transparent text-[15px]",
          "focus-visible:ring-0 focus-visible:ring-offset-0",
          "placeholder:text-muted-foreground min-h-[48px]",
        )}
        style={{ overflow: "hidden" }}
      />

      <div className="flex items-center justify-between px-3 pb-3">
        <div className="flex items-center gap-1.5">
          <input
            ref={fileRef}
            type="file"
            accept={FORMATOS_ACEPTADOS}
            className="hidden"
            onChange={(e) => {
              const f = e.target.files?.[0];
              if (f) onArchivo(f);
              e.target.value = "";
            }}
          />
          <Button
            variant="ghost"
            size="icon"
            title="Subir tu proyecto (PDF, Word o texto)"
            className="rounded-full text-muted-foreground hover:text-foreground"
            onClick={() => fileRef.current?.click()}
          >
            <Paperclip className="w-4 h-4" />
          </Button>

          <div className="relative">
            <button
              onClick={() => setMenuAbierto((v) => !v)}
              className="flex items-center gap-1.5 text-[13px] text-muted-foreground hover:text-foreground rounded-full px-2.5 py-1.5 hover:bg-muted transition-colors"
            >
              <Gauge className="w-3.5 h-3.5" />
              {nivel.nombre}
              <ChevronDown className="w-3.5 h-3.5" />
            </button>

            {menuAbierto && (
              <>
                <div className="fixed inset-0 z-10" onClick={() => setMenuAbierto(false)} />
                <div className="absolute bottom-full mb-2 left-0 z-20 w-60 bg-card text-card-foreground border border-border rounded-2xl p-1.5 shadow-xl">
                  <p className="px-3 pt-1.5 pb-1 text-[11px] font-medium text-muted-foreground uppercase tracking-wide">
                    Profundidad de revisión
                  </p>
                  {NIVELES_ITERACION.map((n) => (
                    <button
                      key={n.valor}
                      onClick={() => {
                        onIteraciones(n.valor);
                        setMenuAbierto(false);
                      }}
                      className="w-full flex items-center justify-between rounded-xl px-3 py-2 hover:bg-muted text-left"
                    >
                      <span>
                        <span className="block text-sm font-medium">{n.nombre}</span>
                        <span className="block text-xs text-muted-foreground">{n.detalle}</span>
                      </span>
                      {n.valor === iteraciones && <Check className="w-4 h-4 text-primary" />}
                    </button>
                  ))}
                </div>
              </>
            )}
          </div>
        </div>

        {ejecutando ? (
          <Button
            size="icon"
            onClick={onDetener}
            title="Detener a los agentes"
            className="rounded-full bg-foreground hover:bg-foreground/85"
          >
            <Square className="w-3.5 h-3.5 fill-current" />
          </Button>
        ) : (
          <Button
            size="icon"
            disabled={!puedeEnviar}
            onClick={enviar}
            className="rounded-full shadow-md shadow-primary/25"
          >
            <ArrowUpIcon className="w-4 h-4" />
            <span className="sr-only">Enviar</span>
          </Button>
        )}
      </div>
    </div>
  );
}
