import { supabase } from "./supabase";
import type { ReglamentoInfo, RubricaUpaoInfo } from "@/types";

const API_URL = (import.meta.env.VITE_API_URL as string | undefined) || "";

export interface SeccionStat {
  seccion: string;
  pagina_inicio: number;
  chars: number;
  n_fragmentos: number;
  mejorado?: boolean;
}

export interface DocumentoInfo {
  doc_id: string;
  nombre: string;
  hash: string;
  ya_indexado: boolean;
  estructura_toc: Record<string, number>;
  stats: SeccionStat[];
  /** De dónde vino el proyecto: "pdf" | "docx" | "texto". */
  formato?: string;
  /** Con qué señal se resolvió la estructura (estilos de Word, marcadores, índice…). */
  origen_estructura?: string;
  /** Avisos de la indexación (páginas sin texto, índice desfasado, sin encabezados…). */
  avisos?: string[];
  alcance?: AlcanceInfo;
}

/** Qué partes del proyecto se someten a evaluación. */
export interface AlcanceInfo {
  modo: "auto" | "declarado";
  grupos: string[];
  items: number[];
}

export interface GrupoAlcance {
  grupo: string;
  items: number[];
  descripcion: string;
}

export interface CatalogoAlcance {
  grupos: GrupoAlcance[];
  alcance: AlcanceInfo | Record<string, never>;
  /** Ítem → caracteres escritos en el proyecto: permite marcar qué ya tiene avance. */
  chars_por_item: Record<string, number>;
}

export interface ChatRespuesta {
  tipo: "conversacion" | "run" | "confirmacion";
  respuesta?: string;
  run_id?: string;
  modo?: "completo" | "secciones";
  secciones?: string[];
  subtipo?: "reevaluar" | "aplicar_mejoras";
  mensaje?: string;
  mejoras_aplicadas?: string[];
}

export interface ChatFlags {
  confirmar_reevaluacion?: boolean;
  decision_mejoras?: "aplicar" | "mantener";
}

export interface EventoRun {
  tipo: string;
  [key: string]: unknown;
}

async function authHeaders(): Promise<Record<string, string>> {
  if (!supabase) return {};
  const { data } = await supabase.auth.getSession();
  const token = data.session?.access_token;
  return token ? { Authorization: `Bearer ${token}` } : {};
}

/** Error de la API con su código HTTP (0 = no hubo respuesta: red caída o CORS). */
export class ApiError extends Error {
  status: number;
  /** El usuario ya fue avisado por otra vía: no hace falta otro mensaje de error. */
  silencioso: boolean;
  constructor(mensaje: string, status: number, silencioso = false) {
    super(mensaje);
    this.name = "ApiError";
    this.status = status;
    this.silencioso = silencioso;
  }
}

async function manejarError(res: Response): Promise<never> {
  let detalle = `Error ${res.status}`;
  try {
    const body = await res.json();
    detalle = body.detail || detalle;
  } catch {
    /* respuesta sin JSON */
  }
  throw new ApiError(detalle, res.status);
}

// ── Servidor arrancando ───────────────────────────────────────────────────────
// El backend corre en UNA instancia de Cloud Run (el registro de proyectos vive en
// memoria). Cuando Cloud Run la recicla —pasa cada uno o dos días, y en cada
// despliegue— la nueva tarda ~1 min en cargar modelos y, mientras tanto, Cloud Run
// responde 429 «no available instance» SIN cabeceras CORS: el navegador lo ve como
// «Failed to fetch». Eso le llegaba al estudiante como un error en su primer mensaje
// tras entrar, o como «el archivo almacenado ya no es legible». Ahora se reintenta
// con espera creciente y la pantalla avisa que el servidor está arrancando.
type OyenteServidor = (arrancando: boolean) => void;
const oyentes = new Set<OyenteServidor>();

export function suscribirEstadoServidor(fn: OyenteServidor): () => void {
  oyentes.add(fn);
  return () => {
    oyentes.delete(fn);
  };
}

let esperando = 0;
function marcarEspera(delta: 1 | -1) {
  const antes = esperando > 0;
  esperando = Math.max(0, esperando + delta);
  if (antes !== esperando > 0) oyentes.forEach((fn) => fn(esperando > 0));
}

const ESPERA_MAX_MS = 150_000;
// 429 = Cloud Run no tenía instancia lista: la petición nunca llegó a la app y
// reintentarla es inocuo. 502/503/504 sí pudieron llegar (p. ej. una instancia que
// murió por memoria a mitad de indexar): un POST se reintenta una sola vez.
const SIN_INSTANCIA = 429;
const FALLOS_PASARELA = new Set([502, 503, 504]);

async function fetchApi(ruta: string, init: RequestInit = {}): Promise<Response> {
  const inicio = Date.now();
  const metodo = (init.method ?? "GET").toUpperCase();
  const maxPasarela = metodo === "GET" ? 4 : 1;
  let intento = 0;
  let fallosPasarela = 0;
  let enEspera = false;
  try {
    for (;;) {
      let res: Response | null = null;
      try {
        res = await fetch(`${API_URL}${ruta}`, {
          ...init,
          headers: { ...(init.headers as Record<string, string> | undefined), ...(await authHeaders()) },
        });
      } catch (exc) {
        if (exc instanceof DOMException && exc.name === "AbortError") throw exc;
        res = null; // red caída, o el 429 de Cloud Run sin cabeceras CORS
      }
      if (res && res.status !== SIN_INSTANCIA && !FALLOS_PASARELA.has(res.status)) return res;
      if (res && FALLOS_PASARELA.has(res.status) && ++fallosPasarela > maxPasarela) return res;
      if (Date.now() - inicio > ESPERA_MAX_MS) {
        if (res) return res;
        throw new ApiError(
          "No pude conectar con el servidor. Revisa tu conexión e inténtalo de nuevo en un momento.",
          0,
        );
      }
      if (!enEspera) {
        enEspera = true;
        marcarEspera(1);
      }
      intento += 1;
      await new Promise((r) => setTimeout(r, Math.min(1500 * intento, 8000)));
    }
  } finally {
    if (enEspera) marcarEspera(-1);
  }
}

/** Toca el backend sin autenticar: si se está reiniciando, el aviso aparece antes
 *  de que el estudiante envíe nada. Nunca lanza. */
export async function despertarServidor(): Promise<void> {
  try {
    await fetchApi("/health");
  } catch {
    /* el siguiente pedido real mostrará el error si sigue caído */
  }
}

export interface DocMemoria {
  evaluadas: string[];
  aplicadas: Record<string, string>;
  pendientes: Record<string, string>;
  // Resumen de la última evaluación, para que el chat rápido no pierda el hilo.
  ultima_revision?: { tipo?: string; texto?: string };
}

/** Origen del proyecto: un archivo, texto pegado o un enlace de Google Docs. */
export type FuenteDocumento =
  | { tipo: "archivo"; archivo: File }
  | { tipo: "texto"; texto: string; nombre?: string }
  | { tipo: "enlace"; enlace: string };

export async function subirDocumento(
  fuente: File | FuenteDocumento,
  memoria?: DocMemoria | null,
): Promise<DocumentoInfo> {
  const form = new FormData();
  const origen: FuenteDocumento =
    fuente instanceof File ? { tipo: "archivo", archivo: fuente } : fuente;

  if (origen.tipo === "archivo") {
    form.append("archivo", origen.archivo);
  } else if (origen.tipo === "texto") {
    form.append("texto", origen.texto);
    form.append("nombre", origen.nombre ?? "Texto pegado");
  } else {
    form.append("enlace", origen.enlace);
  }
  if (memoria) form.append("memoria", JSON.stringify(memoria));
  const res = await fetchApi("/api/documentos", {
    method: "POST",
    body: form,
  });
  if (!res.ok) await manejarError(res);
  return res.json();
}

/** Texto pegado cuando YA hay proyecto: se ubica en una sección y se guarda como
 *  versión de trabajo, sin pisar el documento original. */
export async function agregarFragmento(
  docId: string,
  texto: string,
  nombre = "Texto pegado",
): Promise<{ seccion: string | null; mensaje: string }> {
  const res = await fetchApi("/api/fragmento", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ doc_id: docId, texto, nombre }),
  });
  if (!res.ok) await manejarError(res);
  return res.json();
}

/** Grupos evaluables + alcance actual del proyecto. */
export async function obtenerAlcance(docId: string): Promise<CatalogoAlcance> {
  const res = await fetchApi(`/api/alcance?doc_id=${encodeURIComponent(docId)}`);
  if (!res.ok) await manejarError(res);
  return res.json();
}

/** Declara qué partes del proyecto quiere el estudiante que se evalúen. */
export async function fijarAlcance(
  docId: string,
  opciones: { grupos?: string[]; todo?: boolean },
): Promise<{ alcance: AlcanceInfo }> {
  const res = await fetchApi("/api/alcance", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ doc_id: docId, grupos: opciones.grupos ?? null, todo: !!opciones.todo }),
  });
  if (!res.ok) await manejarError(res);
  return res.json();
}

/** Rúbrica oficial UPAO (fija). Con `docId` incluye el mapeo ítem→secciones del proyecto. */
export async function obtenerRubricaUpao(docId?: string | null): Promise<RubricaUpaoInfo> {
  const qs = docId ? `?doc_id=${encodeURIComponent(docId)}` : "";
  const res = await fetchApi(`/api/rubrica${qs}`);
  if (!res.ok) await manejarError(res);
  return res.json();
}

/** Reglamento UPAO fijo: vigencia, resolución y puntos que afectan la tesis. */
export async function obtenerReglamentoUpao(): Promise<ReglamentoInfo> {
  const res = await fetchApi("/api/reglamento");
  if (!res.ok) await manejarError(res);
  return res.json();
}

export async function obtenerBiblioteca(): Promise<{
  libros: { nombre: string; fragmentos: number }[];
  total_fragmentos: number;
}> {
  const res = await fetchApi("/api/biblioteca");
  if (!res.ok) await manejarError(res);
  return res.json();
}

export async function enviarChat(body: {
  mensaje: string;
  doc_id: string | null;
  conversacion_id?: string | null;
  max_iteraciones: number;
  contexto_previo: string;
  historial?: { rol: string; contenido: string }[];
} & ChatFlags): Promise<ChatRespuesta> {
  const res = await fetchApi("/api/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) await manejarError(res);
  return res.json();
}

/** Ping de presencia para medir el tiempo de uso. No bloquea ni lanza error. */
export async function enviarHeartbeat(conversacionId: string | null): Promise<void> {
  try {
    // fetch directo, sin reintentos: es analítica y no debe encender el aviso de arranque.
    await fetch(`${API_URL}/api/heartbeat`, {
      method: "POST",
      headers: { "Content-Type": "application/json", ...(await authHeaders()) },
      body: JSON.stringify({ conversacion_id: conversacionId }),
      keepalive: true,
    });
  } catch {
    /* silencioso: la analítica nunca debe romper la app */
  }
}

export async function cancelarRun(runId: string) {
  const res = await fetchApi(`/api/runs/${runId}/cancelar`, {
    method: "POST",
  });
  if (!res.ok) await manejarError(res);
  return res.json();
}

export async function streamRun(
  runId: string,
  onEvento: (e: EventoRun) => void,
  signal?: AbortSignal,
): Promise<void> {
  const res = await fetchApi(`/api/runs/${runId}/stream`, { signal });
  if (!res.ok || !res.body) await manejarError(res);

  const reader = res.body!.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    const bloques = buffer.split("\n\n");
    buffer = bloques.pop() ?? "";
    for (const bloque of bloques) {
      const linea = bloque.split("\n").find((l) => l.startsWith("data: "));
      if (!linea) continue;
      try {
        onEvento(JSON.parse(linea.slice(6)) as EventoRun);
      } catch {
        /* evento malformado: ignorar */
      }
    }
  }
}
