"""
Intérprete de intención del chat.

Una sola llamada barata al modelo ligero decide qué hacer con el mensaje del
usuario: lanzar la revisión completa, revisar secciones específicas del TOC,
o responder conversacionalmente (sin lanzar el grafo → cero tokens de agentes).
"""

import logging
import re

from langchain_core.messages import SystemMessage, HumanMessage

from .llm import llm_rapido, extraer_json

logger = logging.getLogger(__name__)

# Verbo EXPLÍCITO de evaluación → es una orden de lanzar la red GRANDE (no una pregunta).
# OJO: "corregir" y "mejorar" NO van aquí — esos los atiende el mini-grafo de debate.
_RE_ACCION_EVAL = re.compile(
    r"\b(eval[uú]a\w*|evaluar|calific\w*|revis\w*|"
    r"audit\w*|punt[uú]a\w*|puntuar|analiz\w*)\b",
    re.I,
)

# Verbo de MEJORA/REDACCIÓN → mini-grafo multiagente (no lanza la red grande).
# Cubre los dos casos de redacción: partir de CERO («elabora un título») y partir
# del texto del estudiante («mejora mi hipótesis», «extiende esto», «parafrasea»).
_RE_MEJORA = re.compile(
    r"\b(corrig\w*|corrije\w*|mejor\w*|redact\w*|reescrib\w*|"
    r"reformul\w*|recomend\w*|lineamient\w*|"
    r"elab[oó]r\w*|gener\w*|escrib\w*|prop[oó]n\w*|propon\w*|plante\w*|formul\w*|"
    r"parafrase\w*|extend\w*|extiend\w*|ampl[ií]\w*|resum\w*|pul\w*|"
    r"ay[uú]dame\s+a\s+(hacer|armar|construir|formular)|"
    r"h[aá]zme|dame\s+(un|una|ideas)|ideas\s+(de|para)|"
    r"c[oó]mo\s+(redacto|formulo|planteo|escribo))\b",
    re.I,
)

# El TÍTULO tiene su propio panel (propone → aterriza → audita) porque juega con
# reglas que ninguna otra sección tiene: límite duro de palabras, delimitación
# espacio/tiempo condicionada al tipo de estudio, y evidencia del repositorio.
_RE_TITULO = re.compile(r"\bt[ií]tulo?s?\b", re.I)
# Verbos que piden TRABAJAR el título (proponer/mejorar), no solo consultarlo.
# Incluye los verbos con los que un estudiante pide ayuda para ELEGIR («qué título
# hago», «no sé cuál escoger»): faltaban, y por eso «no sé qué tema hacer o título»
# no llegaba al panel especializado y lo contestaba el chat genérico.
_RE_TITULO_ACCION = re.compile(
    r"\b(propon\w*|proponer|sugier\w*|sugerir|dame|damelo|plantea\w*|formul\w*|"
    r"cre[ae]\w*|gener\w*|arma\w*|escrib\w*|redact\w*|mejor\w*|corrig\w*|corrije\w*|"
    r"reescrib\w*|reformul\w*|acort\w*|ajust\w*|delimit\w*|opciones|alternativas|ideas|"
    r"hacer|hago|elegir|elijo|escoger|escojo|definir|defino|pensar|piens\w*|"
    r"empez\w*|comenz\w*|orient\w*|ayud\w*)\b",
    re.I,
)

# IDEACIÓN: el estudiante todavía NO tiene tema ni título. Es el momento más
# valioso para el corpus del repositorio y el peor atendido hasta ahora: caía en
# el conversador genérico, que respondía «habla con tu profesor» —exactamente lo
# que daría cualquier modelo suelto—. Este panel SÍ funciona sin proyecto subido,
# porque justo aún no hay proyecto que subir.
_RE_IDEACION = re.compile(
    r"(no\s+s[eé]\s+(qu[eé]|de\s+qu[eé]|sobre\s+qu[eé]|cu[aá]l)\s*(tema|t[ií]tulo|hacer|investigar|"
    r"elegir|escoger)?|"
    r"no\s+(tengo|se\s+me\s+ocurre)\s+(un\s+)?(tema|t[ií]tulo|idea)|"
    r"qu[eé]\s+(tema|t[ií]tulo)\s+(hago|puedo|podr[ií]a|elijo|escojo)|"
    r"(dame|sugi[eé]r\w*|propon\w*|recomi[eé]nda\w*)\s+(me\s+)?(un(os)?\s+)?(tema|t[ií]tulo|idea)|"
    r"ideas?\s+(de|para)\s+(tema|t[ií]tulo|tesis|investigaci[oó]n)|"
    r"no\s+s[eé]\s+por\s+d[oó]nde\s+(empezar|empiezo)|"
    r"ay[uú]dame\s+a\s+(elegir|escoger|definir)\s+(el\s+)?(tema|t[ií]tulo))",
    re.I,
)

# PLANTEAMIENTO: ya tiene título y pide la cadena problema → preguntas → objetivos.
# Es la etapa siguiente a la ideación y se torcía igual: sin proyecto subido caía
# en el chat genérico, que redactaba problemas inventados y preguntas específicas
# que respondían por sí solas la general.
_RE_PLANTEAMIENTO = re.compile(
    r"(planteamiento|realidad problem[aá]tica|formulaci[oó]n del problema|"
    r"redact\w*\s+(el\s+|mi\s+)?problema|plantea\w*\s+(el\s+|mi\s+)?problema|"
    r"pregunta\s+(general|del problema|de investigaci[oó]n)|preguntas?\s+espec[ií]ficas?|"
    r"problemas?\s+espec[ií]ficos?|objetivos?\s+(general|espec[ií]ficos?)|"
    r"qu[eé]\s+sigue|c[oó]mo\s+(sigo|contin[uú]o|avanzo)|"
    r"ya\s+tengo\s+(el\s+)?t[ií]tulo)",
    re.I,
)

# ANTECEDENTES y MARCO TEÓRICO. Panel aparte porque su regla es la contraria a
# la del resto: aquí NO se redacta el contenido. Un antecedente es un estudio
# real y un modelo que lo "redacta" produce referencias inexistentes, que en una
# tesis son falta académica. El panel entrega la búsqueda y la estructura.
_RE_ANTECEDENTES = re.compile(
    r"(antecedent|marco te[oó]rico|marco referencial|bases? te[oó]rica|estado del arte|"
    r"revisi[oó]n (de |de la )?literatura|definici[oó]n de t[eé]rminos|"
    r"art[ií]culos?\s+(cient[ií]fic|para (mi|el))|paper|scopus|scielo|"
    r"c[oó]mo\s+(busco|buscar|encuentro|encontrar)\s+.{0,24}(art[ií]culo|paper|fuente|estudio|"
    r"antecedent|bibliograf))",
    re.I,
)

# OPERACIONALIZACIÓN, MATRIZ DE CONSISTENCIA y MARCO METODOLÓGICO. Panel propio
# porque aquí casi todo es verificable —la muestra se calcula, las columnas están
# fijadas, y qué necesita juicio de expertos se decide de forma determinista— y
# porque es el tramo que deja el camino listo para Tesis 1.
_RE_METODOLOGIA = re.compile(
    # «operalización»/«operacionalisación»: los estudiantes la escriben de mil formas
    # y con la grafía mal escrita la consulta se escapaba a otro panel.
    r"(opera(ci[oó]n)?ali[sz]aci|matriz de consistencia|marco metodol[oó]gic|metodolog[ií]a|"
    r"dimensiones? e indicadores?|escala de medici[oó]n|"
    r"poblaci[oó]n(\s+y\s+muestra)?|tama[nñ]o de (la )?muestra|muestreo|"
    r"dise[nñ]o de (la )?investigaci|preexperiment|cuasiexperiment|experimental puro|"
    r"procedimiento de ejecuci|t[eé]cnicas? (e instrumentos?|de recolecci|de procesamiento)|"
    r"instrumentos? de recolecci|juicio de expertos|cronbach|validaci[oó]n de(l)? instrumento)",
    re.I,
)

# Señal de que el estudiante ESTÁ en una conversación de ideación y responde con
# sus intereses («1. sistemas agénticos 2. …»). Sin esto, el turno siguiente al
# «no sé qué tema» se salía del panel y volvía al chat genérico.
_RE_IDEACION_EN_CURSO = re.compile(
    r"(elegir|escoger|definir)\s+(un\s+)?(tema|t[ií]tulo)|"
    r"posibles?\s+t[ií]tulos|"
    r"problemas?\s+investigables?|"
    r"qu[eé]\s+te\s+interesa|"
    r"[aá]reas?\s+de\s+inter[eé]s",
    re.I,
)

# Pregunta/consulta: empieza con palabra interrogativa o lleva signos de pregunta.
# Alta precisión a propósito: ante la duda preferimos NO lanzar la red.
_RE_PREGUNTA = re.compile(
    r"^\s*(sab[eé]s?|conoc\w+|cu[aá]l\w*|qu[eé]\s|c[oó]mo|d[oó]nde|cu[aá]nto\w*|"
    r"mu[eé]stra\w*|ens[eé][ñn]\w*|recu[eé]rda\w*|dime|tienes?|"
    r"me\s+puedes?\s+decir|puedes?\s+decirme)\b|[¿?]",
    re.I,
)

# CONSULTA sobre lo que el estudiante YA escribió («¿cuál es mi objetivo general?»,
# «¿qué dice mi proyecto sobre la población?», «¿cuántos antecedentes cité?»,
# «cita mi título tal como lo escribí»). Tiene que ganarle a los paneles, que se
# activan por palabras como «objetivo general» o «población»: esos paneles
# GENERAN contenido nuevo, así que a una simple pregunta le devolvían un
# planteamiento inventado sobre otro tema, o guardaban una «versión de trabajo»
# que nadie pidió. Una consulta la responde el conversador leyendo la tesis.
_RE_CONSULTA_DOC = re.compile(
    r"(\bcu[aá]l(es)?\s+(es|son|era|eran|fue|fueron)\s+(mi|mis|el|la|los|las|nuestr\w*)\b|"
    r"\bqu[eé]\s+(\w+\s+){0,4}?(dice|dicen|escrib[ií]\w*|puse|pusimos|plante[eé]\w*|declar[eé]\w*|"
    r"defin[ií]\w*|describ[ií]\w*|cit[eé]\w*|mencion[eé]\w*|propuse|propusimos|tengo|tenemos|hay)\b|"
    r"\bmu[eé]str(a|ame|anos)\b|\bc[ií]t(a|ame|anos)\b|\btal\s+(como|cual)\b|\btextual\w*|"
    r"\bliteral\w*|\bde\s+qu[eé]\s+trata\b|\bres[uú]m(e|eme|enos|ir)\b|"
    r"\bqu[eé]\s+(secciones|partes|apartados|cap[ií]tulos)\b|"
    # Valoraciones de SU texto: «¿mi objetivo guarda relación con mi problema?»,
    # «¿está bien mi hipótesis?». Piden un juicio, no un planteamiento nuevo.
    r"\bguarda(n)?\s+relaci[oó]n\b|\b(es|son)\s+coherentes?\b|\btiene(n)?\s+coherencia\b|"
    r"\bse\s+relaciona(n)?\b|\best[aá](n)?\s+(bien|mal|mejor|correct\w*|alinead\w*|bien\s+planteadx?\w*)\b|"
    r"\bqued[oó]\s+(bien|mejor|mal)\b|"
    r"\bderiva(n)?\s+(de|del)\b|\bse\s+derivan?\b|\bcorresponde(n)?\s+(a|con)\b|\bcumple(n)?\b|"
    r"\bresponde(n)?\s+a\b|\bse\s+alinea(n)?\b|\best[aá](n)?\s+alinead\w*|\bconcuerda(n)?\b|"
    r"\b(es|son)\s+(correct|adecuad|suficient|clar)\w*\b|"
    r"\bcu[aá]nt[oa]s\s+(\w+\s+){0,3}(cit[eé]\w*|puse|tengo|tenemos|escrib[ií]\w*|inclu[ií]\w*|hay)\b|"
    r"\b(tengo|tenemos|est[aá]n?|hay)\s+(ya\s+)?(redactad|escrit|complet|desarrollad|definid)\w*|"
    r"\b(en|seg[uú]n)\s+mi\s+(documento|proyecto|tesis|trabajo|avance)\b)",
    re.I,
)
# Pedidos de ACCIÓN que, aunque vengan en forma de pregunta, sí van a un panel.
_RE_PIDE_ACCION = re.compile(
    r"\b(redact(a|ame|alo|ala|ar|o|en|emos)|mejor(a|ame|alo|ala|ar|o|amos)|corrig\w*|corrij\w*|"
    r"reescrib(e|eme|elo|ir|o)|reformul(a|ame|alo|ar|o)|gener(a|ame|ar)|prop[oó]n\w*|propon(er|go)|"
    r"d[aá]me\w*|ay[uú]d\w*|h[aá]z(me|lo)?|constru\w*|sugi[eé]r\w*|cr[eé]a(me|r)?|arm(a|ame|ar)|"
    r"calcul\w*|busc\w*|complet(a|ame|ar)|plante(a|ame|ar)|formul(a|ame|ar)|escrib(e|eme|ir)|"
    r"elabor(a|ame|ar)|qu[eé]\s+sigue|c[oó]mo\s+(sigo|contin[uú]o|avanzo|hago|debo|puedo|mejoro|redacto))\b",
    re.I,
)


# «¿Qué me falta redactar?» lleva el verbo «redactar», pero pregunta por el
# ESTADO del proyecto: iba al mini-grafo de mejora, que guardaba una versión
# «mejorada» de una sección cualquiera.
_RE_QUE_FALTA = re.compile(
    r"\bqu[eé]\s+(me|nos|le)\s+falta\w*|\bqu[eé]\s+(secciones|partes)\s+(me|nos)\s+falta\w*|"
    r"\bqu[eé]\s+(no\s+)?(he|hemos)\s+(redactado|escrito|completado)|"
    # Pide CONSEJO sobre cómo seguir, no que se reescriba una sección.
    r"\bqu[eé]\s+(deber[ií]a|debo|debemos|tengo\s+que|me\s+conviene|me\s+recomiendas)\s+"
    r"(redactar|escribir|hacer|trabajar|avanzar|completar)|"
    r"\bpor\s+d[oó]nde\s+(empiezo|empezar|sigo|seguir|contin[uú]o)",
    re.I,
)


# Preguntas NORMATIVAS («¿cuántos antecedentes debo tener?», «¿de qué años?»,
# «¿qué norma de citas uso?»): tienen respuesta directa en los criterios fijos del
# conversador. El panel de antecedentes contestaba con cadenas de búsqueda.
_RE_NORMATIVA = re.compile(
    r"\bcu[aá]nt[oa]s\s+(\w+\s+){1,3}(debo|debe|debemos|tengo\s+que|necesito|se\s+piden|piden|"
    r"lleva|llevan|pongo|poner)\b|\bde\s+qu[eé]\s+a[nñ]os?\b|\bqu[eé]\s+tan\s+antigu|"
    r"\bqu[eé]\s+(norma|formato|estilo)\s+(de\s+)?(cita|citas|referencias|citaci[oó]n)",
    re.I,
)


# Preguntas TEÓRICAS («¿qué es el alfa de Cronbach?», «¿para qué sirve la matriz de
# consistencia?», «¿cuál es la diferencia entre…?»). Las palabras técnicas las
# mandaban a un panel que GENERA el apartado del proyecto: a «¿qué es el alfa de
# Cronbach?» le devolvía una operacionalización con una variable inventada.
_RE_TEORICA = re.compile(
    r"^\s*¿?\s*(y\s+)?(qu[eé]\s+(es|son|significa|significan|quiere\s+decir)\b|para\s+qu[eé]\s+sirve|"
    r"cu[aá]ndo\s+(se\s+usa|uso|se\s+aplica|aplico|debo\s+usar|conviene)|"
    r"(cu[aá]l\s+es\s+la\s+|qu[eé]\s+)diferencia|en\s+qu[eé]\s+consiste|c[oó]mo\s+funciona|"
    r"qu[eé]\s+tipos?\s+de\s+\w+\s+(hay|existen))",
    re.I,
)


# Fragmento PEGADO por el estudiante («Mi título es: …», «Este es mi problema: …»).
# Su contenido no es el pedido: «Sistema web para MEJORAR la gestión…» o «¿De qué
# manera un sistema web MEJORA…?» traen verbos que el enrutador tomaba por órdenes,
# y «mi título es: … ¿está bien planteado?» terminaba en el panel de planteamiento,
# que le generaba un problema completo en vez de valorar su título.
_RE_INTRO_PEGADO = re.compile(
    r"\b(mis?|nuestros?|nuestras?|(este|esta)\s+es\s+mi|(estos|estas)\s+son\s+mis|tengo\s+(este|esta|estos|estas))"
    r"\s+(\w+\s+){0,2}?(t[ií]tulos?|problemas?|preguntas?|objetivos?|hip[oó]tesis|justificaci[oó]n|"
    r"variables?|poblaci[oó]n|realidad\s+problem[aá]tica)(\s+(general|espec[ií]fic\w*|central))?"
    r"\s*(es|son|dice|queda|qued[oó])?\s*:",
    re.I,
)

# Tolera «hipostesis», «hipotesis», «hipótesiis»: con la grafía mal escrita la
# excepción de hipótesis no saltaba y «y las hipostesiis cómo serían…» acababa
# en el panel de planteamiento, que le devolvía un problema lleno de huecos.
_RE_HIPOTESIS = re.compile(r"\bhip[oó]s?te?s\w*", re.I)

# Pedido EXPLÍCITO de producir la cadena del planteamiento. Mencionar los objetivos
# («deben ser tantas como objetivos específicos») no es pedirlos.
_RE_PRODUCIR_CADENA = re.compile(
    r"\b(redact|plante|formul|gener|propon|prop[oó]n|arm|constru|elabor|escrib|corrig|corrij|mejor)\w*\s+"
    r"(\w+\s+){0,3}(problema|preguntas?|objetivos?)|\bd[aá]me\s+(\w+\s+){0,3}(problema|preguntas?|objetivos?)",
    re.I,
)


# Pedido de EXPLICACIÓN: cómo se hace o qué lleva una parte del proyecto («la base
# teórica, ¿cómo la redacto?, ¿qué consideraciones debo tener?», «¿al final de los
# antecedentes va la síntesis o no?», «¿se cita?»). Lo responde el conversador con
# los libros y los criterios fijos. Los paneles GENERAN el apartado: a «¿cómo se
# redacta la base teórica?» el de antecedentes le contestó tres veces seguidas con
# cadenas de búsqueda de antecedentes, y el estudiante acabó escribiendo en mayúsculas.
#
# GENERAL: la forma impersonal o de consulta de forma; va siempre al conversador.
_RE_EXPLICACION_GENERAL = re.compile(
    r"(\bcon?sideraci[oó]n\w*|\bexpl[ií]c\w*|"
    r"\bc[oó]mo\s+(es\s+que\s+)?se\s+(redact|escrib|hac|elabor|estructur|desarroll|organiz|cit|"
    r"present|plante|formul|llen|arm|determin|defin|escog|elig|ordena|divid)\w*|"
    r"\bqu[eé]\s+(debe|deber[ií]a|tiene\s+que|tienen\s+que|deben|deber[ií]an)\s+(contener|llevar|incluir|tener|ir|abarcar)|"
    r"\bqu[eé]\s+(va|van|lleva|llevan|contiene|se\s+pone|se\s+coloca|se\s+incluye)\s+en\b|"
    r"\bse\s+(debe|deber[ií]a|tiene\s+que|puede|suele)\s+(colocar|poner|incluir|agregar|a[nñ]adir|citar|usar|redactar)|"
    r"\b(debo|tengo\s+que|hay\s+que|necesito)\s+(citar|colocar|poner|incluir)\b|\bse\s+cita\b|"
    r"\bextensi[oó]n\b|\bextexi[oó]n|\bcu[aá]nt[oa]s?\s+(p[aá]ginas|caras|hojas|palabras|l[ií]neas|p[aá]rrafos)\b|"
    r"\b(est[aá]|estar[ií]a)\s+bien\s+que\b|\bes\s+(necesario|obligatorio|coherente|correcto)\s+(que|poner|colocar|incluir|citar)\b|"
    r"\bo\s+no\s*[?¿.!=]*\s*$|\bdiferencia\s+entre\b|\bforma\s+de\s+redac|\bqu[eé]\s+se\s+hace\b|"
    # «¿De dónde deben ser mis antecedentes?», «¿internacionales o nacionales?»: es la
    # pregunta por el consejo (de preferencia internacionales), no un pedido de búsqueda.
    r"\bde\s+d[oó]nde\s+(\w+\s+){0,2}(deben|debe|deber[ií]an?|tienen\s+que|tiene\s+que)\s+ser\b|"
    r"\b(internacional|nacional|local)(es)?\s+o\s+(internacional|nacional|local)(es)?\b|"
    r"\b(deben|debe|tienen\s+que)\s+ser\s+(solo\s+)?(internacional|nacional|local)\w*)",
    re.I,
)
# PERSONAL: «¿cómo redacto…?», «¿cómo debo hacer…?». Con proyecto o título a la vista
# puede ser un pedido de que se lo arme (lo atienden los paneles, como antes); sin
# nada sobre qué trabajar, el panel solo devolvía plantillas con huecos.
_RE_EXPLICACION_PERSONAL = re.compile(
    r"(\bc[oó]mo\s+(debo|deber[ií]a|debemos|tengo\s+que|tenemos\s+que|hay\s+que|puedo|podr[ií]a)\s+"
    r"(redact|escrib|hac|elabor|estructur|desarroll|organiz|plante|formul|llen|arm|determin|defin|escog|eleg|cre)\w*|"
    r"\bc[oó]mo\s+(la|lo|las|los)\s+(redact|escrib|hag|elabor|estructur|desarroll|organiz|plante|formul|llen|arm)\w*|"
    r"\bc[oó]mo\s+(redacto|escribo|hago|elaboro|estructuro|desarrollo|organizo|planteo|formulo|lleno|armo|"
    r"determino|defino|escojo|elijo|creo)\b|"
    r"\bc[oó]mo\s+(ser[ií]a|ser[ií]an|deber[ií]a\s+ser|debe\s+ser)\b|\bno\s+s[eé]\s+c[oó]mo\b)",
    re.I,
)
# Órdenes de PRODUCIR algo concreto: esas sí van a su panel aunque digan «cómo».
# «se redacta», «se elabora»… son impersonales, no órdenes (de ahí el lookbehind).
_RE_PRODUCIR = re.compile(
    r"\b(?<!\bse\s)(redact(a|ame|alo|ala|alos|alas)|h[aá]z(me|lo|la|los|las)|gener(a|ame)|arm(a|ame)|elabor(a|ame)|"
    r"escr[ií]b(e|eme)|prop[oó]n(me)?|constr[uú]ye(me)?|compl[eé]ta(me)?|b[uú]sca(me)?|"
    r"c[oó]mo\s+(busco|buscar|encuentro|encontrar)|d[oó]nde\s+(busco|buscar|encuentro|encontrar)|"
    r"cadenas?\s+de\s+b[uú]squeda)\b",
    re.I,
)

# El estudiante RECLAMA que la respuesta anterior no era lo que pidió («¿por qué
# sigues dándome antecedentes? Estoy preguntando por la base teórica»). Volver a
# enrutar por palabras clave repetía el mismo panel —el reclamo nombra lo que NO
# quiere—; lo atiende el conversador, que ve el hilo y corrige el rumbo.
_RE_RECLAMO = re.compile(
    r"(\bpor\s*qu[eé]\s+(me\s+)?(sigues|vuelves|repites|insistes|das|est[aá]s\s+dando)\b|"
    r"\b(estoy|te\s+estoy|te)\s+(pidiendo|preguntando|consultando)\b|"
    r"\bno\s+te\s+(ped[ií]|pregunt[eé]|estoy\s+pidiendo|estoy\s+preguntando)\b|"
    r"\bno\s+(es|era)\s+(eso|lo\s+que\s+(te\s+)?(ped[ií]|pregunt[eé]))|\beso\s+no\s+(es|era)\s+lo\s+que\b|"
    r"\bno\s+me\s+(entiendes|entendiste|est[aá]s\s+entendiendo)\b|"
    r"\b(otra\s+vez|de\s+nuevo)\s+(lo\s+mismo|con\s+(eso|lo\s+mismo))\b|\bme\s+(sigues|vuelves\s+a)\s+dar\w*)",
    re.I,
)

# Apartados del PROYECTO que nunca son elegir tema. El enrutador LLM clasificó como
# «ideación» una duda sobre la operacionalización y la respuesta salió con la
# evidencia de títulos del repositorio pegada al final.
_RE_APARTADO_PROYECTO = re.compile(
    r"(opera(ci[oó]n)?ali[sz]aci|hip[oó]s?te?s\w*|antecedent|bases?\s+te[oó]ric|marco\s+te[oó]ric|"
    r"supuestos?\s+b[aá]sic|limitaci[oó]n(es)?\s+del\s+estudio|matriz\s+de\s+consistencia|"
    r"definici[oó]n\s+(de\s+t[eé]rminos|conceptual|operacional)|s[ií]ntesis\s+y\s+brecha)",
    re.I,
)


# Líneas que son pedidos o preguntas, no títulos: «LA BASE TEÓRICA, CÓMO LA REDACTO…»
# se tomaba por el título del proyecto (línea larga sin «?») y el panel armaba la
# búsqueda bibliográfica con «base teórica, redacción, consideraciones» como variables.
# Las interrogativas van SOLO con tilde: «como», «que» y «donde» sin tilde son
# corrientes en un título («… como herramienta para…», «… que mejora…»).
_RE_NO_ES_TITULO = re.compile(
    r"\b(c[óÓ]mo|qu[éÉ]|cu[áÁ]l|cu[áÁ]ndo|d[óÓ]nde|debo|deber[ií]a|debemos|deben|necesito|nesecito|"
    r"ayud\w*|expl[ií]c\w*|por\s*qu[eé]|porque|puedes|podr[ií]as|quiero|quisiera|tengo|tenemos|estoy|"
    r"estamos|hola|gracias|dime|dame|redact\w*|revis\w*|corrig\w*|consideraci\w*|cosideraci\w*|mi|mis|me|"
    r"te|sigues|pidiendo|preguntando|docente|profesor|asesor|okey|ok|bueno|entonces)\b",
    re.I,
)
_RE_PARECE_TITULO = re.compile(
    r"\b(sistema|modelo|aplicaci[oó]n|implementaci[oó]n|desarrollo|propuesta|plataforma|herramienta|"
    r"algoritmo|influencia|efecto|impacto|relaci[oó]n|an[aá]lisis|dise[nñ]o|evaluaci[oó]n|optimizaci[oó]n|"
    r"mejora\w*|gesti[oó]n|automatizaci[oó]n|predicci[oó]n|detecci[oó]n|identificar|identificaci[oó]n|"
    r"inteligencia|business|chatbot|web|m[oó]vil|software|aprendizaje|framework|arquitectura|"
    r"dashboard|tablero|anal[ií]tica)\b",
    re.I,
)
_RE_TITULO_EXPLICITO = re.compile(
    r"t[ií]tulo(\s+de\s+(mi\s+|la\s+)?(tesis|proyecto|investigaci[oó]n))?\s*(es|ser[ií]a|queda|qued[oó])?\s*:?\s*"
    r"[«\"“']\s*(?P<entre>[^«»\"“”\n]{25,300})[»\"”']|"
    r"t[ií]tulo(\s+de\s+(mi\s+|la\s+)?(tesis|proyecto|investigaci[oó]n))?\s*(es|ser[ií]a|queda|qued[oó])?\s*:\s*"
    r"(?P<libre>[^\n]{25,300})",
    re.I,
)


def titulo_en_texto(texto: str) -> str:
    """El título de tesis que el estudiante escribió en un mensaje, o "".

    Primero el título presentado como tal («mi título es: "…"»); si no, una línea
    que tenga forma de título —no de pregunta ni de pedido—."""
    texto = texto or ""
    m = _RE_TITULO_EXPLICITO.search(texto)
    if m:
        t = (m.group("entre") or m.group("libre") or "").strip(" .\"'«»“”")
        t = re.split(r"\s+[¿?]|\s+y\s+el\s+problema|\s*\n", t)[0].strip(" .\"'«»“”")
        if len(t) >= 25:
            return t[:300]
    for linea in texto.split("\n"):
        limpio = linea.strip(" .\"'«»“”-*")
        if not (40 < len(limpio) < 300) or "?" in limpio or "¿" in limpio:
            continue
        if _RE_NO_ES_TITULO.search(limpio) or not _RE_PARECE_TITULO.search(limpio):
            continue
        return limpio
    return ""


def _hay_tema(historial: list[dict] | None, mensaje: str) -> bool:
    """¿Hay un título de tesis a la vista (en el mensaje o en lo que escribió antes)?"""
    candidatos = [mensaje] + [
        t.get("contenido", "") for t in (historial or []) if t.get("rol") == "user"
    ]
    return any(titulo_en_texto(c) for c in candidatos)


def es_pedido_de_explicacion(
    mensaje: str, hay_documento: bool = False, historial: list[dict] | None = None,
) -> bool:
    """¿Pide que le expliquen cómo se hace o qué lleva una parte, sin pedir que se la produzcan?"""
    pedido = parte_pedido(mensaje)
    if _RE_PRODUCIR.search(pedido) or (hay_documento and _RE_ACCION_EVAL.search(pedido)):
        return False
    if _RE_EXPLICACION_GENERAL.search(pedido):
        return True
    return bool(
        _RE_EXPLICACION_PERSONAL.search(pedido)
        and not hay_documento and not _hay_tema(historial, mensaje)
    )


# El panel de antecedentes le pidió su título o tema para armar la búsqueda: la
# respuesta siguiente («mi título es: …») continúa ESE pedido. Sin esto la
# contestaba el conversador, que armó cadenas con «Peru» en la búsqueda
# internacional —justo lo que el panel prohíbe—.
_RE_PIDIO_TEMA = re.compile(
    r"Para prepararte la búsqueda de (tus antecedentes|las fuentes de tu base teórica)"
)


def responde_pedido_de_tema(mensaje: str, historial: list[dict] | None) -> bool:
    """¿Contesta con su título o tema al pedido del panel de antecedentes?"""
    ultima_ia = next(
        (t.get("contenido", "") for t in reversed(historial or []) if t.get("rol") != "user"), ""
    )
    if not _RE_PIDIO_TEMA.search(ultima_ia or ""):
        return False
    if titulo_en_texto(mensaje):
        return True
    pedido = parte_pedido(mensaje)
    return len(pedido.strip()) >= 30 and not _RE_PREGUNTA.search(pedido)


def es_reclamo(mensaje: str) -> bool:
    """¿Reclama que la respuesta anterior no correspondía a lo que pidió?"""
    return bool(_RE_RECLAMO.search(mensaje or ""))


def separar_pegado(mensaje: str) -> tuple[str, str] | None:
    """(introducción, pedido) si el mensaje trae un fragmento pegado; None si no.
    «Mi título es: X. ¿Está bien planteado?» → («Mi título es:», «¿Está bien planteado?»).
    El pedido queda vacío si no pide nada aparte del fragmento."""
    mensaje = mensaje or ""
    m = _RE_INTRO_PEGADO.search(mensaje)
    if not m:
        return None
    intro, resto = mensaje[:m.end()], mensaje[m.end():].strip()
    # Pregunta final separada del fragmento: el último «¿» que no abre el propio texto.
    ult = resto.rfind("¿")
    if ult > 0:
        return intro, resto[ult:]
    if ult == 0 and resto.count("¿") == 1 and len(resto) <= 120:
        return intro, resto          # el «fragmento» es solo la pregunta
    # Sin «¿»: la última oración corta es el pedido («… Mejóralo.»).
    oraciones = [o for o in re.split(r"(?<=[.!?])\s+", resto) if o]
    if len(oraciones) > 1 and len(oraciones[-1]) <= 120:
        return intro, oraciones[-1]
    return intro, ""


def parte_pedido(mensaje: str) -> str:
    """El mensaje sin el fragmento pegado: la introducción («Mi título es:») más el
    pedido («¿Está bien planteado?»). Si no hay fragmento, el mensaje tal cual."""
    partes = separar_pegado(mensaje)
    return f"{partes[0]} {partes[1]}".strip() if partes else (mensaje or "")


def es_consulta_de_contenido(mensaje: str) -> bool:
    """¿Pregunta por lo que ya escribió, sin pedir que se genere o evalúe nada?"""
    mensaje = parte_pedido(mensaje)
    if _RE_QUE_FALTA.search(mensaje or "") and not _RE_ACCION_EVAL.search(mensaje or ""):
        return True
    if _RE_NORMATIVA.search(mensaje or "") and not _RE_PIDE_ACCION.search(mensaje or ""):
        return True
    return bool(
        _RE_CONSULTA_DOC.search(mensaje or "")
        and not _RE_PIDE_ACCION.search(mensaje or "")
        and not _RE_ACCION_EVAL.search(mensaje or "")
    )


_PROMPT_SISTEMA = """Eres el enrutador de un sistema multiagente que revisa proyectos de tesis.
Tu ÚNICA tarea es clasificar el mensaje del estudiante. Responde SOLO con JSON válido:

{{
  "modo": "completo" | "secciones" | "conversacion" | "ideacion" | "planteamiento",
  "secciones": ["nombre exacto de la lista"]
}}

Reglas:
- "ideacion": el estudiante AÚN NO TIENE tema o título de tesis, o lo está eligiendo. Incluye tanto
  el pedido inicial («no sé qué tema hacer», «dame ideas de título», «no sé por dónde empezar») como
  sus RESPUESTAS dentro de esa conversación: si en el historial MentorIA le acaba de plantear
  problemas, áreas o títulos candidatos y el estudiante contesta con sus intereses, un área, una
  empresa o una lista de ideas sueltas (p. ej. «1. sistemas agénticos 2. revísalo tú 3. automatizar
  registros en el sector agrario»), eso SIGUE siendo "ideacion", NO "conversacion". Mientras el hilo
  trate de decidir el tema, el modo es "ideacion".
- "planteamiento": YA TIENE tema o título y pide construir lo que sigue: la realidad problemática,
  la formulación del problema, la pregunta general, las preguntas específicas o los objetivos
  («¿qué sigue?» tras pegar su título, «redacta el problema», «dame la pregunta general y las
  específicas», «ahora los objetivos»). Se distingue de "ideacion" en que aquí YA hay tema: si en el
  mensaje o en el historial aparece un título de tesis, NO es "ideacion", es "planteamiento".
- "completo": pide revisar/evaluar TODO el proyecto, la tesis entera, una revisión general o los puntos débiles globales.
- "secciones": SOLO cuando hay una ORDEN EXPLÍCITA de evaluar/revisar/corregir/calificar/mejorar/auditar una parte
  concreta (p. ej. «revisa mis objetivos», «evalúa mi operacionalización», «corrige mi población»). Usa SOLO nombres
  EXACTOS de la lista del documento. Máximo 3. Si el estudiante menciona un SUB-TEMA que no es un título exacto pero
  pertenece claramente a una sección de la lista (p. ej. «operacionalización de variables», «variable
  dependiente/independiente» → la sección de Variables; «población y muestra» → la sección de Metodología), elige el
  título de la lista que lo CONTIENE. Si no estás seguro de a qué título pertenece, incluye igual tu mejor candidato.
  ⚠️ Una PREGUNTA o consulta sobre el contenido NO es una orden de evaluar, aunque nombre una sección:
  «¿sabes cuál es mi operacionalización?», «¿qué dice mi marco teórico?», «¿cuál es mi población?»,
  «muéstrame mis objetivos», «¿está bien mi hipótesis?» → eso es "conversacion" (el mentor lo responde sin lanzar la red).
  Considera el HISTORIAL: si antes hablaron de una sección y ahora dice «sí, revísala» o «corrígela», resuélvelo a esa sección.
- "conversacion": saludos, dudas metodológicas, preguntas sobre cómo funciona el sistema, preguntas sobre resultados
  previos, o CUALQUIER cosa que no sea una orden explícita de ejecutar una revisión. Ante la duda, usa "conversacion".
- "mejora": CONTINUIDAD del acompañamiento de redacción. Úsalo cuando el ÚLTIMO turno de MentorIA fue una lista de
  PREGUNTAS para poder redactar algo, o una propuesta de IDEAS/temas, y el mensaje actual del estudiante CONTINÚA ese
  hilo: responde a esas preguntas, elige una de las ideas, aporta su tema, o dice que no sabe qué hacer.
  ⚠️ Esto vale AUNQUE el mensaje no traiga ningún verbo y sea muy corto o una simple enumeración
  (p. ej. «1. deep learning 2. cáncer de piel», «la segunda», «en una clínica de Trujillo», «no sé, lo que sea»).
  Esos mensajes NO son "conversacion": son la respuesta que el mentor estaba esperando para poder seguir.

SECCIONES DEL DOCUMENTO:
{toc}

ÚLTIMOS TURNOS DE LA CONVERSACIÓN (para resolver referencias como «esa sección», «sí», «la anterior»):
{historial}
"""


# Marcas de que el ÚLTIMO turno del mentor dejó el hilo abierto esperando respuesta:
# una tanda de preguntas (elicitación) o una propuesta de ideas de tema (ideación).
_RE_MARCA_IDEACION = re.compile(
    r"artefacto\s+propuesto|riesgo\s+principal|variable\s+dependiente|subl[íi]nea|"
    r"acceso\s+real|l[íi]neas?\s+de\s+proyecto|de\s+d[óo]nde\s+saldr[íi]an",
    re.I,
)


def _hilo_abierto(historial: list[dict] | None) -> bool:
    """True si el mentor dejó una pregunta/propuesta pendiente en su último turno.

    Se mira SOLO el último turno del asistente: es el que el estudiante está
    respondiendo ahora.
    """
    ultimo = next(
        (t for t in reversed(historial or []) if t.get("rol") == "assistant"), None
    )
    if not ultimo:
        return False
    texto = (ultimo.get("contenido") or "")
    return texto.count("?") >= 3 or bool(_RE_MARCA_IDEACION.search(texto))


def _historial_breve(historial: list[dict] | None) -> str:
    """Historial para el enrutador, SIN mutilar los turnos del estudiante.

    Recortar al estudiante a 200 caracteres era lo que rompía la clasificación:
    cuando respondía a una tanda de preguntas («1. …Respuesta: …» × 7), lo único
    que llegaba aquí era el arranque de la primera pregunta, así que parecía que
    no había contestado. Los turnos del mentor sí se recortan: son largos,
    repetitivos y solo sirven para saber a qué está respondiendo.
    """
    if not historial:
        return "(sin turnos previos)"
    lineas = []
    for t in historial[-8:]:
        es_alumno = t.get("rol") == "user"
        rol = "Estudiante" if es_alumno else "MentorIA"
        contenido = (t.get("contenido") or "").strip().replace("\n", " ")
        if contenido:
            lineas.append(f"{rol}: {contenido[:1500 if es_alumno else 200]}")
    return "\n".join(lineas) or "(sin turnos previos)"


def interpretar_mensaje(
    mensaje: str,
    toc_nombres: list[str],
    contexto_previo: str = "",
    hay_documento: bool = False,
    historial: list[dict] | None = None,
    vector_store=None,
) -> dict:
    toc_txt = "\n".join(f"- {n}" for n in toc_nombres) if toc_nombres else "(sin documento cargado)"

    # META-PREGUNTA («¿sabes lo que te dije?», «ya te dije mi problema», «me
    # preguntas lo mismo»). Va derecho al mini-grafo, que la resuelve devolviendo
    # la ficha del estudiante sin pasar por ningún LLM. No se clasifica con el
    # modelo a propósito: es el turno en el que el estudiante ya desconfía, y
    # equivocarse ahí es lo que hace que abandone.
    from .ficha import es_meta_pregunta

    if es_meta_pregunta(mensaje):
        logger.info("[intent] Meta-pregunta («¿ya te lo dije?») → mini-grafo, ruta memoria")
        return {"modo": "mejora", "secciones": []}

    llm = llm_rapido(temperatura=0.0)
    try:
        respuesta = llm.invoke([
            SystemMessage(content=_PROMPT_SISTEMA.format(
                toc=toc_txt, historial=_historial_breve(historial),
            )),
            HumanMessage(content=mensaje),
        ])
        data = extraer_json(respuesta.content)
    except Exception as exc:
        logger.error(f"[intent] Error LLM: {exc}")
        data = {}

    modo = data.get("modo")
    if modo not in ("completo", "secciones", "conversacion", "ideacion", "planteamiento",
                    "antecedentes", "metodologia"):
        msg = mensaje.lower()
        if any(p in msg for p in ("todo", "completo", "completa", "entera", "general")) and hay_documento:
            modo = "completo"
        else:
            modo = "conversacion"

    # Las reglas miran el PEDIDO, no el fragmento que pegó (ver parte_pedido).
    pedido = parte_pedido(mensaje)

    # Respuesta al «pégame tu título» del panel de antecedentes: vuelve a ese panel.
    if responde_pedido_de_tema(mensaje, historial):
        logger.info("[intent] Título/tema en respuesta al panel de antecedentes → 'antecedentes'")
        return {"modo": "antecedentes", "secciones": []}

    # CONSULTA sobre su propio texto: la responde el conversador, nunca un panel.
    normativa = bool(
        (_RE_NORMATIVA.search(pedido) or _RE_TEORICA.search(pedido))
        and not _RE_PIDE_ACCION.search(pedido) and not _RE_ACCION_EVAL.search(pedido)
    )
    # Sin documento también: «Mi problema es: … ¿está bien planteado?» pide un juicio
    # sobre el texto que pegó en el mensaje, no un planteamiento nuevo.
    if es_consulta_de_contenido(pedido) or normativa:
        logger.info("[intent] Consulta sobre el contenido del proyecto → 'conversacion'")
        return {"modo": "conversacion", "secciones": []}

    # RECLAMO sobre la respuesta anterior: lo atiende el conversador, que ve el hilo.
    # Salvo que traiga una orden concreta («no es eso, revisa mis objetivos»).
    if (es_reclamo(pedido) and not _RE_PRODUCIR.search(pedido)
            and not (hay_documento and _RE_ACCION_EVAL.search(pedido))):
        logger.info("[intent] Reclamo sobre la respuesta anterior → 'conversacion'")
        return {"modo": "conversacion", "secciones": [], "reclamo": True}

    # EXPLICACIÓN de cómo se hace o qué lleva una parte: la da el conversador.
    if es_pedido_de_explicacion(mensaje, hay_documento, historial):
        logger.info("[intent] Pedido de explicación (cómo se hace / qué lleva) → 'conversacion'")
        return {"modo": "conversacion", "secciones": []}

    # FRAGMENTO PEGADO: los paneles se deciden SOLO por lo que pide después del texto
    # («¿qué sigue?», «dame las preguntas específicas»); la introducción («Mi objetivo
    # general es:») nombra el tema, no el pedido. Si solo quiere que se valore o mejore
    # ese texto, lo hace el conversador sobre lo que pegó: los paneles trabajan sobre
    # la sección del documento, no sobre el texto del mensaje.
    partes = separar_pegado(mensaje)
    if partes is not None:
        cola = partes[1]
        if _RE_METODOLOGIA.search(cola):
            return {"modo": "metodologia", "secciones": []}
        if _RE_ANTECEDENTES.search(cola):
            return {"modo": "antecedentes", "secciones": []}
        if _RE_PLANTEAMIENTO.search(cola) or (not cola and modo == "planteamiento" and not hay_documento):
            return {"modo": "planteamiento", "secciones": []}
        logger.info("[intent] Fragmento pegado con pedido de valoración/mejora → 'conversacion'")
        return {"modo": "conversacion", "secciones": []}

    # METODOLOGÍA antes que antecedentes y planteamiento: es la más específica.
    if (_RE_METODOLOGIA.search(pedido)
            and not (hay_documento and _RE_ACCION_EVAL.search(pedido))):
        logger.info("[intent] Petición metodológica → modo 'metodologia'")
        return {"modo": "metodologia", "secciones": []}

    # ANTECEDENTES va antes que planteamiento: «redacta mis antecedentes» acababa
    # en el panel de planteamiento, que le devolvía la realidad problemática.
    if (_RE_ANTECEDENTES.search(pedido)
            and not (hay_documento and _RE_ACCION_EVAL.search(pedido))):
        logger.info("[intent] Petición de antecedentes / marco teórico → modo 'antecedentes'")
        return {"modo": "antecedentes", "secciones": []}

    # PLANTEAMIENTO va antes que ideación: quien ya trae título no está eligiendo
    # tema, está construyendo la cadena. Sin esta precedencia, «este es mi título,
    # ¿qué sigue?» caía en ideación y le proponía temas nuevos en vez de avanzar.
    # Las HIPÓTESIS no son parte de esa cadena: «¿qué hipótesis podría plantear?» le
    # devolvía problema, preguntas y objetivos. Las propone el conversador, salvo que
    # pida además producir la cadena («redacta mis objetivos y sus hipótesis»):
    # nombrar los objetivos («tantas hipótesis como objetivos») no es pedirlos.
    if ((modo == "planteamiento" or _RE_PLANTEAMIENTO.search(pedido))
            and not (_RE_HIPOTESIS.search(pedido) and not _RE_PRODUCIR_CADENA.search(pedido))
            and not (hay_documento and _RE_ACCION_EVAL.search(pedido))):
        logger.info("[intent] Petición de planteamiento → modo 'planteamiento'")
        return {"modo": "planteamiento", "secciones": []}

    # Panel de IDEACIÓN. NO exige documento: el estudiante que aún
    # no tiene tema es precisamente el que no puede subir nada, y era el caso peor
    # atendido del sistema. Se activa por petición explícita o porque el turno
    # anterior ya era de ideación y ahora está respondiendo con sus intereses.
    # El enrutador LLM decide la continuación del hilo —«1. sistemas agénticos
    # 2. revísalo tú…» sigue siendo ideación aunque no nombre la palabra «tema»—,
    # porque una regex sobre la prosa del asistente resultó demasiado frágil: no
    # reconocía sus propias respuestas y el turno siguiente volvía al chat genérico.
    # La regex se conserva como atajo para el pedido explícito.
    # Una duda sobre un apartado del proyecto (operacionalización, hipótesis,
    # antecedentes…) no es elegir tema aunque el enrutador LLM lo crea.
    _ideando = bool(_RE_IDEACION.search(pedido)) or (
        modo == "ideacion" and not _RE_APARTADO_PROYECTO.search(pedido)
    )
    if not _ideando and not hay_documento and historial:
        ultima_ia = next(
            (t.get("contenido", "") for t in reversed(historial) if t.get("rol") != "user"), ""
        )
        if _RE_IDEACION_EN_CURSO.search(ultima_ia) and not _RE_PREGUNTA.search(pedido):
            _ideando = True
            logger.info("[intent] Continuación del hilo de ideación (marca en la respuesta previa)")

    # El verbo de evaluar solo cancela la ideación si HAY algo que evaluar. Sin
    # proyecto subido, un «revísalo tú» dentro de una conversación de tema no es
    # una orden de calificar —no hay nada que calificar—, es el estudiante
    # delegando la elección. Sin esta distinción, «1. sistemas agénticos
    # 2. revisa tú 3. …» se salía del panel y volvía al chat genérico.
    if _ideando and not (hay_documento and _RE_ACCION_EVAL.search(pedido)):
        logger.info("[intent] Petición sin tema definido → modo 'ideacion'")
        return {"modo": "ideacion", "secciones": []}

    # Panel de TÍTULO: pide trabajar el título y no una calificación formal.
    # Va ANTES del debate rápido porque el título necesita el panel especializado
    # (límite de palabras, política de delimitación, corpus del repositorio) y el
    # debate genérico lo trataba como una sección cualquiera.
    if (hay_documento
            and _RE_TITULO.search(pedido)
            and _RE_TITULO_ACCION.search(pedido)
            and not _RE_ACCION_EVAL.search(pedido)):
        logger.info("[intent] Petición sobre el título → modo 'titulo' (panel especializado)")
        return {"modo": "titulo", "secciones": []}

    # Mini-grafo de debate rápido: petición de MEJORAR/CORREGIR/REDACTAR/lineamientos
    # SIN orden explícita de evaluar (p. ej. «corrige mi planteamiento», «¿cómo mejoro
    # mi título?», «dame lineamientos para…»). No lanza la red grande; requiere documento.
    # Si además pide evaluar («revisa y mejora»), gana la evaluación → sigue al grafo grande.
    if _RE_MEJORA.search(pedido) and not _RE_ACCION_EVAL.search(pedido):
        logger.info(
            f"[intent] Petición de redacción/mejora → modo 'mejora' (mini-grafo multiagente; "
            f"documento={'sí' if hay_documento else 'no'})"
        )
        return {"modo": "mejora", "secciones": []}

    # Red de seguridad: una PREGUNTA sin verbo explícito de evaluación nunca debe
    # lanzar la red (p. ej. «¿sabes cuál es mi operacionalización?» es una consulta,
    # no una orden de calificar). El conversador la responde desde la tesis por RAG.
    if (modo in ("secciones", "completo")
            and not _RE_ACCION_EVAL.search(pedido)
            and _RE_PREGUNTA.search(pedido)):
        logger.info("[intent] Pregunta sin orden de evaluar → conversacion (guarda)")
        modo = "conversacion"

    raw_secciones = data.get("secciones") or []

    # Resuelve CADA pedido por separado: si es un título exacto del TOC se usa tal
    # cual; si es un sub-concepto que no aparece literal en el índice (p. ej.
    # «operacionalización de variables», «matriz de consistencia»), se ubica por RAG
    # dentro de la sección que lo contiene. Antes el RAG solo entraba si NINGÚN pedido
    # matcheaba exacto, así que pedir «operacionalización Y población» descartaba la
    # operacionalización en cuanto «población» matcheaba un título del índice.
    if modo == "secciones" and raw_secciones:
        from backend.rag import resolver_seccion_semantica
        resueltas: list[str] = []
        for guess in raw_secciones:
            if guess in toc_nombres:
                sec = guess
            elif vector_store is not None:
                sec = resolver_seccion_semantica(vector_store, guess, toc_nombres)
            else:
                sec = None
            if sec and sec not in resueltas:
                resueltas.append(sec)
        secciones = resueltas[:3]
        if secciones:
            logger.info(f"[intent] Secciones resueltas (exactas + RAG) → {secciones}")
    else:
        secciones = []

    if modo == "secciones" and not secciones:
        modo = "completo" if hay_documento else "conversacion"

    # Sin documento no se puede revisar: el conversador se encarga de orientar/pedir el PDF.
    if modo != "conversacion" and not hay_documento:
        modo = "conversacion"

    return {"modo": modo, "secciones": secciones}


_PALABRAS_VACIAS = {"de", "del", "la", "las", "los", "el", "y", "e", "en", "con", "para", "por", "a"}


# Primeras palabras que no identifican una sección por sí solas («marco» vale para
# el histórico y el teórico; «tipo», «método»… se repiten en varias).
_RAICES_GENERICAS = {"marco", "tipo", "metodo", "diseno", "tecnic", "recurs", "invest", "proced"}


def _raiz(palabra: str) -> str:
    """Raíz corta para que «objetivos»/«objetivo» o «referencias»/«referencia» coincidan."""
    return palabra[:6]


def _nucleo_seccion(nombre: str) -> tuple[str, list[str]]:
    """(prefijo numérico, raíces clave en orden) de un encabezado como «4.2. Método de investigación»."""
    import unicodedata

    m = re.match(r"^\s*(\d+(?:\.\d+)*)", nombre or "")
    texto = unicodedata.normalize("NFKD", nombre or "").encode("ascii", "ignore").decode().lower()
    texto = re.sub(r"^\s*[\d.\s]+", " ", texto)
    raices: list[str] = []
    for w in re.findall(r"[a-z]+", texto):
        if w not in _PALABRAS_VACIAS and len(w) > 2 and _raiz(w) not in raices:
            raices.append(_raiz(w))
    return (m.group(1) if m and "." in m.group(1) else ""), raices


def secciones_mencionadas(mensaje: str, nombres: list[str], estricto: bool = False) -> list[str]:
    """Secciones que el mensaje nombra: por su número («4.2») o por sus palabras clave.

    `estricto` exige todas las palabras clave: es lo que usa el bloqueo de evaluación,
    donde un falso positivo le negaría una revisión al estudiante.
    """
    import unicodedata

    msg = unicodedata.normalize("NFKD", mensaje or "").encode("ascii", "ignore").decode().lower()
    raices_msg = {_raiz(w) for w in re.findall(r"[a-z]+", msg) if len(w) > 2}
    halladas = []
    for nombre in nombres or []:
        prefijo, clave = _nucleo_seccion(nombre)
        por_numero = bool(prefijo) and re.search(rf"(?<![\d.]){re.escape(prefijo)}(?![\d])", msg)
        comunes = set(clave) & raices_msg
        por_palabras = bool(clave) and (
            comunes == set(clave)
            or (len(clave) >= 3 and len(comunes) >= 2)
            # «mis referencias» → «6. REFERENCIAS BIBLIOGRÁFICAS»: basta la palabra
            # que da nombre a la sección, si no es genérica.
            or (not estricto and len(clave) <= 2 and clave[0] in comunes
                and clave[0] not in _RAICES_GENERICAS)
        )
        if por_numero or por_palabras:
            halladas.append(nombre)
    return halladas
