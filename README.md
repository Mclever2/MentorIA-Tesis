# Sistema de Mentoría Académica UPAO — Red Multiagente

> Sistema de inteligencia artificial multiagente que evalúa y mejora proyectos de tesis de la **Universidad Privada Antenor Orrego (UPAO)**, Facultad de Ingeniería, usando la rúbrica oficial de 33 ítems.

> **Arquitectura:** interfaz **React** (carpeta [`web/`](web/)) con chat conversacional, landing,
> inicio de sesión (Supabase) y streaming de progreso en vivo, sobre la API **FastAPI** de
> [`api/`](api/). El grafo LangGraph de [`backend/`](backend/) contiene la lógica multiagente.
> Guía completa de despliegue en Cloud Run: **[DEPLOY.md](DEPLOY.md)**.

---

## Tabla de Contenidos

- [Descripción](#descripción)
- [Arquitectura](#arquitectura)
- [Requisitos previos](#requisitos-previos)
- [Instalación](#instalación)
- [Configuración](#configuración)
- [Corpus de títulos del repositorio UPAO](#corpus-de-títulos-del-repositorio-upao)
- [Arrancar el proyecto](#arrancar-el-proyecto)
- [Estructura del proyecto](#estructura-del-proyecto)
- [Cómo usar el sistema](#cómo-usar-el-sistema)
- [Agentes y sus roles](#agentes-y-sus-roles)
- [Sistema RAG dual](#sistema-rag-dual)
- [Protección anti-bucle](#protección-anti-bucle)
- [Variables de entorno](#variables-de-entorno)
- [Notas de desarrollo](#notas-de-desarrollo)

---

## Descripción

El sistema recibe el proyecto de tesis —en **PDF, Word (.docx), texto plano, pegado en el chat o
importado de un Google Doc compartido**—, el estudiante declara **qué partes quiere que se evalúen**
y una **red multiagente** itera para mejorar el texto hasta que el mentor humano lo aprueba.

Dos decisiones de diseño que conviene conocer antes de leer el resto:

- **La estructura no depende del índice.** Se busca en cascada: estilos de encabezado de Word →
  marcadores del PDF → encabezados detectados en el cuerpo → índice con puntos guía (calibrando el
  desfase entre la página impresa y la física) → clasificación semántica contra la rúbrica. Un avance
  de tres páginas sin índice se indexa igual que una tesis completa.
- **La evaluación es incremental.** Un proyecto se escribe por partes durante meses; calificar
  siempre los 33 ítems ponía 0 en todo lo que el alumno aún no había escrito. Con el **alcance
  declarado**, lo no entregado no se califica y **no resta**.

**Stack tecnológico:**

| Componente | Tecnología |
|---|---|
| Orquestación multiagente | LangGraph `StateGraph` |
| LLM | Groq `llama-3.3-70b-versatile` |
| Base de datos vectorial | ChromaDB (dual: efímera + persistente) |
| Embeddings | HuggingFace `all-MiniLM-L6-v2` (local, CPU) |
| API | FastAPI (streaming SSE) |
| Interfaz | React + Vite + Tailwind (estética iOS) |
| Autenticación e historial | Supabase (auth + Postgres) |
| Salida estructurada | Pydantic v2 |
| Persistencia de sesión | LangGraph `MemorySaver` checkpointer |

---

## Arquitectura

### Topología: Red Multiagente con Supervisor Orquestador

El sistema implementa una **arquitectura de red pura (Supervisor Network)**. El Supervisor LLM lee el estado completo en cada turno y decide dinámicamente qué agente ejecutar. No existen edges hardcodeados entre agentes.

```
START
  │
  ▼
┌─────────────────────────────────────────┐
│         SUPERVISOR ORQUESTADOR          │  ← LLM decide el siguiente paso
│    Lee estado → elige agente → routing  │    en cada iteración de la red
└──────┬──────┬──────┬──────┬─────────────┘
       │      │      │      │   (5 edges condicionales — nunca hardcodeados)
       ▼      ▼      ▼      ▼
  REDACTOR AUDITOR METOD. DEBATE     ← cada agente devuelve resultado
       │      │      │      │          y regresa al Supervisor
       └──────┴──────┴──────┘
                  │
                  ▼  (cuando el Supervisor decide)
          ┌──────────────┐
          │  nodo_humano │  ← HITL: pausa para el mentor
          │ (HITL pause) │
          └──────────────┘
                  │
                 END
```

**Verificación técnica (0 edges hardcodeados entre agentes):**
```
nodo_supervisor  →  nodo_redactor      [CONDICIONAL]
nodo_supervisor  →  nodo_auditor       [CONDICIONAL]
nodo_supervisor  →  nodo_metodologico  [CONDICIONAL]
nodo_supervisor  →  nodo_debate        [CONDICIONAL]
nodo_supervisor  →  nodo_humano        [CONDICIONAL]
nodo_redactor    →  nodo_supervisor    [FIJO - retorno]
nodo_auditor     →  nodo_supervisor    [FIJO - retorno]
nodo_metodologico → nodo_supervisor   [FIJO - retorno]
nodo_debate      →  nodo_supervisor    [FIJO - retorno]
nodo_humano      →  END               [FIJO]
```

---

## Requisitos previos

- **Python** 3.10 o superior — para la API y el grafo
- **Node.js** 18 o superior — para la interfaz React (`web/`)
- **pip** actualizado (`pip install --upgrade pip`)
- **4 claves de API de Groq** (gratuitas): [console.groq.com/keys](https://console.groq.com/keys)
- (Opcional) Un proyecto **Supabase** para activar el inicio de sesión y el historial
- ~**500 MB** de espacio en disco (modelo de embeddings HuggingFace ~80 MB + dependencias)
- Conexión a internet para la primera descarga del modelo de embeddings

---

## Instalación

```bash
# 1. Clonar o descomprimir el proyecto
cd poc_langgraph_mentoria

# 2. Crear entorno virtual (recomendado)
python -m venv venv

# Windows
venv\Scripts\activate

# macOS / Linux
source venv/bin/activate

# 3. Instalar dependencias
pip install -r requirements.txt
```

> **Nota:** La primera ejecución descarga el modelo `all-MiniLM-L6-v2` (~80 MB). Se cachea automáticamente y no se vuelve a descargar.

---

## Configuración

### 1. Crear el archivo `.env`

Copia el archivo de ejemplo y rellena tus claves:

```bash
cp .env.example .env
```

Edita `.env`:

```env
# Una clave de Groq por agente → distribuye el rate limit (6.000 TPM × 4 = 24.000 TPM efectivos)
GROQ_KEY_SUPERVISOR=gsk_...
GROQ_KEY_REDACTOR=gsk_...
GROQ_KEY_AUDITOR=gsk_...
GROQ_KEY_METODOLOGICO=gsk_...

# Fallback: si no defines claves individuales, todos los agentes usan esta
GROQ_API_KEY=gsk_...
```

> **¿Por qué 4 claves?** La API gratuita de Groq tiene un límite de 6.000 tokens por minuto por clave. Con 4 claves independientes el sistema tiene 24.000 TPM efectivos, evitando errores 429 durante el procesamiento paralelo.

### 2. (Opcional) Configurar la interfaz React (`web/.env`)

Sin estas variables la app funciona en **modo invitado** (acceso directo al chat, sin
persistencia). Para activar el **inicio de sesión** y el historial por usuario, crea
`web/.env` a partir de `web/.env.example` y rellena las credenciales de tu proyecto Supabase
(Dashboard → Project Settings → API):

```env
# URL del backend FastAPI; en desarrollo el proxy de Vite enruta /api → :8080
VITE_API_URL=

# Supabase: activa el login y guarda el historial de asesorías por usuario
VITE_SUPABASE_URL=https://xxxxx.supabase.co
VITE_SUPABASE_ANON_KEY=eyJ...
```

> Aplica el esquema de [`supabase/schema.sql`](supabase/schema.sql) en tu proyecto Supabase
> (SQL Editor) para crear las tablas `conversaciones` y `mensajes`.

### 3. (Opcional) Pre-cargar libros de metodología

Coloca PDFs de libros de metodología de investigación en la carpeta `books/`:

```
books/
  Hernandez-Metodologia-de-la-investigacion.pdf
  otro-libro.pdf
```

Se cargan automáticamente en ChromaDB persistente la primera vez que arranca el servidor.

---

## Corpus de títulos del repositorio UPAO

El panel de título propone títulos anclados en tesis **reales ya aprobadas** por la
universidad, no en el criterio suelto de un modelo. Ese corpus se cosecha del
Repositorio Institucional vía **OAI-PMH** (el protocolo estándar de cosecha de
metadatos que el propio repositorio expone) y se indexa una sola vez:

```bash
python -m scripts.cosechar_titulos_upao
```

Recorre los ~16 000 depósitos del repositorio (OAI-PMH no permite filtrar por escuela
en la petición) pero **guarda solo las ~270 tesis de la escuela de sistemas** en
`data/titulos_upao.jsonl`: Ingeniería de Computación y Sistemas, Ingeniería de Sistemas
—incluida la maestría con mención en Sistemas de Información— e Ingeniería de Sistemas
e Inteligencia Artificial. El criterio vive en [`backend/programas.py`](backend/programas.py).

Guardar el repositorio entero era contraproducente: el corpus es el ANCLA de las
propuestas de título, y con 3 840 tesis de Medicina y 1 451 de Ingeniería Civil dentro,
a un tesista de sistemas que consultaba «historias clínicas» se le devolvían patrones de
investigación clínica. Con `--todas-las-escuelas` se guarda todo (solo para análisis;
la aplicación filtra igualmente al cargar).

Tarda unos 6 minutos y es reanudable con `--reanudar`. No baja PDFs ni scrapea el sitio;
se descartan a propósito DNI, ORCID y jurados.

```bash
python -m scripts.indexar_titulos
```

Construye el índice vectorial en `chroma_db/titulos_upao/` (~15 s con el corpus acotado).
Se hace fuera de la API a propósito: embeber títulos dentro de una petición de chat
dejaría al estudiante esperando.

> Si ya tenías un índice construido con el repositorio completo, recompílalo con
> `python -m scripts.indexar_titulos --reconstruir`. Las búsquedas van contra Chroma, no
> contra el JSONL, así que un índice viejo seguiría trayendo tesis de otras facultades.
> La búsqueda las descarta de todos modos y lo avisa en el log, pero pierdes resultados.

El sistema **degrada en silencio**: si el corpus no está cosechado, el panel de
título sigue funcionando con sus reglas, solo que sin la evidencia del repositorio.

De ese corpus salen dos cosas que antes el sistema no tenía:

- **Patrón real**: los títulos más cercanos al tema del estudiante, como referencia
  de forma (cómo nombran la institución, dónde colocan el periodo).
- **Evidencia de delimitación de la propia escuela**: qué porcentaje de las tesis de
  sistemas aprobadas nombra el lugar y cuál el año. Convierte «te falta delimitar» en un
  dato verificable: sobre las 160 tesis de sistemas desde 2020, el 68 % nombra el lugar o
  la institución, el 51 % incluye el año y solo el 38 % ambos, con una mediana de 21
  palabras. Ese es el listón real de su escuela, no el promedio de la universidad.

---

## Arrancar el proyecto

Necesitas **dos procesos**: la API (Python) y la interfaz (React). En desarrollo, Vite
enruta automáticamente las peticiones `/api` al backend.

```bash
# Terminal 1 — API FastAPI (desde la raíz del proyecto)
uvicorn api.main:app --reload --port 8080 --workers 1
```

```bash
# Terminal 2 — Interfaz React
cd web
npm install        # solo la primera vez
npm run dev
```

La interfaz arranca en `http://localhost:5173` y la API en `http://localhost:8080`.

> **Un solo `--workers 1`:** el vector store de cada tesis vive en memoria del proceso, así que
> solo puede haber una revisión activa por instancia (lock interno). No subas el número de workers.

**Primera ejecución de la API (puede tardar 2-3 minutos):**
- Descarga y cachea el modelo de embeddings HuggingFace
- Compila el grafo LangGraph
- Indexa los libros de la carpeta `books/` en ChromaDB persistente

**Ejecuciones siguientes:** arranque en ~5 segundos (los singletons se cachean en `api/deps.py`).

---

## Estructura del proyecto

```
poc_langgraph_mentoria/
│
├── web/                               # Interfaz React (Vite + Tailwind, estética iOS)
│   ├── src/
│   │   ├── pages/                     # Landing, Auth (login Supabase), Chat
│   │   │   ├── components/chat/           # ChatInput, AdjuntoChip, AlcanceSelector, MessageBubble…
│   │   ├── components/ui/             # Primitivas shadcn (button, textarea)
│   │   └── lib/                       # api.ts (SSE), supabase.ts, utils
│   ├── .env.example                   # VITE_API_URL + credenciales Supabase
│   └── package.json
│
├── api/                               # API FastAPI — backend de la interfaz React
│   ├── main.py                        # Endpoints: documentos, alcance, fragmento, chat, SSE
│   ├── deps.py                        # Singletons cacheados (grafo, embeddings, biblioteca)
│   ├── grafo.py                       # Adaptador del grafo LangGraph para la API
│   ├── registry.py                    # Registro en memoria de vector stores por tesis
│   ├── auth.py                        # Validación del token Supabase
│   └── full_review.py                 # Revisión completa en 3 fases (anti token-burn)
│
├── supabase/
│   ├── schema.sql                     # Tablas conversaciones + mensajes (historial por usuario)
│   └── schema_v7.sql                  # doc_alcance: qué partes pidió evaluar el estudiante
│
├── backend/
│   ├── config.py                      # Rúbrica UPAO (33 ítems), secciones, dependencias cruzadas
│   ├── alcance.py                     # Alcance declarado: qué se califica y qué no resta
│   ├── programas.py                   # Escuela objetivo: solo Ing. de Sistemas / Computacion y Sistemas
│   │
│   ├── ingesta/                       # Entrada única de documentos (PDF, Word, texto, Google Docs)
│   │   ├── __init__.py                # Router por firma binaria → DocumentoExtraido
│   │   ├── pdf.py                     # Cascada pdfium → pdfplumber → pdfminer, página a página
│   │   ├── word.py                    # .docx con estilos de encabezado y tablas
│   │   ├── texto_plano.py             # .txt/.md y texto pegado, con detección de encoding
│   │   ├── gdocs.py                   # Google Doc compartido → export .docx
│   │   └── calidad.py                 # Detecta mojibake/páginas vacías y decide si seguir la cascada
│   │
│   ├── graph/
│   │   ├── state.py                   # MentoriaState (TypedDict) — estado compartido de la red
│   │   ├── workflow.py                # Compilación del StateGraph — topología de red
│   │   ├── edges.py                   # routing_supervisor: lee state["siguiente_nodo"]
│   │   └── nodes/
│   │       ├── supervisor.py          # Orquestador LLM: decide el siguiente agente (DecisionSupervisor)
│   │       ├── redactor.py            # Mejora el texto académico con RAG + feedback
│   │       ├── auditor.py             # Evalúa rúbrica 33 ítems (AuditorOutput Pydantic)
│   │       ├── metodologico.py        # Rigor científico + coherencia cruzada entre secciones
│   │       ├── debate.py              # Debate argumentativo Redactor ↔ Evaluadores (Pydantic)
│   │       ├── human.py               # Nodo HITL — registra la decisión del mentor
│   │       └── _utils.py              # cargar_prompt(), invocar_con_backoff() (anti-429)
│   │
│   ├── prompts/                       # Prompts en Markdown — editables sin tocar código
│   │   ├── supervisor_red_prompt.md   # Prompt del Supervisor Orquestador (routing dinámico)
│   │   ├── redactor_prompt.md         # Prompt del Redactor (estructura UPAO + reglas de lenguaje)
│   │   ├── auditor_prompt.md          # Prompt del Auditor (rúbrica completa + instrucciones)
│   │   ├── metodologico_prompt.md     # Prompt del Metodólogo (rigor + coherencia cruzada)
│   │   ├── debate_redactor_prompt.md  # Prompt para el Redactor en ronda de debate
│   │   └── debate_evaluadores_prompt.md # Prompt para los Evaluadores en ronda de debate
│   │
│   ├── titulo.py                      # Politica de delimitacion del titulo + diagnostico determinista
│   ├── citas.py                       # Vigencia de las fuentes (3 anios recomendado / 5 maximo)
│   ├── verificaciones.py              # Hechos medidos que se inyectan a los agentes ya resueltos
│   │
│   └── rag/
│       ├── embeddings.py              # Singleton HuggingFaceEmbeddings (multilingual-e5-small)
│       ├── estructura.py              # Cascada que resuelve las secciones del proyecto
│       ├── extractor.py               # Extraccion legacy de PDFs (la nueva vive en ingesta/)
│       ├── tesis_store.py             # ChromaDB EphemeralClient — tesis del estudiante (por sesion)
│       ├── library_store.py           # ChromaDB PersistentClient — biblioteca de libros
│       └── titulos_store.py           # Corpus de titulos UPAO: busqueda + estadistica de delimitacion
│
├── scripts/
│   ├── cosechar_titulos_upao.py       # Cosecha OAI-PMH del repositorio institucional
│   └── indexar_titulos.py             # Construye el indice vectorial del corpus (una vez)
│
├── data/                              # Corpus cosechado (generado; ver seccion del corpus)
│   ├── titulos_upao.jsonl             # ~270 tesis de la escuela de sistemas (filtrado)
│   └── titulos_upao_sets.json         # Mapa de comunidades y colecciones del repositorio
│
├── books/                             # PDFs de libros de metodologia (pre-carga automatica)
│   └── *.pdf
│
├── chroma_db/                         # ChromaDB persistente (generado automaticamente)
│   ├── biblioteca/                    # Indice vectorial de los libros
│   └── titulos_upao/                  # Indice vectorial del corpus de titulos
│
├── .env                               # Variables de entorno (NO subir a git)
├── .env.example                       # Plantilla de variables de entorno
├── .gitignore
└── requirements.txt
```

---

## Cómo usar el sistema

### Flujo completo

```
[1] Iniciar sesión  →  [2] Subir PDF  →  [3] Pedir la revisión en el chat
      →  [4] Ver el progreso en vivo  →  [5] Recibir informe + texto mejorado
```

### Paso a paso

**1. Iniciar sesión**
- Con Supabase configurado, la app abre la landing y el formulario de **iniciar sesión / crear cuenta**.
- Sin Supabase configurado, la app entra en **modo invitado** y salta directo al chat (sin guardar historial).

**2. Entregar el proyecto**
- Arrastra o selecciona el archivo: **PDF, Word (.docx), .txt o .md**.
- O **pega el texto** directamente en el chat: si supera ~1 500 caracteres o 15 líneas se adjunta como
  un chip `TXT` (con vista previa) en vez de volcarse en la conversación, y se indexa igual.
- O importa un **Google Doc** compartido como «cualquiera con el enlace»; se exporta a .docx y entra
  por la misma tubería que un Word, conservando sus encabezados.
- El sistema extrae el texto, resuelve la estructura y construye un ChromaDB efímero (en memoria).
- Si ya hay un proyecto cargado, el texto pegado no lo pisa: se ubica en su sección y se guarda como
  versión de trabajo, y al evaluar se te pregunta cuál usar.

**2b. Elegir qué evaluar (alcance)**
- Al terminar la indexación aparece **«¿Qué parte de tu proyecto quieres que evalúe?»** con los 7
  grupos de la rúbrica, premarcados según lo que ya tienes redactado.
- Lo que dejes fuera no se califica y **no te resta**: la nota se informa sobre lo entregado, junto al
  avance real («7 de 33 ítems»), para no confundirla con la nota de sustentación.
- Se cambia cuando quieras con el botón **Alcance** de la cabecera del chat.

**3. Pedir la revisión en el chat**
- Escribe en lenguaje natural: «revisa mis objetivos», «evalúa todo el proyecto», o usa las acciones rápidas.
- Ajusta la **profundidad** (Rápido / Equilibrado / Profundo) según cuántas iteraciones quieras.
- El Supervisor LLM decide qué agentes intervienen; para "todo el proyecto" se ejecuta la revisión en 3 fases anti token-burn.

**4. La red multiagente trabaja (en vivo)**

El progreso se transmite por SSE y se ve paso a paso en el chat. El Supervisor orquesta el flujo dinámicamente:

```
Supervisor → Redactor (genera versión mejorada)
Supervisor → Auditor  (evalúa rúbrica 33 ítems)
Supervisor → Metodólogo (rigor científico + coherencia)
Supervisor → Debate   (Redactor argumenta ↔ Evaluadores responden)
Supervisor → Redactor (nueva iteración si quedan errores)
     ...
Supervisor → Humano   (cuando el texto está listo o se alcanza el límite)
```

**5. Informe y texto mejorado**
- El chat muestra el **informe** con los puntos débiles priorizados y la síntesis del debate.
- Puedes abrir el **análisis detallado** por sección y, cuando el sistema propone texto corregido, decidir si lo incorpora a su memoria para las siguientes revisiones.
- Con Supabase activo, toda la conversación queda guardada en tu cuenta y la puedes retomar desde la barra lateral.

---

## Agentes y sus roles

| Agente | Archivo | Modelo | Rol |
|---|---|---|---|
| **Supervisor** | `nodes/supervisor.py` | `llama-3.3-70b` temp=0.2 | Orquestador: lee estado completo y decide el siguiente agente (routing dinámico) |
| **Redactor** | `nodes/redactor.py` | `llama-3.3-70b` temp=0.4 | Mejora el texto académico usando plan del Supervisor, feedback del Auditor, observaciones del Metodólogo y contexto RAG cruzado |
| **Auditor** | `nodes/auditor.py` | `llama-3.3-70b` temp=0.1 | Evalúa el texto contra los 33 ítems de la rúbrica oficial UPAO (escala 0–3). Salida estructurada Pydantic `AuditorOutput` |
| **Metodólogo** | `nodes/metodologico.py` | `llama-3.3-70b` temp=0.2 | Evalúa el rigor científico y la coherencia entre secciones relacionadas del documento |
| **Debate** | `nodes/debate.py` | `llama-3.3-70b` temp=0.3 | Intercambio argumentativo: Redactor defiende sus decisiones, Evaluadores responden con veredicto Pydantic (`VeredictoEvaluadores`). Actualiza `errores_rubrica` aceptando o manteniendo cada ítem |

### Panel de título (`api/titulo_panel.py`)

El título tiene su propio panel porque juega con reglas que ninguna otra sección
tiene: límite duro de 20 palabras, delimitación espacio/tiempo **condicionada al tipo
de estudio**, y un corpus de referencia propio. Un solo modelo que propone y se
autoevalúa tiende a validar lo que acaba de escribir, así que cada rol trabaja sobre
evidencia que el anterior no controla:

| Agente | Rol |
|---|---|
| **Proponente** | Escribe 3 candidatos. Ve el proyecto por RAG, la política de delimitación de ESTE estudio y títulos reales del repositorio UPAO |
| **Verificador de anclaje** | No propone: comprueba que cada institución, año, población o técnica del título esté en el proyecto. Lo que no esté, lo marca como inventado |
| **Auditor** | Falla contra los ítems 1, 2 y 3 con el conteo de palabras y el diagnóstico de delimitación ya **medidos**. Puede devolver el trabajo al proponente una vez |

Entre agente y agente corre un chequeo determinista (`backend/titulo.py`): las
palabras se cuentan, no se opinan. Y cuando falta un dato — no se sabe la empresa, ni
el periodo — el panel entrega un marcador explícito `[institución]` y lo pide, en
lugar de rellenarlo con un nombre plausible.

### Reglas transversales verificadas (`backend/verificaciones.py`)

Dos comprobaciones que un LLM hace mal por naturaleza se resuelven fuera del modelo y
se le entregan resueltas al auditor del grafo, al barrido de la revisión completa y al
debate rápido:

- **Delimitación del título** (`backend/titulo.py`) — el ítem 2 pide «variables,
  espacio y tiempo», pero leerlo como «siempre lugar y año» produce títulos falsos. La
  política decide si cada delimitación es EXIGIDA, RECOMENDADA u OPCIONAL según el
  tipo, el diseño y el origen de los datos: un modelo entrenado sobre un dataset
  público no se delimita por año; una encuesta a los trabajadores de una empresa, sí.
- **Vigencia de las fuentes** (`backend/citas.py`) — se recomienda que las citas no
  pasen de **3 años** y no deberían superar los **5**. Se cuentan los años reales de
  las citas del texto y se clasifican, con la excepción explícita de obras seminales,
  textos de metodología, normas técnicas y legislación, que no se penalizan por fecha.

---

## Documentación funcional de nodos

| Nodo | Archivo | Funcionalidad |
|---|---|---|
| `nodo_supervisor` | `nodes/supervisor.py` | Orquesta la red leyendo el estado completo y decidiendo determinísticamente qué agente ejecutar a continuación, con protección anti-bucle por contador de pasos. |
| `nodo_redactor` | `nodes/redactor.py` | Reescribe el texto académico de la sección integrando el plan del supervisor, el feedback del auditor, las observaciones del metodólogo y contexto recuperado por RAG. |
| `nodo_auditor` | `nodes/auditor.py` | Evalúa el texto ítem por ítem contra la rúbrica UPAO de 33 criterios (escala 0–3) y emite una lista de errores bloqueantes con puntuación total. |
| `nodo_metodologico` | `nodes/metodologico.py` | Analiza el rigor científico del texto y su coherencia con las secciones dependientes del documento (variables, hipótesis, diseño, instrumentos). |
| `nodo_consenso` | `nodes/consenso.py` | Sintetiza los puntos de acuerdo entre el Auditor y el Metodólogo para identificar los errores compartidos más críticos antes del debate. |
| `nodo_disenso` | `nodes/disenso.py` | Detecta las contradicciones entre las evaluaciones del Auditor y el Metodólogo y propone cómo resolverlas antes de que el Redactor intervenga. |
| `nodo_debate` | `nodes/debate.py` | Ejecuta una ronda argumentativa en la que el Redactor defiende sus decisiones y los Evaluadores emiten un veredicto estructurado que puede cerrar errores o mantenerlos. |
| `nodo_humano` | `nodes/human.py` | Pausa el grafo para que el mentor revise, edite y apruebe o rechace el texto final, y genera los reportes de métricas y transcript de debate al aprobar. |

### Estado compartido (`MentoriaState`)

Todos los agentes leen y escriben en un `TypedDict` centralizado con persistencia via `MemorySaver`:

```python
MentoriaState:
  # Contexto de entrada
  seccion_objetivo, contexto_recuperado, contexto_dependencias, contexto_teorico

  # Control de ciclos
  max_iteraciones, max_rondas_debate

  # Routing de red (nuevo en v3)
  siguiente_nodo        # el Supervisor escribe aquí su decisión
  pasos_ejecutados      # contador anti-bucle
  max_pasos_red         # techo calculado automáticamente
  iter_auditada         # el Supervisor sabe si el Auditor ya corrió esta iteración
  iter_metodologica     # ídem para el Metodólogo

  # Agentes
  plan_supervisor, texto_iterado, numero_iteracion
  feedback_auditor, errores_rubrica, puntaje_estimado
  observaciones_metodologicas
  ronda_debate, historial_debate, veredicto_debate

  # HITL
  aprobacion_humana
```

---

## Reglas de consenso y disenso entre agentes

Después de que el **Auditor** y el **Metodólogo** completan sus evaluaciones en cada ciclo, el Supervisor activa obligatoriamente dos nodos de arbitraje antes de pasar al debate: **Consenso** (Fase 3) y **Disenso** (Fase 4). Ambos reciben las mismas entradas y producen síntesis complementarias que informan al Supervisor y al nodo Debate.

### Cuándo se activan

```
Ciclo N:
  Fase 1 → Auditor       (evalúa rúbrica 33 ítems)
  Fase 2 → Metodólogo    (evalúa rigor y coherencia cruzada)
  Fase 3 → Consenso      (obligatorio: sintetiza acuerdos)
  Fase 4 → Disenso       (obligatorio: sintetiza conflictos)
  Fase 5 → Debate        (si hay errores y rondas disponibles)
  Fase 6 → Redactor      (aplica correcciones al texto)
  Fase 7 → Humano        (si 0 errores o ciclos agotados)
```

El Supervisor detecta si cada fase ya corrió en el ciclo actual comparando el contador `iter_xxx` con `numero_iteracion`. Si `iter_consenso > numero_iteracion`, el Consenso ya corrió y se pasa al Disenso, y así sucesivamente.

---

### Nodo Consenso — Reglas de análisis

Recibe: `feedback_auditor` + `observaciones_metodologicas` + `texto_iterado`

Analiza cuatro dimensiones:

| Dimensión | Qué busca |
|---|---|
| **Acuerdos explícitos** | Aspectos que **ambos** agentes señalan como problemáticos o correctos, usando los mismos términos. |
| **Convergencia temática** | Aunque usen términos distintos, ¿apuntan al mismo problema de fondo? (ej. Auditor dice "sin hipótesis formal", Metodólogo dice "relación causal no establecida"). |
| **Fortalezas consensuadas** | Aspectos que ambos reconocen como bien logrados — no se tocan en el debate. |
| **Prioridad de corrección** | El error más crítico según los dos evaluadores, expresado en una sola oración accionable para el Redactor. |

Salida → `resultado_consenso`: narrativa estructurada con secciones `ACUERDOS DETECTADOS`, `FORTALEZAS CONSENSUADAS` y `PRIORIDAD DE CORRECCIÓN CONSENSUADA`.

---

### Nodo Disenso — Reglas de análisis

Recibe: `feedback_auditor` + `observaciones_metodologicas` + `texto_iterado` + `n_errores`

Analiza cuatro dimensiones:

| Dimensión | Qué busca |
|---|---|
| **Conflictos directos** | Ítems donde uno aprueba y el otro rechaza, o donde sus recomendaciones son contradictorias. |
| **Divergencia de enfoque** | El Auditor prioriza formato/estructura (rúbrica formal); el Metodólogo prioriza rigor lógico. Detecta tensión entre ambas prioridades. |
| **Brechas de evaluación** | Aspectos que solo uno de los dos agentes evaluó — zonas ciegas de la evaluación. |
| **Recomendación para el Supervisor** | En 1-2 oraciones: qué criterio (formal o metodológico) debe pesar más para esta sección específica y por qué. |

Salida → `resultado_disenso`: narrativa estructurada con secciones `CONFLICTOS DETECTADOS`, `BRECHAS DE EVALUACIÓN` y `RECOMENDACIÓN PARA EL SUPERVISOR`.

---

### Cómo usan sus salidas los nodos siguientes

```
Consenso + Disenso
       │
       ├──→ Debate (nodo_debate)
       │      ├─ Redactor usa: errores_rubrica (filtrados por el consenso como críticos)
       │      │                contexto_teorico, historial_debate anterior
       │      └─ Evaluadores usan: feedback_auditor + observaciones_metodologicas
       │
       └──→ Supervisor (fallback LLM)
              └─ resultado_consenso + resultado_disenso como campos del estado
                 para informar el routing cuando no aplica ninguna fase determinista
```

**El Consenso no modifica `errores_rubrica` directamente** — solo prioriza. Los errores se eliminan únicamente cuando el nodo Debate emite un veredicto `"aceptado"` para un ítem.

---

### Reglas del Debate (mecanismo de resolución de errores)

El debate es la única instancia donde un error bloqueante puede cerrarse sin que el Redactor reescriba el texto:

| Paso | Quién actúa | Qué hace |
|---|---|---|
| **1. Argumento** | Redactor | Para cada crítica: acepta (con corrección propuesta en texto), cuestiona (señala dónde ya está en el texto) o propone alternativa (con texto concreto). |
| **2. Veredicto** | Panel evaluador (Auditor + Metodólogo, llamada conjunta) | Emite `"aceptado"` o `"mantenido"` por cada ítem con razón explícita. |
| **3. Actualización** | `nodo_debate` (código) | Elimina de `errores_rubrica` los ítems con veredicto `"aceptado"`. |

**Reglas del veredicto (hardcodeadas en el prompt de evaluadores):**
1. Se acepta si el Redactor demuestra que el elemento ya está presente en el texto con referencia concreta.
2. Se mantiene si la crítica está sustentada en la rúbrica UPAO o en principios metodológicos sólidos.
3. Si el argumento es parcialmente válido → se mantiene el error pero se reconoce el punto válido.
4. La coherencia cruzada entre secciones es **no negociable** — si hay incoherencia real, no se acepta el argumento.

---

## Sistema RAG Dual

El sistema usa **dos instancias de ChromaDB independientes**:

| Instancia | Tipo | Contenido | Ciclo de vida |
|---|---|---|---|
| **Tesis** | `EphemeralClient` (en memoria) | PDF del estudiante actual | Por sesión — se destruye al reiniciar |
| **Biblioteca** | `PersistentClient` (en disco) | PDFs de libros de metodología | Permanente — sobrevive reinicios |

### Embeddings

Modelo: `sentence-transformers/all-MiniLM-L6-v2`
- Se ejecuta **localmente en CPU** (sin costo, sin latencia de API)
- Se descarga automáticamente en la primera ejecución (~80 MB)
- Se carga una sola vez como singleton de proceso (`api/deps.py`) y se reutiliza en todas las peticiones

### RAG Cruzado entre Secciones

Antes de invocar el grafo, el sistema consulta `DEPENDENCIAS_SECCIONES` (definido en `config.py`) para recuperar contexto de secciones relacionadas. Por ejemplo, al evaluar "Título del proyecto" también recupera fragmentos de Objetivos, Variables, Hipótesis y Marco Metodológico — garantizando que el Redactor y el Auditor detecten incoherencias entre secciones.

---

## Protección Anti-Bucle

El sistema tiene **dos capas independientes** para evitar bucles infinitos:

### Capa 1 — Semántica (Supervisor)
```python
max_pasos_red = max_iteraciones × (4 + max_rondas_debate) + 3
# Ejemplo: 3 iter × (4 + 2) + 3 = 21 pasos máximos

if pasos_ejecutados >= max_pasos_red:
    # El Supervisor fuerza "humano" sin llamar al LLM
    return {"siguiente_nodo": "humano", ...}
```

### Capa 2 — Sistémica (LangGraph)
```python
RECURSION_LIMIT = 60  # en workflow.py
# LangGraph lanza GraphRecursionError si se superan 60 supersteps
```

Con configuración por defecto (3 iteraciones, 2 rondas de debate):
- Pasos máximos semánticos: **21**
- Supersteps máximos de LangGraph: **60**
- Hay ~40 supersteps de margen antes de que LangGraph corte

---

## Variables de entorno

| Variable | Requerida | Descripción |
|---|---|---|
| `GROQ_KEY_SUPERVISOR` | Recomendada | Clave Groq exclusiva para el Supervisor |
| `GROQ_KEY_REDACTOR` | Recomendada | Clave Groq exclusiva para el Redactor |
| `GROQ_KEY_AUDITOR` | Recomendada | Clave Groq exclusiva para el Auditor |
| `GROQ_KEY_METODOLOGICO` | Recomendada | Clave Groq exclusiva para el Metodólogo |
| `GROQ_API_KEY` | Sí (fallback) | Si no se definen las claves individuales, todos los agentes usan esta |
| `LANGCHAIN_TRACING_V2` | Opcional | `true` para activar tracing con LangSmith |
| `LANGCHAIN_API_KEY` | Opcional | Clave de LangSmith para tracing |
| `LANGCHAIN_PROJECT` | Opcional | Nombre del proyecto en LangSmith |

---

## Notas de desarrollo

### Modificar prompts sin tocar código

Todos los prompts están en `backend/prompts/*.md` como archivos Markdown independientes. Edítalos directamente y recarga el servidor — no es necesario modificar ningún archivo `.py`.

### Añadir nuevas secciones de tesis

Edita `backend/config.py`:
1. Agrega la sección a `SECCIONES_TESIS` con su `nombre` y `query`
2. Agrega los ítems UPAO correspondientes a `SECCION_ITEMS_MAP`
3. (Opcional) Define dependencias cruzadas en `DEPENDENCIAS_SECCIONES`

### Cambiar el modelo LLM

En `backend/graph/workflow.py`, cambia el modelo en la función `_llm()`:

```python
return ChatGroq(
    api_key=api_key,
    model="llama-3.3-70b-versatile",  # ← cambia aquí
    ...
)
```

Modelos compatibles con Groq: `llama-3.3-70b-versatile`, `llama-3.1-8b-instant`, `mixtral-8x7b-32768`, entre otros.

### Tracing con LangSmith

Para trazabilidad completa de cada llamada al LLM, activa LangSmith en `.env`:

```env
LANGCHAIN_TRACING_V2=true
LANGCHAIN_API_KEY=ls__xxxxxxxxxxxxxxxx
LANGCHAIN_PROJECT=mentoria-upao
```

### Rate limits de Groq (API gratuita)

| Límite | Por clave | Con 4 claves |
|---|---|---|
| Tokens por minuto (TPM) | 6.000 | ~24.000 |
| Tokens por día (TPD) | 500.000 | ~2.000.000 |
| Requests por minuto (RPM) | 30 | ~120 |

El sistema incluye `invocar_con_backoff()` en `nodes/_utils.py` con reintentos exponenciales (5s × 2^intento + jitter) ante errores 429.

---

## Licencia

Proyecto académico desarrollado como prueba de concepto (PoC) para la **Universidad Privada Antenor Orrego (UPAO)**, Facultad de Ingeniería. Uso educativo y de investigación.
