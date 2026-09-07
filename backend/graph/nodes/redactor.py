"""
Nodo Redactor — 2 modos según el puntaje de la sección.

1. Si el puntaje es > 90% del máximo posible → modo PULIDO (Pulidor):
   - El texto ya está bien; NO se reescribe ni se cambia estructura/contenido.
   - Se aplican solo retoques FINOS (puntuación, tildes, claridad, palabra exacta) y se
     devuelve el texto pulido + la lista de qué se retocó (en las recomendaciones).

2. Si el puntaje es <= 90% del máximo posible → modo ESCRITURA (Escritor):
   - Reescribe y mejora el texto base, cerrando la brecha hacia la meta de la rúbrica.
   - Devuelve `texto_redactado` (limpio, calificable) + `recomendaciones` (lo que no debe
     forzarse en el texto: incongruencias de enfoque/diseño, coherencia con otras secciones).

Nota: la EVALUACIÓN contra la rúbrica la realiza el nodo Auditor, no el redactor.
"""

import logging
import os
import re
import unicodedata

from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field

from backend.reglas_seccion import es_seccion_de_fuentes, reglas_de_nucleo, reglas_para
from ..state import MentoriaState
from ._utils import invocar_con_backoff
from ._rag_planner import obtener_contexto_dinamico

logger = logging.getLogger(__name__)

_UMBRAL_EXCELENCIA = 0.90


class RedaccionSeccion(BaseModel):
    """Dos entregables separados del Subagente Escritor.

    Solo `texto_redactado` se califica (auditor + juez LLM). Las `recomendaciones`
    orientan al estudiante pero NO se evalúan, por eso van fuera del texto.
    """
    texto_redactado: str = Field(
        description=(
            "Versión mejorada de SOLO la sección pedida, lista para entregar. "
            "Sin avisos, notas ni advertencias dentro: solo el texto de la tesis."
        )
    )
    recomendaciones: str = Field(
        default="",
        description=(
            "Observaciones que NO van dentro del texto: incongruencias con el enfoque/diseño, "
            "problemas metodológicos o de coherencia con otras secciones, redactadas como "
            "sugerencias accionables. Cadena vacía si no hay nada que observar."
        ),
    )

_PROMPT_ESCRITOR = """
Eres un asesor académico experto en redacción de tesis de pregrado en Ingeniería.
Tu tarea tiene DOS entregables SEPARADOS para la sección indicada:

1) `texto_redactado`: la versión mejorada de **solo la sección pedida**, lista para entregar.
2) `recomendaciones`: observaciones que NO van dentro del texto (incongruencias, problemas
   metodológicos o de coherencia con otras secciones), redactadas como sugerencias.

POR QUÉ SEPARADOS: lo único que se califica es `texto_redactado`. Las `recomendaciones`
orientan al estudiante pero no se evalúan, así que NUNCA mezcles avisos, notas, advertencias
ni «(sugerencia: …)» dentro de `texto_redactado`.

REGLAS PARA `texto_redactado`:
- Respeta el ENFOQUE del proyecto (tipo y diseño). NO impongas estructuras de otro enfoque.
- NO FUERCES elementos que el tipo/diseño no requiere:
  * No agregues hipótesis si el enfoque no las exige, ni hipótesis a un objetivo específico que no las necesita.
  * Si el diseño pide hipótesis cuantitativas Y cualitativas y solo hay de un tipo, NO inventes las faltantes dentro del texto.
  * Si el tipo no contempla operacionalización de variables (p. ej. cualitativa, tecnológica), no la agregues.
- Si el estudiante TIENE algo que NO corresponde a su enfoque (p. ej. hipótesis estadísticas en
  un estudio cualitativo, hipótesis en un objetivo específico que no las requiere), NO lo borres
  ni lo "arregles" a la fuerza dentro del texto: déjalo y explica el problema en `recomendaciones`.
- FIDELIDAD FACTUAL (obligatoria): NO cambies ni inventes datos del proyecto: cifras, años,
  tamaños de muestra/población, fórmulas, ESCALAS de medición ni instrumentos declarados
  (si el instrumento es la «rúbrica oficial del curso», NO lo conviertas en «Likert» ni en
  «puntajes del 1 al 5»; si la escala es 0-3, sigue siendo 0-3). Si necesitas un dato que no
  está en el original ni en el contexto, usa `[COMPLETAR: …]` en vez de inventarlo.
- NO ELIMINES contenido correcto al reescribir: conserva TODAS las dimensiones, indicadores,
  ítems y CITAS (Autor, año) del texto original. Puedes reordenarlos, precisarlos o corregirlos,
  nunca omitirlos; si crees que algo sobra, dilo en `recomendaciones`, no lo borres.
- Usa el contexto RAG para corregir vacíos REALES señalados por el panel (antecedentes, datos,
  referencias de otras secciones del proyecto). Si falta un dato, usa marcadores como
  `[INSERTAR DATO ESTADÍSTICO ACÁ]` o redacta de forma cualitativa con base en la realidad del proyecto.
- Mantén el registro académico formal y respeta la numeración y estructura de la sección.
- OPERACIONALIZACIÓN DE VARIABLES: es una tabla ANCHA (variable, definición conceptual, definición
  operacional, dimensiones, indicadores, ítems, escala) que se ROMPE en el chat. NUNCA la pongas como
  tabla ni copies la tabla cruda del PDF (con tabulaciones). Preséntala SIEMPRE como LISTA con viñetas
  anidadas, con EXACTAMENTE el MISMO formato para TODAS las variables (no una en tabla y otra en lista):
    - **Variable independiente: <nombre>**
      - Definición conceptual: …
      - Definición operacional: …
      - Dimensiones: …
      - Indicadores: …
      - Ítems: …
      - Escala de medición: …
    - **Variable dependiente: <nombre>**
      - (las mismas sub-viñetas)
- OTRAS TABLAS: si de verdad necesitas una y es angosta, hazla en Markdown GFM VÁLIDO (fila de
  encabezado + fila separadora `|---|---|` + filas con el MISMO número de columnas y celdas, sin
  mezclar tabulaciones con pipes); si tendría muchas columnas, usa la lista con viñetas anidadas.
- Solo si el enfoque es CUANTITATIVO, para el OBJETIVO GENERAL usa la forma:
  [verbo infinitivo] + [variable independiente] + "en" + [variable dependiente] + "de" +
  [unidad de análisis] + "en" + [horizonte temporal]; los específicos derivan de él, cada uno en
  una oración independiente. Para OTROS enfoques, respeta la forma propia de su tipo y NO impongas
  variables ni medición que su enfoque no contempla.

REGLAS PARA `recomendaciones`:
- Español, como sugerencias accionables (no como texto de tesis).
- Aquí va lo que NO cuadra con el enfoque/diseño, las incongruencias de trazabilidad señaladas por
  el metodólogo y cualquier problema de coherencia con otras secciones.
- Si no hay nada que observar, deja la cadena vacía.
"""

_PROMPT_PULIDOR = """
Eres un asesor académico experto en tesis de Ingeniería de pregrado.
La sección del estudiante YA alcanzó una calidad excelente (>90% de la rúbrica): su contenido,
estructura, argumentos, datos y enfoque son correctos. NO la reescribas: NO cambies su estructura,
ideas, argumentos, datos ni significado, ni expandas el texto.

Tu tarea es aplicar ÚNICAMENTE retoques FINOS de FORMA: puntuación, tildes/ortografía,
concordancia, claridad de alguna frase puntual o una palabra más precisa. Cambios mínimos y
locales, jamás estructurales ni de contenido.

Devuelve DOS campos:
- `texto_redactado`: la MISMA sección con esos retoques mínimos ya aplicados (si no hay nada que
  retocar, devuélvela idéntica). Solo el texto de la tesis, sin notas ni marcas dentro.
- `recomendaciones`: en español, di que el texto YA estaba correcto y LISTA exactamente qué
  retoques aplicaste y dónde (p. ej. «coma añadida tras "…"», «tilde en "análisis"»,
  «se precisó "hacer" por "implementar"»). Si no aplicaste ninguno, dilo explícitamente.
"""

def make_nodo_redactor(llm: ChatOpenAI):
    """Construye el Nodo Redactor con 3 subagentes."""
    model_name = getattr(llm, "model_name", "gpt-4o-mini")

    def nodo_redactor(state: MentoriaState) -> dict:
        iteracion_actual = state.get("numero_iteracion", 0) + 1
        universidad      = state.get("universidad", "upao")
        programa         = state.get("programa", "ingeniería de sistemas")
        seccion          = state["seccion_objetivo"]
        modo_nucleo      = bool(state.get("modo_nucleo"))
        from backend.rag import limpiar_marcas_rag
        texto_base       = limpiar_marcas_rag(state.get("texto_iterado") or state["contexto_recuperado"])

        historial_textos = list(state.get("historial_textos") or [])
        if not historial_textos:
            historial_textos.append(state.get("contexto_recuperado") or "")

        puntaje_estimado = float(state.get("puntaje_estimado") or 0.0)
        puntaje_max      = float(state.get("_puntaje_max") or 0.0)
        porcentaje       = (puntaje_estimado / puntaje_max) if puntaje_max > 0 else 0.0
        # En modo NÚCLEO siempre se ESCRIBE (su "puntaje" contra criterios genéricos no
        # es una nota real; entrar en pulido devolvería el contexto sin mejorar y se
        # saltaría el plan peso+margen).
        supera_umbral    = (porcentaje > _UMBRAL_EXCELENCIA) and not modo_nucleo

        universidad_l = str(universidad).lower()
        # El núcleo NO es la sección "título" aunque su nombre contenga la palabra.
        es_titulo = _es_seccion_titulo(seccion) and not modo_nucleo
        es_upao   = "upao" in universidad_l or "antenor orrego" in universidad_l

        logger.info(
            f"[Redactor] Iteración #{iteracion_actual} | {seccion} | "
            f"Puntaje: {puntaje_estimado}/{puntaje_max} ({porcentaje:.0%}) | "
            f"Modo: {'PULIDOR (Sub3)' if supera_umbral else 'ESCRITURA (Sub1+Sub2)'}"
        )

        if supera_umbral:
            prompt_pul = ChatPromptTemplate.from_messages([
                ("system", _PROMPT_PULIDOR),
                ("human", (
                    "Sección evaluada: **{seccion}** (iteración #{iteracion})\n\n"
                    "**PUNTAJE:** {puntaje_estimado}/{puntaje_max} ({porcentaje})\n\n"
                    "**FEEDBACK DEL AUDITOR:**\n{feedback_auditor}\n\n"
                    "**TEXTO ACTUAL DEL ESTUDIANTE:**\n{texto_actual}\n\n"
                    "Aplica los retoques mínimos y devuelve `texto_redactado` (texto pulido) "
                    "y `recomendaciones` (qué retocaste)."
                )),
            ])
            chain_pul = prompt_pul | llm.with_structured_output(RedaccionSeccion)

            try:
                output = invocar_con_backoff(chain_pul, {
                    "seccion":            seccion,
                    "iteracion":          iteracion_actual,
                    "puntaje_estimado":   int(puntaje_estimado),
                    "puntaje_max":        int(puntaje_max),
                    "porcentaje":         f"{porcentaje:.0%}",
                    "feedback_auditor":   state.get("feedback_auditor") or "Sin feedback específico.",
                    "texto_actual":       texto_base,
                })
                texto_final      = (output.texto_redactado or "").strip() or texto_base
                sugerencias_texto = (output.recomendaciones or "").strip() or (
                    f"Tu texto ya está en nivel ({porcentaje:.0%}); no hizo falta ningún retoque."
                )
            except Exception as exc:
                logger.warning(f"[Redactor/Pulidor] Falló: {exc} — usando fallback")
                texto_final = texto_base
                sugerencias_texto = (
                    f"Sección aprobada con excelente puntuación ({porcentaje:.0%}). "
                    f"No hay retoques de pulido adicionales."
                )

            # Aun en pulido, el título UPAO no puede exceder 20 palabras.
            if es_titulo and es_upao:
                n_pal = _palabras_titulo(texto_final)
                if n_pal > 20:
                    sugerencias_texto += (
                        f"\n\n**Atención:** el título tiene {n_pal} palabras; UPAO exige máximo 20 "
                        "(incluyendo conectores y fechas). Recórtalo conservando variables y unidad de análisis."
                    )

            notas_na = _notas_na_tipo(state)
            if notas_na:
                sugerencias_texto += "\n\n" + notas_na

            historial_textos.append(texto_final)

            return {
                "texto_iterado":                 texto_final,
                "numero_iteracion":              iteracion_actual,
                "loras_activas":                 ["redactor_pulidor"],
                "redactor_sugerencias_mejoras":  sugerencias_texto,
                "redactor_evaluacion_rubrica":   None,
                "redactor_solo_pulido":          True,
                "historial_textos":              historial_textos,
            }

        
        evaluacion_rubrica_dict = None


        logger.info("[Redactor] Subagente 1 ejecutando reescritura del texto...")
        
        from ._rubrica import criterios_para_seccion
        crit = criterios_para_seccion(state, seccion)
        criterios_str = crit["criterios_str"]

        from backend.enfoque import bloque_enfoque
        enfoque = bloque_enfoque(state.get("tipo_investigacion"), state.get("diseno"))

        # Paquete de coherencia: reusa el contexto que ya planificó el auditor en
        # esta iteración (mismo proyecto/sección) en vez de gastar otra llamada RAG.
        contexto_dinamico = state.get("contexto_coherencia") or obtener_contexto_dinamico(
            llm              = llm,
            seccion          = seccion,
            texto_snippet    = texto_base[:500],
            rol              = "redactor académico que mejora secciones de tesis de ingeniería",
            criterios        = criterios_str,
            feedback_auditor = state.get("feedback_auditor") or state.get("observaciones_metodologicas") or "",
        )

        # Brecha hacia la meta: aunque no queden "errores", si el puntaje sigue por
        # debajo del objetivo el redactor debe empujar los ítems al máximo.
        import math
        meta            = float(state.get("meta_aprobacion") or 0.90)
        meta_pts        = math.ceil(puntaje_max * meta) if puntaje_max else 0
        items_mejorables = state.get("items_mejorables") or []
        if items_mejorables:
            brecha_items = "\n".join(
                f"- Ítem {it.get('item_numero', '?')}: actualmente en {it.get('puntaje', '?')} "
                f"(debe llegar al máximo) — {it.get('observacion', '')}"
                for it in items_mejorables
            )
        else:
            brecha_items = "Sin ítems puntuales pendientes; eleva la calidad y completitud general."
        brecha_meta = (
            f"Puntaje actual: {int(puntaje_estimado)}/{int(puntaje_max)}; meta: {meta_pts}/{int(puntaje_max)} "
            f"({meta:.0%}). Ítems aún por debajo del máximo:\n{brecha_items}\n"
            "Cierra EXACTAMENTE esa brecha en esta versión; no te quedes en el mismo nivel de la iteración anterior."
        )

        # Modo NÚCLEO: el redactor trabaja el esqueleto de coherencia en una sola pasada.
        # Solo REESCRIBE (texto mejorado) los subpuntos prioritarios (peso en la rúbrica +
        # margen de mejora); para el RESTO entrega solo una OBSERVACIÓN del porqué de su nota.
        if state.get("modo_nucleo"):
            instruccion_nucleo = _instruccion_nucleo(state.get("nucleo_plan"))
        else:
            instruccion_nucleo = "—"

        # Reglas del título. El límite de palabras no basta: lo que fallaba era la
        # DELIMITACIÓN (variables · espacio · tiempo del ítem 2), que no es la misma
        # para todos los estudios. `bloque_regla_titulo` la decide según el tipo, el
        # diseño y el origen de los datos, y añade el diagnóstico medido del título actual.
        if es_titulo:
            from backend.titulo import bloque_regla_titulo
            contexto_proyecto = " ".join(filter(None, [
                (contexto_dinamico or "")[:2500],
                (state.get("contexto_dependencias") or "")[:1500],
                texto_base[:1500],
            ]))
            regla_titulo = bloque_regla_titulo(
                tipo_investigacion=state.get("tipo_investigacion"),
                diseno=state.get("diseno"),
                contexto_proyecto=contexto_proyecto,
                universidad=universidad if es_upao else "",
                titulo_actual=texto_base,
            )
        else:
            regla_titulo = ""

        # Vigencia de las fuentes: aplica a toda sección que cite (antecedentes, bases
        # teóricas, referencias), no solo al título.
        from backend.citas import analizar_vigencia, bloque_regla_citas
        regla_citas = bloque_regla_citas(diagnostico=analizar_vigencia(texto_base))

        historial_debate_lista = state.get("historial_debate") or []
        if historial_debate_lista:
            ultima = historial_debate_lista[-1]
            confirmados = ultima.get("items_confirmados", [])
            descartados = ultima.get("items_descartados", [])
            veredicto_debate = (
                f"Tras {len(historial_debate_lista)} ronda(s) de debate:\n"
                f"- Ítems confirmados como errores reales: {confirmados}\n"
                f"- Ítems descartados: {descartados}"
            )
        else:
            veredicto_debate = "No hubo debate previo en esta iteración."

        inputs_base = {
            "seccion":                  seccion,
            "iteracion":                iteracion_actual,
            "max_iteraciones":          state.get("max_iteraciones", 3),
            "contexto_recuperado":      state["contexto_recuperado"],
            "contexto_dependencias":    contexto_dinamico or state.get("contexto_dependencias") or "Sin contexto de secciones relacionadas.",
            "contexto_teorico":         state.get("contexto_teorico") or "",
            "texto_actual":             texto_base,
            "plan_supervisor":          state.get("plan_supervisor") or "Sin plan previo.",
            "feedback_auditor":         state.get("feedback_auditor") or "Primera iteración.",
            "observaciones_metodologicas": state.get("observaciones_metodologicas") or "",
            "veredicto_debate":         veredicto_debate,
            "errores_confirmados":      _formatear_errores(state.get("errores_rubrica") or []),
            "universidad":              universidad,
            "programa":                 programa,
            "perfil_institucional":     state.get("perfil_institucional") or "Sin lineamientos institucionales adicionales.",
            "enfoque":                  enfoque,
            "brecha_meta":              brecha_meta,
            "regla_titulo":             regla_titulo or "—",
            "regla_citas":              regla_citas,
            "instruccion_nucleo":       instruccion_nucleo,
            "contexto_secciones_relacionadas": "",
            # Reglas de dominio de ESTA sección, compartidas con los paneles de
            # asesoría. Sin esto el redactor contradecía al asesor: le reescribía
            # los antecedentes con citas inventadas después de que el panel le
            # hubiera explicado que eso es falta académica.
            # En modo núcleo la sección se llama «Núcleo de coherencia (título · …)»:
            # resolverla por nombre daba solo las reglas del título y dejaba la
            # operacionalización sin las suyas.
            "reglas_seccion": reglas_de_nucleo() if modo_nucleo else reglas_para(seccion),
            # Lo que el estudiante NO puso a revisión no se reescribe ni se le
            # reclama: reescribirlo sería ponerle palabras que no ha escrito.
            "alcance_declarado": state.get("alcance_declarado") or "",
        }

        prompt_esc = ChatPromptTemplate.from_messages([
            ("system", _PROMPT_ESCRITOR),
            ("human", (
                "{enfoque}\n\n"
                "Genera la versión mejorada del texto para la sección **{seccion}** (iteración #{iteracion}).\n\n"
                "**TEXTO ORIGINAL:**\n{texto_actual}\n\n"
                "**ERRORES CONFIRMADOS POR EL PANEL:**\n{errores_confirmados}\n\n"
                "**BRECHA HACIA LA META (cierra esto):**\n{brecha_meta}\n\n"
                "**MODO NÚCLEO:**\n{instruccion_nucleo}\n\n"
                "**ALCANCE DECLARADO:**\n{alcance_declarado}\n\n"
                "**REGLA DEL TÍTULO:**\n{regla_titulo}\n\n"
                "**VIGENCIA DE LAS FUENTES:**\n{regla_citas}\n\n"
                "**FEEDBACK METODOLÓGICO:**\n{observaciones_metodologicas}\n\n"
                "**CONTEXTO RAG DE LIBROS:**\n{contexto_teorico}\n\n"
                "**CONTEXTO DE OTRAS SECCIONES:**\n{contexto_dependencias}\n\n"
                "**LINEAMIENTOS DE LA UNIVERSIDAD (ajusta el estilo y exigencias a esto):**\n{perfil_institucional}\n\n"
                "Devuelve `texto_redactado` (solo la sección, limpia) y `recomendaciones` "
                "(lo que no cuadra con el enfoque o no debe forzarse en el texto)."
            )),
        ])
        chain_esc = prompt_esc | llm.with_structured_output(RedaccionSeccion)

        sugerencias_escritor = None
        try:
            output_esc = invocar_con_backoff(chain_esc, inputs_base)
            texto_final = (output_esc.texto_redactado or "").strip() or texto_base
            sugerencias_escritor = (output_esc.recomendaciones or "").strip() or None
        except Exception as exc:
            logger.warning(f"[Redactor/Escritor] Falló: {exc} — usando fallback")
            texto_final = texto_base

        # Red de seguridad del PLAN DEL NÚCLEO: se comprueba que el texto entregado
        # cubra lo que había que reescribir. Se observó al redactor saltarse el
        # título —el subpunto peor calificado— y en cambio "mejorar" los objetivos y
        # las hipótesis, que ya estaban en su máximo: el estudiante recibe cambios
        # que no necesita y sigue sin el arreglo que sí necesitaba.
        if modo_nucleo:
            faltantes = _subpuntos_omitidos(state.get("nucleo_plan"), texto_final)
            if faltantes:
                aviso = (
                    "Estos subpuntos debían reescribirse y no aparecen en el texto propuesto: "
                    + "; ".join(faltantes)
                    + ". Su nota original se mantiene: pide la revisión de nuevo o trabájalos aparte."
                )
                sugerencias_escritor = (
                    f"{sugerencias_escritor}\n\n{aviso}" if sugerencias_escritor else aviso
                )
                logger.warning(f"[Redactor/Núcleo] Subpuntos omitidos: {faltantes}")

        # Red de seguridad determinista de las FUENTES: al reescribir antecedentes o
        # marco teórico, el modelo tiende a "completar" con estudios que suenan
        # bien y no existen. Aquí se compara contra el texto original: toda cita
        # que no estuviera ya, se sustituye por un marcador. Una referencia
        # inventada en una tesis es falta académica, no un desliz de estilo.
        if es_seccion_de_fuentes(seccion):
            from api.antecedentes import citas_inventadas

            previas = set(citas_inventadas(texto_base))
            nuevas = citas_inventadas(texto_final, permitidas=previas)
            if nuevas:
                for cita in nuevas:
                    texto_final = texto_final.replace(
                        cita, "[antecedente pendiente: verifica esta fuente]"
                    )
                aviso = (
                    "Se detectaron y neutralizaron "
                    f"{len(nuevas)} referencia(s) que no estaban en tu texto original "
                    f"({', '.join(nuevas[:3])}). No las uses: búscalas y verifícalas tú antes de "
                    "incorporarlas."
                )
                sugerencias_escritor = (
                    f"{sugerencias_escritor}\n\n{aviso}" if sugerencias_escritor else aviso
                )
                logger.warning(
                    f"[Redactor] {len(nuevas)} cita(s) inventada(s) neutralizadas en «{seccion}»"
                )

        # Red de seguridad determinista del título: límite de palabras Y delimitación.
        # El LLM puede argumentar bien y aun así entregar un título de 24 palabras o sin
        # la unidad de análisis; esto se verifica fuera del modelo.
        if es_titulo and texto_final:
            avisos = _avisos_titulo(
                texto_final,
                tipo_investigacion=state.get("tipo_investigacion"),
                diseno=state.get("diseno"),
                contexto_proyecto=(state.get("contexto_dependencias") or "")[:2000],
                es_upao=es_upao,
            )
            if avisos:
                sugerencias_escritor = (
                    f"{sugerencias_escritor}\n\n{avisos}" if sugerencias_escritor else avisos
                )

        # Verificación de fidelidad (sin LLM): citas perdidas y escalas/instrumentos
        # inventados respecto al texto que se le dio a mejorar.
        aviso_fid = _verificar_fidelidad(texto_base, texto_final)
        if aviso_fid:
            sugerencias_escritor = (
                f"{sugerencias_escritor}\n\n{aviso_fid}" if sugerencias_escritor else aviso_fid
            )
            logger.info("[Redactor] Verificación de fidelidad con observaciones — aviso añadido")

        notas_na = _notas_na_tipo(state)
        if notas_na:
            sugerencias_escritor = (
                f"{sugerencias_escritor}\n\n{notas_na}" if sugerencias_escritor else notas_na
            )

        historial_textos.append(texto_final)

        return {
            "texto_iterado":                 texto_final,
            "numero_iteracion":              iteracion_actual,
            "loras_activas":                 ["redactor_escritor", "redactor_evaluador"],
            "redactor_sugerencias_mejoras":  sugerencias_escritor,
            "redactor_evaluacion_rubrica":   evaluacion_rubrica_dict,
            "redactor_solo_pulido":          False,
            "historial_textos":              historial_textos,
        }

    return nodo_redactor

def _es_seccion_titulo(seccion: str) -> bool:
    s = (seccion or "").lower()
    return "título" in s or "titulo" in s or "title" in s


def _palabras_titulo(texto: str) -> int:
    """Cuenta palabras del título, quitando una etiqueta inicial tipo «Título: …»."""
    from backend.titulo import contar_palabras_titulo
    return contar_palabras_titulo(texto)


def _avisos_titulo(
    texto: str,
    tipo_investigacion: str | None,
    diseno: str | None,
    contexto_proyecto: str,
    es_upao: bool,
) -> str:
    """Avisos VERIFICADOS sobre el título entregado: extensión y delimitación faltante.

    Se comprueba fuera del LLM porque son las dos cosas que el modelo daba por buenas
    con más frecuencia: entregaba títulos de más de 20 palabras y, sobre todo, títulos
    sin espacio ni tiempo en estudios que sí los exigían.
    """
    from backend.titulo import MAX_PALABRAS_UPAO, diagnosticar_titulo, politica_delimitacion

    diag = diagnosticar_titulo(texto)
    pol = politica_delimitacion(tipo_investigacion, diseno, contexto_proyecto)
    avisos: list[str] = []

    if es_upao and diag.excede_limite:
        avisos.append(
            f"**Atención:** el título propuesto tiene {diag.n_palabras} palabras; UPAO exige "
            f"máximo {MAX_PALABRAS_UPAO} (incluyendo conectores y fechas). Recórtalo conservando "
            "las variables y la unidad de análisis."
        )

    if pol.espacio == "exigida" and not diag.tiene_espacio:
        avisos.append(
            "**Falta la delimitación espacial:** el ítem 2 pide que el título articule el espacio, "
            f"y este estudio la exige — {pol.motivo_espacio}. Añade la institución, el sector o el "
            "ámbito territorial; si aún no lo sabes, deja «[institución]» y complétalo, pero no lo inventes."
        )
    if pol.tiempo == "exigida" and not diag.tiene_tiempo:
        avisos.append(
            "**Falta la delimitación temporal:** este estudio la exige — "
            f"{pol.motivo_tiempo}. Añade el año o el rango de años del periodo de referencia."
        )
    # El caso inverso, que era el otro error: meter un año donde no delimita nada.
    if pol.tiempo == "opcional" and diag.tiene_tiempo:
        avisos.append(
            "**Revisa el año del título:** para este tipo de estudio la delimitación temporal es "
            f"opcional — {pol.motivo_tiempo}. Consérvalo solo si ese año corresponde de verdad a los "
            "datos; si no, quítalo y gana palabras para las variables."
        )

    if avisos:
        logger.info(f"[Redactor] Título con {len(avisos)} aviso(s) determinista(s)")
    return "\n\n".join(avisos)


def _subpuntos_omitidos(plan: dict | None, texto: str) -> list[str]:
    """Subpuntos que el plan mandaba reescribir y no aparecen en el texto entregado.

    Se compara por el nombre del subpunto sin su numeración y sin tildes, porque el
    modelo reescribe «### Título» donde el índice dice «1 Título»; exigir el nombre
    literal daría falsos positivos en cada documento.
    """
    reescribir = (plan or {}).get("reescribir") or []
    if not reescribir or not texto:
        return []

    def _clave(s: str) -> str:
        s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower()
        s = re.sub(r"^\s*[\divxlc]+(\.[\d]+)*[.)]?\s+", "", s)   # quita la numeración
        return re.sub(r"[^a-z0-9]+", " ", s).strip()

    cuerpo = _clave(texto)
    return [s for s in reescribir if (k := _clave(s)) and k not in cuerpo]


def _instruccion_nucleo(plan: dict | None) -> str:
    """Instrucción del modo NÚCLEO: MEJORAR lo que no llega a su máximo y JUSTIFICAR lo que sí.

    `plan = {"reescribir": [secciones (nota < máx)],
             "observar":   [{"seccion","puntaje","maximo","razones"} (ya en su máximo)],
             "razones_reescribir": {seccion: [razones]}}`.
    Sin plan → reescribir todos los subpuntos.
    """
    plan = plan or {}
    reescribir = plan.get("reescribir") or []
    observar   = plan.get("observar") or []
    razones_re = plan.get("razones_reescribir") or {}

    if not reescribir and not observar:
        return (
            "Estás mejorando el NÚCLEO DE COHERENCIA del proyecto (varios subpuntos juntos). "
            "En `texto_redactado` entrega el texto mejorado de CADA subpunto, separado por "
            "encabezados markdown (### Título, ### Problema/Pregunta, ### Objetivos, "
            "### Hipótesis, ### Variables, y los que apliquen). Asegura la TRAZABILIDAD entre "
            "ellos y con el tipo/diseño, la población y el método; no fuerces lo que el tipo no requiere."
        )

    lin_re = []
    for s in reescribir:
        falta = "; ".join(r for r in (razones_re.get(s) or []) if r)
        lin_re.append(f"- {s}" + (f" → qué cerrar: {falta}" if falta else ""))
    lin_re_txt = "\n".join(lin_re) or "- (ninguno: todos alcanzan ya su nota máxima)"

    lin_obs = []
    for o in observar:
        pj, mx = o.get("puntaje"), o.get("maximo")
        nota = f"{pj}/{mx}" if pj is not None and mx else "máximo"
        lin_obs.append(f"- {o.get('seccion')} (ya en {nota})")
    lin_obs_txt = "\n".join(lin_obs) or "- (ninguno)"

    # Feedback de la ITERACIÓN ANTERIOR (núcleo iterativo): ítems que aún no llegaron al
    # máximo, con el porqué, para que esta vuelta se acerque más (parte del texto ya mejorado).
    feedback = plan.get("feedback_iteracion") or []
    if feedback:
        lin_fb = "\n".join(
            f"- Ítem {f.get('numero')}: {f.get('criterio', '')} — sigue por debajo del máximo porque: "
            f"{f.get('razon') or 'falta evidenciarlo plenamente'}"
            for f in feedback
        )
        bloque_fb = (
            "\n\nITERACIÓN PREVIA — estos ítems AÚN NO llegaron al máximo. Estás partiendo del texto que YA "
            "mejoraste; analiza POR QUÉ no llegaron y mejóralos ESPECÍFICAMENTE en esta versión, sin deshacer "
            "lo que ya estaba bien:\n" + lin_fb
        )
    else:
        bloque_fb = ""

    return (
        "Estás trabajando el NÚCLEO DE COHERENCIA (título · problema · objetivos · hipótesis · "
        "variables). TODO va en `texto_redactado`.\n"
        "ENCABEZADOS OBLIGATORIOS: usa EXACTAMENTE los nombres de las listas A y B, copiados tal cual "
        "y precedidos de `### `. No inventes otros encabezados, no cambies su numeración, no añadas "
        "subpuntos que no estén en las listas y no omitas ninguno. Cada bloque contiene SOLO su propio "
        "contenido.\n\n"
        "A) MEJÓRALOS DE VERDAD (su nota NO es la máxima). Entrega el texto del subpunto YA MEJORADO, "
        "listo para entregar, APLICANDO los cambios (no solo describiéndolos). Cada cambio tiene que "
        "cerrar una de las brechas indicadas abajo: si un retoque no cierra ninguna, NO lo hagas — "
        "cambiar palabras correctas por sinónimos no sube la nota y le borra su voz al estudiante. "
        "Cierra exactamente estas brechas:\n"
        f"{lin_re_txt}\n\n"
        "B) NO los reescribas: YA tienen la nota máxima de su criterio. Reproduce su texto SIN TOCARLO "
        "y añade debajo una línea «✓ Ya cumple (nota)» que FUNDAMENTE, apoyándote en los LIBROS DE "
        "METODOLOGÍA del CONTEXTO RAG, POR QUÉ cumple el criterio (menciona la fuente de forma natural). "
        "No inventes citas ni autores. Si crees que aun así mejorarían, dilo en `recomendaciones`, "
        "nunca reescribiéndolos:\n"
        f"{lin_obs_txt}\n\n"
        "En `recomendaciones` entrega una LISTA NUMERADA de los CAMBIOS CONCRETOS que aplicaste en cada "
        "subpunto reescrito, y de qué brecha cierra cada uno (p. ej. «1. Título: se precisó “X” por “Y” "
        "para articular la relación entre variables — cierra el ítem 2»). No incluyas ahí los subpuntos "
        "de la lista B. Respeta la TRAZABILIDAD entre subpuntos y con el tipo/diseño; no fuerces lo que "
        "el tipo no requiere."
        + bloque_fb
    )


def _notas_na_tipo(state: MentoriaState) -> str:
    """Mensaje DUAL para ítems que el tipo no exige pero la rúbrica sí califica:
    no son errores (por el tipo) y el sistema les otorga el puntaje MÁXIMO."""
    na = state.get("items_na_tipo") or []
    if not na:
        return ""
    lineas = [
        "**Criterios que la rúbrica UPAO califica pero tu tipo de investigación no requiere** "
        "(recibieron el puntaje máximo: al no poder exigírsete, no se te penaliza):"
    ]
    for it in na:
        n   = it.get("item_numero", "?")
        obs = (it.get("observacion") or "").strip()
        lineas.append(
            f"- Ítem {n}: no exigible por tu tipo/diseño → máximo otorgado. "
            f"Aun así, prepárate para justificar su ausencia ante el jurado. {obs}"
        )
    return "\n".join(lineas)


# ── Verificación determinística de fidelidad del texto mejorado ────────────────
_RE_CITA_KEY = re.compile(
    r"\(\s*([A-ZÁÉÍÓÚÑ][A-Za-zÁÉÍÓÚÜÑáéíóúüñ\-]+)[^()]{0,80}?,\s*((?:19|20)\d{2})[a-z]?\s*\)"
)
_RE_ESCALA_SOSPECHOSA = re.compile(
    r"(likert(?:\s+de\s+\d+\s+puntos?)?|puntajes?\s+del?\s+\d+\s+al?\s+\d+|"
    r"escala\s+(?:de\s+)?\d+\s*(?:a|al|-|–)\s*\d+)",
    re.IGNORECASE,
)


def _norm_ascii(t: str) -> str:
    import unicodedata
    return unicodedata.normalize("NFKD", t or "").encode("ascii", "ignore").decode("ascii").lower()


def _verificar_fidelidad(texto_original: str, texto_mejorado: str) -> str:
    """Compara el texto mejorado contra el original y reporta desvíos factuales.

    Sin LLM (regex): (1) citas (Autor, año) del original que la reescritura perdió;
    (2) menciones de escalas/instrumentos («Likert de 5», «puntajes del 1 al 5»)
    que NO existen en el original — el caso real fue inventar una escala 1-5 cuando
    el instrumento oficial es la rúbrica 0-3. Devuelve un aviso markdown o ''.
    """
    if not (texto_original or "").strip() or not (texto_mejorado or "").strip():
        return ""
    avisos: list[str] = []

    mejorado_norm = _norm_ascii(texto_mejorado)
    perdidas = []
    for m in _RE_CITA_KEY.finditer(texto_original):
        apellido, anio = m.group(1), m.group(2)
        if _norm_ascii(apellido) not in mejorado_norm:
            clave = f"{apellido} ({anio})"
            if clave not in perdidas:
                perdidas.append(clave)
    if perdidas:
        avisos.append(
            "la reescritura perdió estas citas del original: "
            + ", ".join(perdidas[:6])
            + (" …" if len(perdidas) > 6 else "")
            + ". Restitúyelas o verifica que su contenido siga respaldado."
        )

    original_norm = _norm_ascii(texto_original)
    nuevas_escalas = []
    for m in _RE_ESCALA_SOSPECHOSA.finditer(texto_mejorado):
        frase = m.group(0).strip()
        if _norm_ascii(frase) not in original_norm and frase not in nuevas_escalas:
            nuevas_escalas.append(frase)
    if nuevas_escalas:
        avisos.append(
            "menciona escalas/instrumentos que NO están en tu texto original: "
            + "; ".join(f"«{f}»" for f in nuevas_escalas[:4])
            + ". Verifica que correspondan a tu instrumento real (p. ej. la rúbrica oficial 0-3) "
              "antes de adoptar la reescritura."
        )

    if not avisos:
        return ""
    return "⚠️ **Verificación de fidelidad del texto mejorado:** " + " Además, ".join(avisos)


def _formatear_errores(errores: list) -> str:
    """Formatea la lista de errores confirmados para el prompt del redactor."""
    if not errores:
        return "No hay errores específicos confirmados — revisa el feedback general del Auditor."
    lineas = []
    for e in errores:
        if isinstance(e, dict):
            lineas.append(
                f"- Ítem {e.get('item_numero', '?')}: {e.get('descripcion', '')} "
                f"(puntaje actual: {e.get('puntaje_actual', '?')}/3)"
            )
    return "\n".join(lineas) if lineas else "Sin errores específicos."
