"""
Panel de IDEACIÓN — «no sé qué tema hacer».

Es el momento más caro de equivocarse de toda la tesis y el que peor se atendía:
la consulta caía en el conversador genérico, que respondía lo que respondería
cualquier modelo suelto —«habla con tu profesor», «revisa la literatura»— sin
tocar ninguna de las dos fuentes que este sistema tiene y un modelo suelto no:
las 266 tesis aprobadas de la escuela de sistemas y los cuatro libros de
metodología indexados.

Tres agentes con incentivos opuestos, igual que el panel de título:

  1. PROBLEMATIZADOR — convierte el interés del estudiante en PROBLEMAS
     investigables. Su regla dura es invertir el orden de ingeniería: primero a
     quién le duele qué y con qué evidencia se sabe, y solo después la
     tecnología. Si el estudiante llega con una solución buscando problema
     («quiero hacer algo con sistemas agénticos»), lo dice y lo reencuadra.
  2. DISEÑADOR — para cada problema arma el esqueleto metodológico completo:
     variables independiente y dependiente, tipo y diseño que se derivan, QUÉ
     PERMITE CONCLUIR ese diseño y qué no, y los instrumentos y datos concretos
     que harían falta.
  3. AUDITOR DE VIABILIDAD — ataca cada opción por donde se cae: datos que no se
     conseguirán, alcance que no cabe en una tesis, medición imposible, o un tema
     ya cubierto por el repositorio. Recomienda una y dice qué debe confirmar el
     estudiante antes de comprometerse.

No inventa empresas ni cifras: lo que no está respaldado se marca como supuesto
a verificar.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Literal, TypedDict

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from .llm import llm_rapido

logger = logging.getLogger(__name__)

_K_LIBROS = 6
_MAX_CHARS_FRAG = 900
_MAX_CANDIDATOS = 3

_FALLBACK = (
    "No pude completar el análisis de temas en este momento. Vuelve a pedírmelo en unos "
    "segundos, o cuéntame en una línea qué te interesa y lo retomamos."
)


# ── Contratos de salida ─────────────────────────────────────────────────────

class ProblemaCandidato(BaseModel):
    problema: str = Field(description="El problema en una frase: quién lo sufre, dónde y en qué se nota. "
                                      "Redactado para que lo lea él, sin referirte a él en tercera persona.")
    a_quien_afecta: str = Field(description="Actor concreto que padece el problema (área, rol, empresa tipo).")
    evidencia_necesaria: str = Field(
        description="Qué dato o hecho habría que mostrar para probar que el problema existe y su magnitud."
    )
    por_que_investigable: str = Field(
        description="Por qué esto es investigable y no solo un encargo de desarrollo."
    )


class SalidaProblematizador(BaseModel):
    diagnostico_enfoque: str = Field(
        description="Hablándole DE TÚ: si viene con una solución buscando problema, díselo con claridad "
                    "y explícale el riesgo; si ya trae un problema, reconóceselo. 2-4 frases. Nunca "
                    "escribas «el estudiante» ni «el usuario»."
    )
    problemas: list[ProblemaCandidato] = Field(description="2 o 3 problemas investigables.")
    preguntas_para_el_estudiante: list[str] = Field(
        default_factory=list,
        description="Preguntas CONCRETAS cuya respuesta cambia el rumbo (máx. 3). Nombra SIEMPRE el "
                    "dato exacto, quién lo custodia y para qué se usaría; y añade qué harías si la "
                    "respuesta es NO, para que el estudiante no se quede bloqueado en un sí/no.",
    )


class DisenoCandidato(BaseModel):
    titulo: str = Field(description="Título propuesto, una línea, sin dos puntos decorativos.")
    problema: str = Field(description="El problema que este título se compromete a resolver.")
    variable_independiente: str = Field(description="Lo que construyes o manipulas (o el artefacto).")
    variable_dependiente: str = Field(description="Lo que se mide para saber si mejoró, con su unidad.")
    tipo_y_diseno: str = Field(description="Tipo de investigación y diseño que este título obliga a usar.")
    que_permite_concluir: str = Field(
        description="Qué se puede afirmar con ese diseño Y qué NO se puede afirmar. Explícito en ambos lados."
    )
    instrumentos: str = Field(description="Instrumentos concretos de recolección, nombrados.")
    datos_necesarios: str = Field(description="Qué datos hacen falta, de dónde salen y quién los tiene.")
    riesgo_principal: str = Field(description="Lo que más probablemente haga fracasar este título.")


class SalidaDisenador(BaseModel):
    candidatos: list[DisenoCandidato] = Field(description="Un diseño por cada problema recibido.")


class VeredictoViabilidad(BaseModel):
    titulo: str = Field(description="El título evaluado, tal cual lo recibiste.")
    viable: bool = Field(description="¿Es defendible como proyecto de tesis de pregrado?")
    obstaculo: str = Field(
        description="El obstáculo EXPLICADO en una frase completa: qué falla y por qué hunde el "
                    "proyecto. No pongas solo la etiqueta («Dato inaccesible»): escribe «Los "
                    "registros de tiempos no existen todavía, así que no habría línea base con la "
                    "que comparar»."
    )
    ajuste: str = Field(
        description="La ACCIÓN correctora, siempre empezando por un verbo: «Acota el estudio a…», "
                    "«Cambia la variable dependiente por…», «Levanta una línea base con…». Nunca "
                    "expliques aquí el problema ni empieces por una negación («No se puede…»): eso "
                    "va en `obstaculo`. Si el título no tiene arreglo, la acción es sustituirlo, así "
                    "que escribe por cuál."
    )


class SalidaAuditor(BaseModel):
    veredictos: list[VeredictoViabilidad]
    recomendado: str = Field(
        description="El título que recomiendas, TEXTUAL y listo para usar. Si ninguno se sostenía tal "
                    "como llegó, escribe aquí la versión YA CORREGIDA del más rescatable. Nunca lo dejes "
                    "vacío ni pongas «ninguno»: el estudiante tiene que salir con un título en la mano."
    )
    por_que: str = Field(description="Por qué ese y no los otros. Compara, no elogies.")
    ajuste_aplicado: str = Field(
        default="",
        description="Si corregiste el título recomendado, di qué le cambiaste y por qué. Vacío si iba bien."
    )
    siguiente_paso: str = Field(
        description="Una acción VERIFICABLE y concreta, en imperativo, que el estudiante pueda hacer esta "
                    "semana (a quién preguntar, qué registro pedir, qué medir). Nada de «reformula el "
                    "enfoque» ni «investiga más»: eso no es un paso, es un deseo."
    )


# ── Estado ──────────────────────────────────────────────────────────────────

class EstadoIdeacion(TypedDict, total=False):
    interes: str
    historial: str
    programa: str
    evidencia_corpus: str
    filas_repositorio: list[dict]
    libros: str
    fuentes_libros: list[str]
    problematizacion: dict
    disenos: dict
    auditoria: dict
    respuesta_final: str


# ── Prompts ─────────────────────────────────────────────────────────────────

_REGLA_VOZ = """\
CÓMO ESCRIBES — LE HABLAS A ÉL, NO DE ÉL:
Todo lo que redactes lo va a LEER el estudiante tal cual, sin que nadie lo reescriba. Diríjete a él
de TÚ, en segunda persona. Nunca escribas «el estudiante menciona…», «el usuario busca…» ni «se
observa que…»: eso suena a informe sobre alguien que no está en la sala, y él está leyendo.
  MAL:  «El estudiante menciona problemas con el registro de empleados, lo que indica que ya tiene
         un problema en mente.»
  BIEN: «Ya traes un problema concreto: el registro de empleados en Grupo Rocío. Eso es más de lo
         que suele haber a estas alturas, y nos sirve de punto de partida.»
Tampoco hables de ti en tercera persona ni menciones que eres un agente o un panel."""

_REGLA_ORDEN = """\
REGLA INNEGOCIABLE — ORDEN PROBLEMA → SOLUCIÓN:
Una tesis de ingeniería NO es «tengo una tecnología, busco dónde aplicarla». Es «existe un problema
medible, y una solución de ingeniería lo mejora de forma comprobable». Si el estudiante llega con la
tecnología primero (por ejemplo «quiero hacer algo con sistemas agénticos» o «con IA»), NO le sigas
la corriente: nómbralo, explícale por qué ese orden hunde la defensa —el jurado pregunta «¿y cuál era
el problema?» y no hay respuesta— y reencuádralo hacia el problema que esa tecnología resolvería.
La tecnología entra después, como MEDIO, y solo si es la mejor opción para ese problema."""

_PROMPT_PROBLEMATIZADOR = """\
Eres el PROBLEMATIZADOR de un panel metodológico universitario. El estudiante todavía NO tiene tema
de tesis, o tiene una idea vaga. Tu trabajo es convertir su interés en PROBLEMAS INVESTIGABLES.

{regla_voz}

{regla_orden}

LO QUE EL ESTUDIANTE HA DICHO:
{interes}

CONVERSACIÓN PREVIA (para no repetir ni contradecir):
{historial}

TÍTULOS QUE YA LE PROPUSISTE EN ESTE HILO. Si hay alguno, es porque te pidió otros o te dio contexto
nuevo: propón problemas DISTINTOS de estos, no versiones maquilladas de los mismos, y no repitas el
mismo sector si ya lo descartó.
{opciones_previas}

TESIS REALES YA APROBADAS EN SU ESCUELA (repositorio institucional). Te dicen qué problemas se
investigan de hecho en este programa y con qué enfoques; úsalas para calibrar el nivel y el alcance
esperados, NO para copiar:
{evidencia_corpus}

FUNDAMENTO METODOLÓGICO (fragmentos de los libros de metodología del sistema):
{libros}

CÓMO TRABAJAS:
- Propón 2 o 3 problemas DISTINTOS entre sí, no tres versiones del mismo.
- Cada problema se enuncia por su efecto medible, no por la tecnología: «los registros de campo se
  llevan en papel y la consolidación tarda días, lo que retrasa decisiones de riego» es un problema;
  «usar sistemas agénticos» no lo es.
- Anclado en lo que el estudiante mencionó. Si nombró una organización concreta, úsala; si no,
  describe el TIPO de organización y márcalo como supuesto, sin inventarte un nombre.
- Las preguntas que le devuelvas deben ser accionables y específicas. Prohibido preguntar «¿tienes
  acceso a los datos?» sin decir a QUÉ datos, quién los custodia y para qué se usarían. Cada pregunta
  lleva su plan B: «si no existe ese registro, se puede levantar una línea base en dos semanas con una
  ficha de tiempos» — así un «no» no bloquea al estudiante, lo reencamina."""

_PROMPT_DISENADOR = """\
Eres el DISEÑADOR METODOLÓGICO del panel. Recibes problemas ya planteados y conviertes cada uno en un
esqueleto de investigación completo, con su título.

{regla_voz}

{regla_orden}

{enfoque_delimitacion}

PROBLEMAS PLANTEADOS POR EL PROBLEMATIZADOR:
{problemas}

LO QUE EL ESTUDIANTE HA DICHO (su contexto real):
{interes}

TESIS REALES APROBADAS EN SU ESCUELA (patrón de forma y de alcance, y qué técnicas resultan viables):
{evidencia_corpus}

FUNDAMENTO METODOLÓGICO (libros indexados del sistema — apóyate en ellos para el tipo, el diseño y
los instrumentos; no inventes autores ni teorías que no aparezcan aquí):
{libros}

CÓMO TRABAJAS — esto es lo que distingue tu respuesta de una lista de títulos bonitos:
- VARIABLES: nombra la independiente (lo que se construye o manipula) y la dependiente (lo que se mide
  para saber si mejoró). La dependiente SIEMPRE con su unidad o indicador: «tiempo de consolidación de
  registros (horas)», «exactitud del inventario (%)». Sin unidad no es una variable, es un deseo.
- DISEÑO Y SUS CONSECUENCIAS: di qué tipo y diseño obliga a usar ese título, y a continuación qué
  PERMITE CONCLUIR y qué NO. Un preexperimento con un solo grupo no permite atribuir causalidad; un
  estudio descriptivo no permite afirmar mejora. El estudiante debe entender que el título ya decide
  el alcance de sus conclusiones.
- INSTRUMENTOS Y DATOS: nómbralos concretamente (ficha de registro de tiempos, cuestionario a los
  operarios de almacén, extracción del log del ERP) y di de dónde salen y quién los custodia.
- Máximo {max_palabras} palabras por título, CONTANDO TODO: los conectores (y, de, por, en, para,
  con…) y el año o periodo. Cuéntalas una a una antes de entregar; 21 ya es demasiado.
- EL AÑO NO SE INVENTA. Hoy estamos en {anio}. Si el estudiante no ha dicho en qué periodo hará el
  estudio, escribe «[periodo]» y no un año plausible: poner uno pasado, como 2024, delata que el
  título se generó sin leer el proyecto.
- Si falta otro dato que la delimitación exige, mismo criterio: «[empresa]», «[área]»."""

_PROMPT_AUDITOR = """\
Eres el AUDITOR DE VIABILIDAD del panel. No propones nada: intentas tumbar cada opción por donde se
cae de verdad. Eres el último filtro antes de que el estudiante se comprometa meses con un tema.

{regla_voz}

DISEÑOS PROPUESTOS:
{disenos}

LO QUE EL ESTUDIANTE HA DICHO:
{interes}

TESIS YA APROBADAS EN SU ESCUELA (si un tema ya está cubierto casi igual, es un riesgo de originalidad):
{evidencia_corpus}

POR DÓNDE ATACAS, EN ESTE ORDEN:
1. DATO INACCESIBLE: la variable dependiente exige una medición que el estudiante probablemente no
   podrá tomar (le negarán el acceso, no existe registro histórico, requiere meses de operación).
   Es la causa más común de tesis abandonadas a mitad.
2. ALCANCE: ¿cabe en un proyecto de pregrado con un solo autor? Un título que promete «transformar la
   gestión» no cabe; uno que mejora un proceso acotado sí.
3. MEDICIÓN: ¿la mejora se puede comparar contra algo? Sin línea base, no hay resultado que defender.
4. ORDEN INVERTIDO: ¿el título sigue siendo una solución buscando problema?
5. ORIGINALIDAD frente al repositorio.

Sé concreto y comparativo, pero NO te limites a destruir: tu trabajo termina con el estudiante
teniendo un título usable en la mano.
- Recomienda UNA opción y justifica frente a las otras.
- Si NINGUNA se sostiene tal como llegó —lo normal en esta fase—, RESCATA la más prometedora:
  reescríbela ya corregida (acotando el alcance, cambiando la variable dependiente por una que sí se
  pueda medir, o reduciendo el proceso a uno solo) y explica qué le cambiaste. Dejar al estudiante con
  «ninguna es viable, reformula» es el peor resultado posible: es justo lo que no sabe hacer solo.
- El siguiente paso debe ser una acción verificable de esta semana: a quién preguntar, qué registro
  pedir, qué medir. No «revisa la literatura»."""


# ── Triage del turno: no todo mensaje pide el panel entero ───────────────────
#
# El panel de tres agentes es caro y, sobre todo, tiene UNA sola forma de
# respuesta. Lanzarlo en cada turno hacía que una duda teórica («¿es necesario
# acotar a un sector?») recibiera otra vez el mismo bloque de problemas,
# opciones y veredictos: el estudiante lee dos respuestas casi idénticas y
# concluye, con razón, que está hablando con una plantilla. Antes de armar nada
# se decide qué necesita este turno.

_RE_OPCION_PROPUESTA = re.compile(r"###\s*Opci[oó]n\s*\d+\s*[—–-]\s*«([^»]+)»")

# Pedir otras opciones es lo único que el triage NO puede leer mal: si el
# estudiante dice que ninguna le convence y el panel no se relanza, se queda sin
# nada. Con opciones ya en el hilo el prompt tiende a ver «pregunta» en todo, así
# que este caso se resuelve antes de consultar al modelo.
_COSAS = r"(?:ideas?|opciones?|temas?|t[ií]tulos?|propuestas?|alternativas?)"
_OTRAS = r"(?:otr[oa]s?|m[aá]s|nuev[oa]s?|distint[oa]s?|diferentes?)"
_RE_PIDE_OTRAS = re.compile(
    # «otras ideas» y «títulos diferentes»: el adjetivo va delante o detrás.
    rf"{_OTRAS}\s+{_COSAS}|{_COSAS}\s+{_OTRAS}|"
    # El rechazo cuenta solo si es a TODAS: «no me gusta la 2» no pide otra tanda,
    # está eligiendo.
    r"ningun[oa]s?\b[^.]{0,25}\bme\s+(?:convencen?|gustan?|cuadran?|sirven?)|"
    r"no\s+me\s+(?:convencen|gustan|sirven|cuadran)\b",
    re.I,
)


class SalidaTriage(BaseModel):
    ruta: Literal["proponer", "pregunta", "elegir"] = Field(
        description="Qué necesita el último mensaje del estudiante."
    )
    consulta_libros: str = Field(
        default="",
        description="Si la ruta NO es «proponer»: en qué buscar en los libros de metodología para "
                    "responderle bien. Una frase con los términos metodológicos que aplican."
    )
    pregunta_pendiente: str = Field(
        default="",
        description="Si la ruta ES «proponer» pero además hizo una PREGUNTA que el panel de opciones "
                    "no responde por sí solo, cópiala aquí tal como la hizo. Vacío si no preguntó nada."
    )


_PROMPT_TRIAGE = """\
Eres el TRIAGE del panel de ideación de tema de tesis. NO respondes al estudiante: solo decides qué
necesita su último mensaje.

ÚLTIMO MENSAJE DEL ESTUDIANTE:
{mensaje}

CONVERSACIÓN PREVIA:
{historial}

OPCIONES QUE EL PANEL YA LE PROPUSO EN ESTE HILO:
{opciones}

LAS RUTAS:
- "proponer": todavía no tiene opciones; o pide otras NUEVAS («dame otras ideas», «ninguna me
  convence», «más opciones», «no me gusta ninguna»); o trae contexto nuevo (una empresa, un área, un
  proceso concreto) sobre el que aún no se le ha propuesto nada. Solo aquí se arma el panel completo
  de problemas, títulos y veredictos.
- "pregunta": está preguntando algo. Una duda teórica o metodológica («¿hace falta acotar a un
  sector?», «¿qué diferencia hay entre preexperimental y cuasiexperimental?»), una duda sobre alguna
  de las opciones que ya recibió, o una corrección a lo que le respondiste («fue una pregunta
  teórica», «no era eso lo que te pedí», «no quiero que me repitas lo mismo»).
- "elegir": ya se quedó con una de las opciones y quiere avanzar con ella.

REGLA DURA: si en este hilo ya recibió opciones y su mensaje no pide opciones NUEVAS ni aporta
contexto nuevo, NO es "proponer". Volver a soltarle el mismo panel es el peor error posible: le
confirma que está leyendo una plantilla y no a un mentor. Entre "proponer" y "pregunta", cuando ya
hay opciones en el hilo, elige "pregunta".
Esa regla NO se aplica cuando pide opciones nuevas o dice que ninguna le convence: ahí siempre es
"proponer", porque negarle opciones lo deja sin nada."""


_PROMPT_DIALOGO = """\
Eres MentorIA, en medio de una conversación con un estudiante de tesis que está decidiendo su tema.
Ahora mismo NO estás armando un panel de opciones: estás RESPONDIENDO a lo que te acaba de decir.

{regla_voz}

LO QUE TE ACABA DE DECIR — a esto respondes, y a nada más:
{mensaje}

CONVERSACIÓN PREVIA:
{historial}

OPCIONES QUE YA LE PROPUSISTE EN ESTE HILO (ya las tiene delante; refiérete a ellas por su nombre
cuando venga al caso, pero NO las vuelvas a listar):
{opciones}

FUNDAMENTO METODOLÓGICO (fragmentos de los libros indexados del sistema). Apóyate en ellos y nombra
el libro cuando lo uses; no inventes autores, teorías ni citas que no aparezcan aquí:
{libros}

TESIS YA APROBADAS EN SU ESCUELA (evidencia de lo que de hecho se acepta en este programa):
{evidencia_corpus}

{politica}

{foco}

CÓMO RESPONDES:
- Responde lo que preguntó, y respóndelo con fundamento: la regla, de dónde sale y qué implica para
  su caso. Una respuesta que un modelo cualquiera podría dar sin leer nada es una respuesta fallida.
- NADA DE «SIEMPRE» NI DE «NUNCA» cuando la regla tiene casos. Si la respuesta depende de algo —de
  dónde salen los datos, del tipo de estudio, del diseño—, ESO va en la PRIMERA frase: «depende de si
  …». No abras con un «sí» rotundo para matizarlo tres párrafos después; el estudiante se queda con
  la primera línea y se lleva la regla equivocada. Después desarrollas: cuándo es obligatorio, cuándo
  solo recomendable y cuándo no aplica, con el criterio que separa un caso del otro. Ese criterio
  está arriba; úsalo, no lo sustituyas por tu intuición.
- CITA EL LIBRO por lo que DICE, no por que exista. Apoya al menos una afirmación en un fragmento de
  arriba nombrando el libro y parafraseando la idea concreta que usas. «La claridad es clave según
  X» no es una cita: no aporta nada que no supieras sin el libro. Si los fragmentos no dan para
  sostener la respuesta, dilo en vez de inventar el respaldo.
- APÓYATE EN LOS TÍTULOS REALES. Cuando la duda sea sobre la forma del título (si hace falta la
  empresa, el sector, el año), cita uno o dos títulos aprobados de arriba y señala qué llevan y qué
  no: es la prueba de que la regla se cumple en su escuela.
- Si te está corrigiendo porque no respondiste lo que preguntaba («fue una pregunta teórica», «no era
  eso»), su mensaje de ahora NO es la pregunta: búscala en la conversación previa, es el mensaje suyo
  al que respondiste mal. Dale la razón en una línea, sin disculpas largas, y RESPONDE ESA pregunta
  —completa, con criterio metodológico—, no la parafrasees ni le expliques por qué es importante.
- NO propongas temas, problemas ni títulos nuevos, y NO reproduzcas la estructura del panel («Los
  problemas que veo…», «Opción 1 —…», «Veredicto de viabilidad»). Eso ya se lo diste; repetirlo es
  exactamente lo que hace que parezca una plantilla.
- La extensión la marca la pregunta: una duda teórica se responde en tres o cuatro párrafos, con la
  regla, su matiz y el ejemplo. Sin encabezados de sección; markdown solo si de verdad ayuda a leer.
- No cierres con la lista de fuentes: eso se añade después, con los títulos a la vista.
- Cierra pidiendo UNA sola cosa, y solo si de verdad la necesitas para seguir. Si no la necesitas, no
  preguntes nada."""

_FOCO_PREGUNTA = """\
QUÉ TOCA EN ESTE TURNO:
Responder su duda con criterio metodológico y aterrizarla a su caso: qué implica para el tema que
está eligiendo. Termina de responder antes de sugerir cualquier otra cosa.
Si la duda es sobre delimitar (sector, empresa, lugar, año), la respuesta útil no es sí ni no: es
decirle en qué caso cae, qué le exige ese caso y qué pasaría si lo pone sin tenerlo —un año o una
empresa que no puede sostener es una falsedad en la carátula, y el jurado pregunta por ella."""

_FOCO_ELEGIR = """\
QUÉ TOCA EN ESTE TURNO:
Ya eligió. Confirma con cuál se queda, dile en una frase qué gana y qué pierde con esa elección, y
qué le falta cerrar antes de escribir el planteamiento (el dato o el acceso que aún no tiene
confirmado). Luego dile que el siguiente paso es construir la realidad problemática y la formulación
del problema, y que te lo pida cuando quiera."""


def _opciones_del_hilo(historial: list[dict] | None) -> list[str]:
    """Títulos que el panel ya propuso en este hilo, para no repetirlos.

    Se leen de las propias respuestas de MentorIA porque el hilo es lo único que
    persiste entre turnos: el estado del panel no se guarda.
    """
    vistos: list[str] = []
    for t in historial or []:
        if t.get("rol") == "user":
            continue
        for m in _RE_OPCION_PROPUESTA.finditer(t.get("contenido") or ""):
            titulo = m.group(1).strip()
            if titulo and titulo not in vistos:
                vistos.append(titulo)
    return vistos


def _triage(
    modelo, mensaje: str, historial_txt: str, opciones: list[str]
) -> tuple[str, str, str]:
    """Decide si este turno pide el panel completo o una respuesta a secas.

    Devuelve la ruta, la consulta con la que buscar en los libros y —cuando el
    turno sí pide opciones pero además traía una pregunta— esa pregunta, que el
    panel por sí solo no contesta.
    """
    if _RE_PIDE_OTRAS.search(mensaje or ""):
        logger.info("[ideacion] Pide opciones nuevas → se arma el panel")
        return "proponer", mensaje, ""

    salida = _invocar(
        _PROMPT_TRIAGE.format(
            mensaje=mensaje or "(sin mensaje)",
            historial=historial_txt,
            opciones="\n".join(f"- «{t}»" for t in opciones) or "(ninguna todavía)",
        ),
        modelo, SalidaTriage,
        "Clasifica qué necesita este turno.",
    )
    if salida is None:
        # Sin clasificación fiable manda la evidencia del hilo: si ya se le
        # entregaron opciones, repetirlas es peor que responderle de más.
        return ("pregunta" if opciones else "proponer"), mensaje, ""
    return salida.ruta, (salida.consulta_libros or mensaje), salida.pregunta_pendiente.strip()


_PROMPT_PENDIENTE = """\
El estudiante pidió temas de tesis y, en el mismo mensaje, preguntó otra cosa. El panel le va a
responder lo que pidió; tú respondes SOLO la pregunta, y va delante del panel.

{regla_voz}

SU PREGUNTA:
{pregunta}

SU MENSAJE COMPLETO (contexto):
{mensaje}

FUNDAMENTO METODOLÓGICO (fragmentos de los libros indexados; no inventes autores ni teorías que no
estén aquí):
{libros}

{politica}

CÓMO RESPONDES:
- Entre 120 y 180 palabras, dos párrafos, sin encabezados ni listas.
- Nada de «siempre» ni de «nunca» si la regla tiene casos: si depende de algo, eso va en la PRIMERA
  frase («depende de si…»), y luego dices qué exige cada caso, con el criterio que los separa. El de
  arriba, no tu intuición.
- Apoya la respuesta en uno de los fragmentos nombrando el libro ({libro_ejemplo}, por ejemplo) y
  parafraseando lo que dice, no el hecho de que exista. Si los fragmentos no dan para sostenerla,
  dilo en vez de inventarte el respaldo.
- No propongas títulos ni temas: de eso se encarga lo que viene debajo. Cierra enlazando con ello en
  media frase («con eso en mente, mira las opciones»), sin anunciar secciones."""


def _responder_pendiente(modelo, pregunta: str, mensaje: str, biblioteca) -> str:
    """Contesta la pregunta que venía pegada al pedido de temas.

    Sin esto, un mensaje como «necesito ayuda con mi título, ¿hace falta acotar a
    un sector?» recibía el panel entero y ni una palabra sobre lo preguntado.
    """
    libros_txt, fuentes = _libros(biblioteca, pregunta)
    prompt = _PROMPT_PENDIENTE.format(
        regla_voz=_REGLA_VOZ,
        pregunta=pregunta,
        mensaje=mensaje,
        libros=libros_txt or "(sin fragmentos disponibles)",
        libro_ejemplo=fuentes[0] if fuentes else "el libro que estés usando",
        politica=_bloque_politica(),
    )
    return _texto_con_cita(modelo, prompt, pregunta, fuentes, bool(libros_txt))


_AVISO_SIN_CITA = """\

REESCRIBE LA RESPUESTA. La que ibas a dar no se apoyaba en ninguno de los fragmentos: no nombraba
ningún libro. Vuelve a escribirla entera —igual de directa, sin alargarla— apoyando al menos una de
sus afirmaciones en un fragmento concreto y nombrando el libro del que sale, con lo que ese libro
dice, no con que exista. Si de verdad los fragmentos no cubren esta pregunta, escríbelo con esas
palabras en vez de citar por citar."""


def _norm_cita(s: str) -> str:
    import unicodedata

    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"\s+", " ", s).strip().lower()


def _firma_libro(fuente: str) -> str:
    """La parte del nombre que identifica a ESE libro y no a cualquier otro.

    Los cuatro libros empiezan igual («METODOLOGÍA DE LA INVESTIGACIÓN…»), que
    además es una frase corriente en español: buscar ese prefijo daba por citado
    cualquier texto que dijera «metodología de la investigación» de pasada. Lo
    que distingue a cada uno es lo que va tras el guion.
    """
    cola = _norm_cita(fuente.rsplit("-", 1)[-1])
    return cola[:25] if len(cola) >= 12 else _norm_cita(fuente)[:25]


def _cita_algun_libro(texto: str, fuentes: list[str]) -> bool:
    """¿La respuesta nombra alguno de los libros que se le pasaron?

    Sin este chequeo, la instrucción de citar se cumplía a ratos: el modelo daba
    una respuesta correcta pero indistinguible de la de cualquier chat, que es
    justo lo que el sistema tiene que superar.
    """
    t = _norm_cita(texto)
    return any(_firma_libro(f) in t for f in fuentes if len(f) >= 10)


def _texto_con_cita(
    modelo, prompt: str, mensaje: str, fuentes: list[str], hay_fragmentos: bool
) -> str:
    """Invoca al modelo y, si no citó ningún libro habiéndolos, le da una segunda pasada."""
    def _invocar_texto(sistema: str) -> str:
        try:
            return modelo.invoke(
                [SystemMessage(content=sistema), HumanMessage(content=mensaje)]
            ).content.strip()
        except Exception as exc:                               # noqa: BLE001
            logger.warning(f"[ideacion] Respuesta en prosa falló: {exc}")
            return ""

    texto = _invocar_texto(prompt)
    if not texto or not fuentes or not hay_fragmentos:
        return texto
    if _cita_algun_libro(texto, fuentes):
        return texto

    logger.info("[ideacion] La respuesta no citaba ningún libro; se pide de nuevo con la cita")
    segundo = _invocar_texto(prompt + _AVISO_SIN_CITA)
    return segundo or texto


def _dialogar(
    modelo, mensaje: str, historial_txt: str, opciones: list[str],
    biblioteca, programa: str, consulta: str, ruta: str,
) -> str:
    """Responde dentro del hilo de ideación, sin volver a montar el panel."""
    libros_txt, fuentes = _libros(biblioteca, consulta or mensaje)
    evidencia, filas = _evidencia_repositorio(consulta or mensaje, programa)

    prompt = _PROMPT_DIALOGO.format(
        regla_voz=_REGLA_VOZ,
        mensaje=mensaje,
        historial=historial_txt,
        opciones="\n".join(f"- «{t}»" for t in opciones) or "(ninguna todavía)",
        libros=libros_txt or "(sin fragmentos disponibles)",
        libro_ejemplo=fuentes[0] if fuentes else "el libro que estés usando",
        evidencia_corpus=evidencia or "(el repositorio no está disponible en este momento)",
        politica=_bloque_politica(),
        foco=_FOCO_ELEGIR if ruta == "elegir" else _FOCO_PREGUNTA,
    )
    texto = _texto_con_cita(modelo, prompt, mensaje, fuentes, bool(libros_txt))
    if not texto:
        return ""

    pie = _pie_fuentes(fuentes, filas, programa)
    return f"{texto}\n\n{pie}" if pie else texto


_MAX_TITULOS_VISIBLES = 5


def _bloque_politica() -> str:
    """Cuándo el título DEBE delimitar y cuándo no, según de dónde salgan los datos.

    «¿Tengo que aplicarlo a un sector?» no se responde con un sí: depende de si
    el estudio recoge datos de una población real o se entrena sobre un dataset.
    Los dos casos salen del mismo motor de reglas que usa la evaluación
    (`politica_delimitacion`), para que el chat no diga una cosa y la rúbrica otra.
    """
    try:
        from backend.titulo import politica_delimitacion

        campo = politica_delimitacion(
            "tecnologica", None,
            "la solución se valida con la población de usuarios de una empresa concreta",
        )
        dataset = politica_delimitacion(
            "tecnologica", None,
            "el modelo se entrena y evalúa sobre un dataset público de datos secundarios",
        )
    except Exception as exc:                                   # noqa: BLE001
        logger.warning(f"[ideacion] Política de delimitación no disponible: {exc}")
        return ""

    return (
        "QUÉ EXIGE DELIMITAR EL TÍTULO — la regla del sistema, que NO es «siempre». Depende de\n"
        "dónde salgan los datos, y por eso la respuesta se da distinguiendo los dos casos:\n\n"
        "CASO A — el estudio recoge datos de una organización o población real (se implanta, se\n"
        "encuesta, se mide en campo):\n"
        f"{campo.bloque()}\n\n"
        "CASO B — el modelo se entrena y evalúa sobre un dataset público, un benchmark o en\n"
        "laboratorio, sin una organización que lo adopte:\n"
        f"{dataset.bloque()}"
    )


def _delimitacion_legible(titulo: str) -> str:
    """Qué delimita de hecho un título aprobado: lugar, periodo, ambos o ninguno.

    Es el dato que el estudiante necesita para decidir si SU título tiene que
    llevar empresa o año: no la regla enunciada, sino qué hicieron los que ya
    pasaron por el jurado.
    """
    from backend.titulo import contar_palabras_titulo, diagnosticar_titulo

    d = diagnosticar_titulo(titulo)
    # Las marcas espaciales van completas: el detector se queda con la primera
    # coincidencia de cada tipo y a veces la primera es genérica («laboratorio»)
    # mientras el nombre real («Trujillo») viene después.
    lleva = d.marcas_espacio[:2] + d.marcas_tiempo[:1]
    falta = []
    if not d.tiene_espacio:
        falta.append("sin lugar ni institución")
    if not d.tiene_tiempo:
        falta.append("sin año ni periodo")

    partes = []
    if lleva:
        partes.append("lleva " + " y ".join(lleva))
    if falta:
        partes.append(", ".join(falta))
    partes.append(f"{contar_palabras_titulo(titulo)} palabras")
    return "; ".join(partes)


def _estadistica_delimitacion(programa: str = "") -> str:
    """Cuántas de las tesis aprobadas llevan de hecho lugar y periodo."""
    try:
        from backend.rag.titulos_store import estadisticas_delimitacion

        est = estadisticas_delimitacion(programa=programa or None)
        return est.resumen() if est.n else ""
    except Exception as exc:                                   # noqa: BLE001
        logger.warning(f"[ideacion] Estadística de delimitación no disponible: {exc}")
        return ""


def _pie_fuentes(
    fuentes: list[str], filas: list[dict] | None = None, programa: str = ""
) -> str:
    """La evidencia, mostrada: los títulos reales y qué delimita cada uno.

    Antes esto era una línea que decía «consulté 8 tesis y 2 libros», que el
    estudiante no puede verificar ni aprovechar. Viendo los títulos aprobados —y
    si llevan empresa, lugar o año— puede decidir por comparación si el suyo
    necesita esa delimitación, que es justo la duda que trae.
    """
    bloques: list[str] = []

    for f in (filas or [])[:_MAX_TITULOS_VISIBLES]:
        titulo = (f.get("titulo") or "").strip()
        if not titulo:
            continue
        if not bloques:
            bloques.append(
                "**Las tesis aprobadas en las que me apoyé** — fíjate en cómo están delimitadas:"
            )
        anio = f" ({f['anio']})" if f.get("anio") else ""
        enlace = f"[«{titulo}»]({f['url']})" if f.get("url") else f"«{titulo}»"
        bloques.append(f"{len(bloques)}. {enlace}{anio} — {_delimitacion_legible(titulo)}")

    est = _estadistica_delimitacion(programa)
    if est and bloques:
        bloques.append(est)

    if fuentes:
        # Sin recortar a mitad de palabra: el nombre truncado del libro
        # («…CUANTITATIVA, CUAL») no acredita nada, que es para lo que está.
        plural = "Libros de metodología consultados" if len(fuentes) > 1 else "Libro de metodología consultado"
        bloques.append(f"**{plural}:** {', '.join(fuentes)}.")

    if not bloques:
        return ""
    return "---\n\n" + "\n\n".join(bloques)


# ── Saneado determinista de los títulos propuestos ──────────────────────────

_RE_ANIO = re.compile(r"\b(19|20)\d{2}\b")


class TituloRecortado(BaseModel):
    original: str = Field(description="El título largo, copiado tal cual.")
    recortado: str = Field(
        description="El mismo título dentro del límite de palabras, sin perder las variables ni la "
                    "delimitación. Se quitan adornos y redundancias, no información."
    )


class SalidaRecorte(BaseModel):
    titulos: list[TituloRecortado]


_PROMPT_RECORTE = """\
Eres el corrector de extensión de títulos. Recibes títulos que EXCEDEN el límite de {max_palabras}
palabras de la ficha UPAO y los devuelves dentro del límite.

CUENTAN TODAS LAS PALABRAS: los conectores (y, de, por, en, para, con, la, el…) y también el año o
periodo. No hay palabras que «no sumen».

CÓMO RECORTAS, en este orden:
1. Quita adornos y redundancias: «mediante el uso de» → «mediante»; «para mejorar el consumo de agua
   y la producción agrícola» → deja la variable dependiente principal.
2. Funde perífrasis: «sistema de monitoreo en tiempo real» → «monitoreo en tiempo real».
3. NO quites: la variable independiente (lo que se construye), la variable dependiente (lo que se
   mide), ni la delimitación de lugar. Si hay que sacrificar algo, sacrifica la segunda variable
   dependiente, no el lugar.

TÍTULOS A RECORTAR (con su conteo actual):
{titulos}"""


def _anio_valido() -> int:
    from datetime import date

    return date.today().year


def _sanear_anio(titulo: str) -> str:
    """Sustituye por un marcador cualquier año que el modelo se haya inventado.

    Los modelos rellenan el hueco de delimitación temporal con un año plausible
    —2024 una y otra vez— que además queda caduco. El periodo del estudio lo
    decide el estudiante, no el panel: hasta que lo diga, va un marcador.
    """
    actual = _anio_valido()
    admitidos = {str(actual), str(actual + 1)}

    def _reemplazo(m: re.Match) -> str:
        return m.group(0) if m.group(0) in admitidos else "[periodo]"

    saneado = _RE_ANIO.sub(_reemplazo, titulo)
    # El año solía venir ya entre corchetes («… [2024]»), así que la sustitución
    # dejaba «[[periodo]]».
    return saneado.replace("[[periodo]]", "[periodo]")


def _sanear_titulos(modelo, disenos: dict) -> dict:
    """Aplica el límite de palabras y el saneado de año a los títulos propuestos.

    El límite se pedía en el prompt pero nadie lo comprobaba, y salían títulos de
    22 palabras contra un máximo de 20 — el conteo determinista ya existía en
    `backend.titulo`, solo no se estaba usando aquí.
    """
    from backend.titulo import MAX_PALABRAS_UPAO, contar_palabras_titulo

    candidatos = disenos.get("candidatos") or []
    if not candidatos:
        return disenos

    for c in candidatos:
        c["titulo"] = _sanear_anio(c.get("titulo", ""))

    largos = [
        c for c in candidatos
        if contar_palabras_titulo(c.get("titulo", "")) > MAX_PALABRAS_UPAO
    ]
    if largos:
        listado = "\n".join(
            f"- «{c['titulo']}» ({contar_palabras_titulo(c['titulo'])} palabras)" for c in largos
        )
        salida = _invocar(
            _PROMPT_RECORTE.format(max_palabras=MAX_PALABRAS_UPAO, titulos=listado),
            modelo, SalidaRecorte,
            "Recorta cada título dentro del límite sin perder variables ni delimitación.",
        )
        if salida:
            por_original = {t.original.strip(): t.recortado.strip() for t in salida.titulos}
            for c in largos:
                nuevo = por_original.get(c["titulo"].strip(), "")
                if nuevo and contar_palabras_titulo(nuevo) <= MAX_PALABRAS_UPAO:
                    logger.info(
                        f"[ideacion] Título recortado de "
                        f"{contar_palabras_titulo(c['titulo'])} a {contar_palabras_titulo(nuevo)} palabras"
                    )
                    c["titulo"] = _sanear_anio(nuevo)
        aun_largos = [
            c for c in candidatos
            if contar_palabras_titulo(c.get("titulo", "")) > MAX_PALABRAS_UPAO
        ]
        for c in aun_largos:
            # Si ni recortando entra, se avisa en el propio texto: es preferible
            # que el estudiante lo sepa a que lo entregue creyendo que cumple.
            c["riesgo_principal"] = (
                f"⚠️ Este título tiene {contar_palabras_titulo(c['titulo'])} palabras y el máximo "
                f"UPAO es {MAX_PALABRAS_UPAO} (cuentan los conectores y el periodo): recórtalo antes "
                "de presentarlo. " + (c.get("riesgo_principal") or "")
            ).strip()
    return disenos


# ── Saneado de los veredictos de viabilidad ─────────────────────────────────

# Un «ajuste» que empieza negando no es un arreglo: es el obstáculo puesto en el
# campo equivocado, y el estudiante se queda sin saber qué hacer.
_RE_AJUSTE_INVERTIDO = re.compile(
    r"^\s*(no\s+(se|hay|existe|tiene|es|puede|resulta|se\s+puede)|"
    r"es\s+imposible|resulta\s+imposible|ser[ií]a\s+imposible|"
    r"carece|falta[n]?\s|sin\s+embargo)",
    re.I,
)
_MIN_CHARS_OBSTACULO = 30


class VeredictoCorregido(BaseModel):
    titulo: str = Field(description="El título, copiado tal cual lo recibiste.")
    obstaculo: str = Field(description="El obstáculo explicado en una frase completa.")
    ajuste: str = Field(
        description="La acción correctora, empezando por un verbo en imperativo. Nunca una negación."
    )


class SalidaCorreccionVeredictos(BaseModel):
    veredictos: list[VeredictoCorregido]


_PROMPT_VEREDICTOS = """\
Corriges veredictos de viabilidad mal repartidos. En los de abajo el obstáculo y el arreglo están
intercambiados o incompletos: donde debería ir la ACCIÓN correctora hay una explicación del problema,
normalmente empezando por «No se puede…».

Para cada uno devuelve los dos campos bien puestos:
  · `obstaculo`: qué falla y por qué hunde el proyecto, en una frase completa.
  · `ajuste`: qué HACER, empezando por un verbo en imperativo («Acota…», «Cambia…», «Levanta…»,
    «Sustituye…»). Nunca empieza por una negación: si el problema es que no hay datos, la acción es
    cómo conseguirlos o con qué sustituirlos, no repetir que no los hay.

VEREDICTOS A CORREGIR:
{veredictos}"""


def _sanear_veredictos(modelo, auditoria: dict) -> dict:
    """Repone la acción correctora cuando el modelo la cambió por una negación.

    Pasaba de hecho: el obstáculo salía como etiqueta suelta («Dato inaccesible»)
    y en el arreglo aparecía «No se puede garantizar el acceso a datos…», que
    explica otra vez el problema y deja al estudiante sin nada que hacer.
    """
    veredictos = auditoria.get("veredictos") or []
    if not veredictos:
        return auditoria

    malos = [
        v for v in veredictos
        if _RE_AJUSTE_INVERTIDO.match(v.get("ajuste", "") or "")
        or len((v.get("obstaculo") or "").strip()) < _MIN_CHARS_OBSTACULO
    ]
    if not malos:
        return auditoria

    listado = "\n\n".join(
        f"TÍTULO: {v.get('titulo','')}\n  obstaculo actual: {v.get('obstaculo','')}\n"
        f"  ajuste actual: {v.get('ajuste','')}"
        for v in malos
    )
    salida = _invocar(
        _PROMPT_VEREDICTOS.format(veredictos=listado), modelo, SalidaCorreccionVeredictos,
        "Reparte bien el obstáculo y la acción correctora de cada veredicto.",
    )
    if not salida:
        return auditoria

    por_titulo = {c.titulo.strip(): c for c in salida.veredictos}
    n = 0
    for v in malos:
        c = por_titulo.get((v.get("titulo") or "").strip())
        if c and c.ajuste.strip() and not _RE_AJUSTE_INVERTIDO.match(c.ajuste.strip()):
            v["obstaculo"] = c.obstaculo.strip() or v.get("obstaculo", "")
            v["ajuste"] = c.ajuste.strip()
            n += 1
    if n:
        logger.info(f"[ideacion] {n} veredicto(s) con el obstáculo y el arreglo intercambiados, corregidos")
    return auditoria


# ── Recuperación de contexto ────────────────────────────────────────────────

def _libros(biblioteca, consulta: str) -> tuple[str, list[str]]:
    """Fragmentos de los libros de metodología + las fuentes usadas."""
    if biblioteca is None:
        return "", []
    try:
        if biblioteca._collection.count() == 0:
            return "", []
        docs = biblioteca.similarity_search(consulta, k=_K_LIBROS)
    except Exception as exc:                                   # noqa: BLE001
        logger.warning(f"[ideacion] RAG de libros falló: {exc}")
        return "", []

    partes, fuentes = [], []
    for d in docs:
        # La clave del metadato es "fuente" (la pone `library_store` al indexar);
        # leer otra devolvía «libro» y el pie de la respuesta no decía nada útil.
        fuente = (d.metadata or {}).get("fuente") or "Libro de metodología"
        if fuente not in fuentes:
            fuentes.append(fuente)
        partes.append(f"[{fuente}]\n{d.page_content[:_MAX_CHARS_FRAG]}")
    return "\n\n---\n\n".join(partes), fuentes


def _evidencia_repositorio(tema: str, programa: str) -> tuple[str, list[dict]]:
    """Títulos reales de la escuela + estadística de delimitación.

    Devuelve también las FILAS, no solo el bloque para el prompt: al estudiante
    hay que enseñarle los títulos, no decirle que se consultaron.
    """
    try:
        from backend.rag.titulos_store import buscar_titulos_similares, contexto_titulos
        from .deps import get_embeddings

        emb = get_embeddings()
        texto = contexto_titulos(emb, tema=tema, programa=programa or None, k=8)
        filas = buscar_titulos_similares(emb, tema, k=8, programa=programa or None)
        return texto, filas
    except Exception as exc:                                   # noqa: BLE001
        logger.warning(f"[ideacion] Evidencia del repositorio no disponible: {exc}")
        return "", []


# ── Nodos ───────────────────────────────────────────────────────────────────

def _invocar(prompt: str, modelo, esquema, usuario: str):
    """Llamada con salida estructurada; None si el modelo no la respeta."""
    try:
        return modelo.with_structured_output(esquema).invoke(
            [SystemMessage(content=prompt), HumanMessage(content=usuario)]
        )
    except Exception as exc:                                   # noqa: BLE001
        logger.warning(f"[ideacion] Fallo de salida estructurada: {exc}")
        return None


def _formatear_problemas(datos: dict) -> str:
    filas = []
    for i, p in enumerate(datos.get("problemas") or [], 1):
        filas.append(
            f"{i}. PROBLEMA: {p.get('problema','')}\n"
            f"   Afecta a: {p.get('a_quien_afecta','')}\n"
            f"   Evidencia necesaria: {p.get('evidencia_necesaria','')}\n"
            f"   Por qué es investigable: {p.get('por_que_investigable','')}"
        )
    return "\n\n".join(filas) or "(sin problemas planteados)"


def _formatear_disenos(datos: dict) -> str:
    filas = []
    for i, c in enumerate(datos.get("candidatos") or [], 1):
        filas.append(
            f"{i}. TÍTULO: {c.get('titulo','')}\n"
            f"   Problema: {c.get('problema','')}\n"
            f"   VI: {c.get('variable_independiente','')} | VD: {c.get('variable_dependiente','')}\n"
            f"   Tipo y diseño: {c.get('tipo_y_diseno','')}\n"
            f"   Permite concluir: {c.get('que_permite_concluir','')}\n"
            f"   Instrumentos: {c.get('instrumentos','')}\n"
            f"   Datos: {c.get('datos_necesarios','')}\n"
            f"   Riesgo: {c.get('riesgo_principal','')}"
        )
    return "\n\n".join(filas) or "(sin diseños)"


# ── Redacción de la respuesta ───────────────────────────────────────────────

def _componer(estado: EstadoIdeacion) -> str:
    prob = estado.get("problematizacion") or {}
    dis = estado.get("disenos") or {}
    aud = estado.get("auditoria") or {}
    partes: list[str] = []

    if prob.get("diagnostico_enfoque"):
        partes.append(f"## Antes de elegir tema\n\n{prob['diagnostico_enfoque']}")

    problemas = prob.get("problemas") or []
    if problemas:
        partes.append("## Los problemas que veo detrás de tu interés")
        for i, p in enumerate(problemas, 1):
            partes.append(
                f"**{i}. {p.get('problema','')}**\n\n"
                f"- **A quién afecta:** {p.get('a_quien_afecta','')}\n"
                f"- **Qué tendrías que demostrar:** {p.get('evidencia_necesaria','')}\n"
                f"- **Por qué es investigable:** {p.get('por_que_investigable','')}"
            )

    candidatos = dis.get("candidatos") or []
    veredictos = {v.get("titulo", ""): v for v in (aud.get("veredictos") or [])}
    if candidatos:
        partes.append("## Cómo se convierte cada uno en una tesis")
        for i, c in enumerate(candidatos, 1):
            v = veredictos.get(c.get("titulo", ""), {})
            bloque = [
                f"### Opción {i} — «{c.get('titulo','')}»",
                f"**Problema que resuelve:** {c.get('problema','')}",
                "",
                f"- **Variable independiente:** {c.get('variable_independiente','')}",
                f"- **Variable dependiente (lo que mides):** {c.get('variable_dependiente','')}",
                f"- **Tipo y diseño que te obliga a usar:** {c.get('tipo_y_diseno','')}",
                f"- **Qué te deja concluir y qué no:** {c.get('que_permite_concluir','')}",
                f"- **Instrumentos:** {c.get('instrumentos','')}",
                f"- **Datos que necesitas y de dónde salen:** {c.get('datos_necesarios','')}",
                f"- **Riesgo principal:** {c.get('riesgo_principal','')}",
            ]
            if v:
                estado_v = "viable" if v.get("viable") else "no viable tal como está"
                # El ajuste puede venir vacío: sin este guardia la línea terminaba
                # en un «Ajuste:» huérfano, justo donde iba lo accionable.
                linea = f"- **Veredicto de viabilidad:** {estado_v}. {v.get('obstaculo','')}".rstrip()
                if (v.get("ajuste") or "").strip():
                    linea += f" *Cómo se corrige:* {v['ajuste'].strip()}"
                bloque.append(linea)
            partes.append("\n".join(bloque))

    if aud.get("recomendado"):
        partes.append(
            f"## Cuál elegiría y por qué\n\n**«{aud['recomendado']}»**\n\n{aud.get('por_que','')}"
        )
    if aud.get("siguiente_paso"):
        partes.append(f"## Tu siguiente paso\n\n{aud['siguiente_paso']}")

    preguntas = prob.get("preguntas_para_el_estudiante") or []
    if preguntas:
        partes.append(
            "## Lo que necesito saber de ti\n\n"
            + "\n".join(f"- {p}" for p in preguntas)
        )

    pie = _pie_fuentes(
        estado.get("fuentes_libros") or [],
        estado.get("filas_repositorio") or [],
        estado.get("programa") or "",
    )
    if pie:
        partes.append(pie)

    return "\n\n".join(partes).strip()


# ── Orientación inicial (el estudiante no ha dicho NADA de sus intereses) ───

class LineaInvestigacion(BaseModel):
    linea: str = Field(description="Nombre corto de la línea de investigación.")
    que_problemas_ataca: str = Field(description="Qué tipo de problema real se resuelve ahí. Una o dos frases.")
    ejemplo_real: str = Field(description="Un título REAL de la lista, copiado tal cual.")
    que_necesitarias: str = Field(description="Qué acceso o dato haría falta para hacer una tesis en esa línea.")


class SalidaOrientacion(BaseModel):
    lineas: list[LineaInvestigacion] = Field(description="4 a 6 líneas de investigación distintas.")


_PROMPT_ORIENTACION = """\
Eres el orientador del panel. El estudiante dice que no sabe sobre qué hacer su tesis y NO ha dado
ninguna pista de sus intereses.

{regla_voz}
 No le sirve que le digas «habla con tu profesor» o «revisa la
literatura»: eso ya lo sabe. Lo que necesita es ver QUÉ SE INVESTIGA DE HECHO en su escuela para
tener sobre qué reaccionar.

Abajo tienes títulos REALES de tesis ya aprobadas en su escuela. Agrúpalos en las líneas de
investigación que de verdad existen ahí y descríbelas por el PROBLEMA que atacan, no por la
tecnología que usan.

TÍTULOS REALES APROBADOS EN SU ESCUELA:
{titulos}

CÓMO TRABAJAS:
- 4 a 6 líneas, claramente distintas entre sí.
- Cada una descrita por el tipo de problema que resuelve («los tiempos de atención en mesa de ayuda
  se descontrolan y no hay trazabilidad»), no por el nombre de la herramienta.
- El ejemplo real debe ser un título copiado literalmente de la lista, sin retocar.
- En «qué necesitarías» sé concreto: a qué organización habría que tener acceso y qué registro o
  medición habría que poder tomar. Nada de «acceso a los datos» a secas."""


def _total_corpus() -> int:
    """Cuántas tesis de la escuela hay indexadas (no las que se muestrearon)."""
    try:
        from backend.rag.titulos_store import cargar_corpus
        return len(cargar_corpus())
    except Exception:                                          # noqa: BLE001
        return 0


def _titulos_recientes(n: int = 45) -> list[str]:
    """Muestra de títulos reales de la escuela, los más recientes primero."""
    try:
        from backend.rag.titulos_store import filtrar_corpus

        filas = filtrar_corpus(anio_min=2018)
        filas.sort(key=lambda f: (f.get("anio") or 0), reverse=True)
        return [f["titulo"] for f in filas[:n] if f.get("titulo")]
    except Exception as exc:                                   # noqa: BLE001
        logger.warning(f"[ideacion] No se pudo muestrear el corpus: {exc}")
        return []


def _sin_interes_declarado(interes: str) -> bool:
    """¿El estudiante todavía no ha dicho NADA sobre qué le interesa?

    Se quita la parte que es puro «no sé qué tema hacer»: si no queda contenido,
    no hay sobre qué problematizar y proponerle problemas inventados sería peor
    que no responder — que es justo lo que hacía el chat genérico.
    """
    import re as _re

    resto = _re.sub(
        r"(no\s+s[eé]|no\s+tengo|ayuda\w*|dame|ideas?|tema|t[ií]tulo|tesis|proyecto|"
        r"hacer|hago|elegir|escoger|definir|empezar|por\s+d[oó]nde|qu[eé]|de|sobre|"
        r"mi|un|una|el|la|para|con|y|o|hola|gracias)",
        " ", interes, flags=_re.I,
    )
    return len(_re.sub(r"[^a-záéíóúñ0-9]", "", resto, flags=_re.I)) < 18


def _orientar(modelo, titulos: list[str]) -> str:
    """Respuesta para el estudiante en blanco: qué se investiga en su escuela."""
    if not titulos:
        return ""
    salida = _invocar(
        _PROMPT_ORIENTACION.format(
            regla_voz=_REGLA_VOZ, titulos="\n".join(f"- {t}" for t in titulos)
        ),
        modelo, SalidaOrientacion,
        "Agrupa los títulos en las líneas de investigación reales de esta escuela.",
    )
    if salida is None or not salida.lineas:
        return ""

    partes = [
        "## Sobre qué se investiga de verdad en tu escuela",
        "",
        f"No te voy a decir que hables con un profesor: eso ya lo sabes. Te muestro lo que "
        f"**sí** se ha aprobado en Ingeniería de Sistemas de la UPAO. Tengo {_total_corpus()} "
        f"tesis de tu escuela indexadas del repositorio; para esto miré las {len(titulos)} más "
        "recientes, que son las que marcan lo que se está aprobando ahora.",
    ]
    for i, l in enumerate(salida.lineas, 1):
        partes.append(
            f"**{i}. {l.linea}**\n\n"
            f"- **Qué problema ataca:** {l.que_problemas_ataca}\n"
            f"- **Tesis real aprobada:** «{l.ejemplo_real}»\n"
            f"- **Qué necesitarías tener:** {l.que_necesitarias}"
        )
    partes.append(
        "## Lo que necesito de ti para concretar\n\n"
        "El tema no sale de elegir una tecnología bonita, sale de un problema al que tengas "
        "acceso. Contéstame estas tres y te armo los títulos con sus variables, su diseño y "
        "los instrumentos que harían falta:\n\n"
        "1. **¿Dónde has trabajado, hecho prácticas o tienes contacto?** Una empresa, un área "
        "de tu universidad, el negocio de un familiar. Es lo que decide a qué datos podrás llegar.\n"
        "2. **¿Qué proceso has visto fallar ahí?** Algo que se hace a mano, que se repite, que "
        "se pierde o que tarda demasiado. No pienses en la solución todavía.\n"
        "3. **¿Existe algún registro de cómo va hoy ese proceso?** Un Excel, un log del sistema, "
        "un cuaderno, tiempos anotados. Sin línea base no hay mejora que puedas demostrar.\n\n"
        "Con una respuesta aunque sea a medias ya puedo trabajar."
    )
    return "\n\n".join(partes)


# ── Entrada pública ─────────────────────────────────────────────────────────

def responder_ideacion(mensaje: str, historial: list[dict], doc, biblioteca) -> dict:
    """Panel de ideación: del «no sé qué tema» a opciones con esqueleto metodológico."""
    from backend.titulo import MAX_PALABRAS_UPAO

    interes = _interes_del_hilo(mensaje, historial)
    programa = (getattr(doc, "programa", "") or "") if doc is not None else ""
    modelo = llm_rapido(temperatura=0.35)

    # Sin ninguna pista, problematizar produce problemas inventados que no son
    # suyos. Se le enseña primero lo que su escuela investiga de verdad y se le
    # piden los tres datos que sí determinan el tema.
    if _sin_interes_declarado(interes):
        titulos = _titulos_recientes()
        respuesta = _orientar(modelo, titulos)
        if respuesta:
            logger.info(f"[ideacion] Orientación inicial con {len(titulos)} títulos del repositorio")
            return {"respuesta": respuesta, "titulo": "", "seccion": None}

    # Estar en el hilo de ideación no significa querer otra tanda de opciones. Una
    # duda teórica, una corrección o un «me quedo con la segunda» se responden
    # hablando; montar el panel otra vez devolvía una respuesta casi idéntica a la
    # anterior, que es justo lo que hace que el sistema parezca precacheado.
    historial_txt = _historial_texto(historial)
    opciones_previas = _opciones_del_hilo(historial)
    ruta, consulta, pendiente = _triage(modelo, mensaje, historial_txt, opciones_previas)
    if ruta in ("pregunta", "elegir"):
        respuesta = _dialogar(
            modelo, mensaje, historial_txt, opciones_previas,
            biblioteca, programa, consulta, ruta,
        )
        if respuesta:
            logger.info(f"[ideacion] Turno resuelto como '{ruta}' (sin relanzar el panel)")
            return {"respuesta": respuesta, "titulo": "", "seccion": None}
        logger.info(f"[ideacion] El diálogo '{ruta}' no produjo respuesta; se arma el panel")

    evidencia, filas_rep = _evidencia_repositorio(interes or mensaje, programa)
    libros_txt, fuentes = _libros(
        biblioteca,
        f"planteamiento del problema variables tipo y diseño de investigación instrumentos "
        f"de recolección {interes}",
    )

    estado: EstadoIdeacion = {
        "interes": interes or mensaje,
        "historial": historial_txt,
        "programa": programa,
        "evidencia_corpus": evidencia or "(el repositorio no está disponible en este momento)",
        "libros": libros_txt or "(sin fragmentos disponibles)",
        "fuentes_libros": fuentes,
    }
    estado["filas_repositorio"] = filas_rep                      # type: ignore[typeddict-unknown-key]

    p = _invocar(
        _PROMPT_PROBLEMATIZADOR.format(
            regla_voz=_REGLA_VOZ,
            regla_orden=_REGLA_ORDEN,
            interes=estado["interes"],
            historial=estado["historial"],
            opciones_previas="\n".join(f"- «{t}»" for t in opciones_previas) or "(ninguno)",
            evidencia_corpus=estado["evidencia_corpus"],
            libros=estado["libros"],
        ),
        modelo, SalidaProblematizador,
        "Plantea los problemas investigables detrás de lo que te ha dicho el estudiante.",
    )
    if p is None:
        return {"respuesta": _FALLBACK, "titulo": "", "seccion": None}
    estado["problematizacion"] = p.model_dump()

    from backend.titulo import politica_delimitacion

    # Sin proyecto aún no se conoce el tipo de estudio, así que se aplica la
    # política por defecto: sirve para que los títulos propuestos ya nazcan
    # delimitados en vez de tener que corregirlos después.
    try:
        politica = (
            "## QUÉ DEBE DELIMITAR EL TÍTULO\n"
            f"{politica_delimitacion(None, None).bloque()}\n"
            "Lo marcado OPCIONAL o NO APLICA no se inventa para «cumplir la rúbrica»."
        )
    except Exception as exc:                                   # noqa: BLE001
        logger.warning(f"[ideacion] Política de delimitación no disponible: {exc}")
        politica = ""

    d = _invocar(
        _PROMPT_DISENADOR.format(
            regla_voz=_REGLA_VOZ,
            regla_orden=_REGLA_ORDEN,
            enfoque_delimitacion=politica,
            problemas=_formatear_problemas(estado["problematizacion"]),
            interes=estado["interes"],
            evidencia_corpus=estado["evidencia_corpus"],
            libros=estado["libros"],
            max_palabras=MAX_PALABRAS_UPAO,
            anio=_anio_valido(),
        ),
        modelo, SalidaDisenador,
        "Convierte cada problema en un título con su esqueleto metodológico completo.",
    )
    estado["disenos"] = _sanear_titulos(modelo, d.model_dump() if d else {})

    if estado["disenos"].get("candidatos"):
        a = _invocar(
            _PROMPT_AUDITOR.format(
                regla_voz=_REGLA_VOZ,
                disenos=_formatear_disenos(estado["disenos"]),
                interes=estado["interes"],
                evidencia_corpus=estado["evidencia_corpus"],
            ),
            modelo, SalidaAuditor,
            "Ataca cada opción por su punto débil y recomienda una.",
        )
        estado["auditoria"] = _sanear_veredictos(modelo, a.model_dump() if a else {})

    respuesta = _componer(estado)
    # Si además de pedir temas preguntó algo, se le contesta ANTES del panel: el
    # panel no tiene dónde meter esa respuesta y quedaba sin contestar.
    if respuesta and pendiente:
        previa = _responder_pendiente(modelo, pendiente, mensaje, biblioteca)
        if previa:
            logger.info("[ideacion] Pregunta del mensaje respondida antes del panel")
            respuesta = f"{previa}\n\n{respuesta}"
    if not respuesta:
        return {"respuesta": _FALLBACK, "titulo": "", "seccion": None}

    recomendado = _sanear_anio((estado.get("auditoria") or {}).get("recomendado", ""))
    if estado.get("auditoria"):
        estado["auditoria"]["recomendado"] = recomendado
    logger.info(
        f"[ideacion] {len(estado['problematizacion'].get('problemas') or [])} problemas, "
        f"{len(estado['disenos'].get('candidatos') or [])} diseños, "
        f"{len(filas_rep)} títulos del repositorio, {len(fuentes)} libros"
    )
    return {"respuesta": respuesta, "titulo": recomendado, "seccion": None}


def _historial_texto(historial: list[dict] | None) -> str:
    if not historial:
        return "(sin turnos previos)"
    lineas = []
    for t in historial[-8:]:
        rol = "Estudiante" if t.get("rol") == "user" else "MentorIA"
        c = (t.get("contenido") or "").strip().replace("\n", " ")
        if c:
            lineas.append(f"{rol}: {c[:300]}")
    return "\n".join(lineas) or "(sin turnos previos)"


def _interes_del_hilo(mensaje: str, historial: list[dict] | None) -> str:
    """Junta lo que el estudiante ha dicho sobre sus intereses en el hilo.

    Hace falta porque la ideación es conversacional: primero dice «no sé qué
    tema» y en el turno siguiente suelta las ideas sueltas. Tomar solo el último
    mensaje perdía justo la parte con contenido.
    """
    partes = []
    for t in (historial or [])[-6:]:
        if t.get("rol") == "user":
            c = (t.get("contenido") or "").strip()
            if c:
                partes.append(c)
    if mensaje.strip():
        partes.append(mensaje.strip())
    return "\n".join(partes[-4:])[:2000]
