# [Título del artículo: objeto de estudio + institución + periodo si aplica]

<!--
PLANTILLA IMRAD DEL ARTÍCULO DERIVADO DE LA TESIS
Estado: ESQUELETO. Se llena con la versión de la tesis que entregue el autor.
Los bloques marcados [TESIS] se toman del informe de tesis.
Los bloques marcados [REPO] tienen un borrador basado en el código del repositorio MentorIA-Tesis
y DEBEN confirmarse contra la tesis antes de quedar en el texto final.
Los bloques marcados [AUTOR] requieren una decisión del autor (ver 00_lineamientos_imrad.md §5).
Las reglas de cada sección están en 00_lineamientos_imrad.md.
-->

**Autores:** [AUTOR] Nombre Apellido¹, Nombre Apellido²
**Afiliación:** ¹ Universidad Privada Antenor Orrego, Facultad de Ingeniería, Trujillo, Perú
**Correspondencia:** [AUTOR]
**ORCID:** [AUTOR]

---

## Resumen

<!-- 150-250 palabras. Cuatro movimientos: problema y objetivo · método (tipo, diseño, muestra,
instrumentos) · resultado principal con cifra · conclusión e implicancia. Sin citas. -->

[TESIS] ...

**Palabras clave:** [TESIS] sistemas multiagente; inteligencia artificial generativa; mentoría
académica; proyectos de tesis; rúbrica de evaluación; LangGraph (ajustar a 4-6 términos).

## Abstract

<!-- Traducción fiel del resumen si la revista lo exige. -->

[AUTOR/TESIS] ...

**Keywords:** ...

---

## 1. Introducción

<!-- Orden sugerido (Codina §6; curso):
P1  Objeto de estudio y contexto: elaboración de proyectos de tesis en la facultad; rol del asesor.
P2  Problema: dificultades observadas (situación problemática), con dato o evidencia de la tesis.
P3  Implicancias y justificación: por qué importa resolverlo; oportunidad (IA generativa,
    agentes, rúbrica oficial).
P4-P6 Antecedentes directamente relacionados (3 a 6): qué hicieron, qué hallaron, qué dejaron
    pendiente. Cerrar cada uno señalando la brecha.
P7  Brechas que cubre este estudio (información / experimentación / metodología) y aporte.
P8  Objetivo general y específicos (o preguntas de investigación / hipótesis si existen).
-->

[TESIS] Situación problemática y formulación del problema → párrafos 1-3.

[TESIS] Antecedentes seleccionados (de los 12 del informe, solo los directamente relacionados).

[TESIS] Brechas identificadas y aporte del estudio.

[TESIS] Objetivos. Hipótesis solo si la tesis las formula.

### 1.1 Fundamentos (opcional, solo teorías relevantes)

<!-- Sistemas multiagente con LLM; orquestación supervisor-red; RAG; evaluación con rúbrica;
human-in-the-loop. Máximo dos párrafos o eliminar si la revista no lo pide. -->

[TESIS] ...

---

## 2. Materiales y Métodos

### 2.1 Tipo y diseño de investigación

<!-- Declarar sin forzar: tecnológica/aplicada, descriptiva, pre-experimental, etc.
Si no se manipulan variables, no llamarla experimental. -->

[TESIS] ...

### 2.2 Población, muestra y muestreo

<!-- Unidad de análisis (proyectos de tesis, estudiantes, secciones), tamaño, técnica
(aleatorio, por conveniencia, casuística), criterios de inclusión, consentimiento informado. -->

[TESIS] ...

### 2.3 Variables e indicadores

<!-- Tabla de operacionalización resumida. Solo si la tesis la tiene; no inventar VI/VD. -->

| Variable | Dimensión | Indicador | Instrumento |
|---|---|---|---|
| [TESIS] | | | |

### 2.4 Instrumentos, validez y confiabilidad

<!-- Instrumentos aplicados (rúbrica oficial de 33 ítems, cuestionarios, métricas automáticas),
validación por juicio de expertos y coeficiente de confiabilidad si existe. -->

[TESIS] ...

### 2.5 Sistema propuesto

<!-- [REPO] Borrador a confirmar con la tesis. Resumir en 3-5 párrafos y una figura de arquitectura. -->

[REPO] El sistema es una red multiagente orquestada por un supervisor que decide dinámicamente el
siguiente agente en cada iteración (sin transiciones fijas entre agentes). Los agentes tienen roles
separados: Redactor (propone texto mejorado apoyado en RAG), Auditor (califica los 33 ítems de la
rúbrica oficial con salida tipada), Metodólogo (rigor y coherencia cruzada entre secciones) y
Debate (ronda argumentativa Redactor ↔ evaluadores). Un nodo humano (human-in-the-loop) detiene el
flujo para la decisión del mentor.

[REPO] Componentes: orquestación con LangGraph `StateGraph`; modelo de lenguaje `llama-3.3-70b`
servido por Groq; recuperación aumentada (RAG) dual con ChromaDB (almacén efímero por tesis y
almacén persistente de bibliografía metodológica); embeddings locales; API FastAPI con streaming;
interfaz React; autenticación e historial con Supabase; despliegue en Cloud Run.

[REPO] Decisiones de diseño relevantes para el método: la evaluación es incremental según el
alcance declarado por el estudiante (lo no entregado no se califica); la estructura del documento
se resuelve en cascada (estilos Word → marcadores PDF → encabezados → índice → clasificación
semántica); el documento original es inmutable y las mejoras viven en la memoria RAG.

**Figura 1.** Arquitectura de la red multiagente. [REPO/TESIS: tomar del informe o redibujar]

### 2.6 Procedimiento

<!-- Fases: construcción (POC 1 jerárquico en Python → POC 2 jerárquico con tool-calling →
POC 3 red pura LangGraph → productización), aplicación a la muestra, recolección, análisis. -->

[TESIS/REPO] ...

### 2.7 Procesamiento y análisis de datos

<!-- Herramientas (Python: pandas, scipy). Estadísticos descriptivos. Si hay hipótesis:
Shapiro-Wilk → T de Student o Wilcoxon. Métricas automáticas del evaluador. -->

[TESIS] ...

[REPO] Métricas disponibles en el módulo evaluador del sistema (confirmar cuáles reporta la tesis):
gain score inicial→final según juez LLM, kappa de acuerdo entre evaluadores en el debate, similitud
coseno entre texto inicial y final, ROUGE/BLEU contra texto de referencia, context precision de los
fragmentos recuperados por RAG, y juez LLM con rúbrica por tipo de investigación (cuantitativa,
cualitativa, mixta, tecnológica, innovación).

---

## 3. Resultados

<!-- Abrir con un párrafo: objetivo, instrumentos aplicados, validez y confiabilidad.
Luego una subsección por objetivo específico. Cada tabla con nota al pie.
Si los datos son extensos, muestra representativa e indicarlo en la tabla. -->

[TESIS] Párrafo introductorio.

### 3.1 Resultado para el objetivo específico 1

**Tabla 1.** [Título]
| | | |
|---|---|---|
| | | |
*Nota.* [Descripción de la tabla, fuente e instrumento.]

[TESIS] Lectura del resultado (sin interpretarlo todavía).

### 3.2 Resultado para el objetivo específico 2

...

### 3.n Docimasia de hipótesis (solo si la tesis formula hipótesis)

<!-- Prueba de normalidad (Shapiro-Wilk, n<50) → estadístico, p-valor, decisión.
Prueba paramétrica (T de Student) o no paramétrica (Wilcoxon) → estadístico, p, tamaño de efecto. -->

[TESIS] ...

---

## 4. Discusión

<!-- Por cada resultado:
(a) qué muestra; (b) con qué antecedente coincide o difiere y por qué; (c) si supera o no el estado
del arte, considerando tamaño de muestra y validez interna.
Luego: cierre de brechas (información / experimentación / metodología / parcial), limitaciones y
líneas futuras. -->

[TESIS] Contraste del resultado 1 con antecedentes.

[TESIS] Contraste del resultado 2 con antecedentes.

### 4.1 Cierre de brechas

[TESIS] Brecha 1 → cómo se cubrió (tipo de aporte). Brecha 2 → ...

### 4.2 Limitaciones

[TESIS] Tamaño de muestra, dependencia del proveedor LLM, una sola institución y rúbrica, etc.

---

## 5. Conclusiones

<!-- Una conclusión por objetivo, con su implicancia. Registro asertivo. -->

1. [TESIS] Respecto al objetivo general...
2. [TESIS] Respecto al objetivo específico 1...
3. ...

### 5.1 Recomendaciones (si la revista las admite junto a las conclusiones)

<!-- Orientadas a estudios futuros: mismos datos con otra metodología, otras rúbricas o
universidades, estudios con muestras mayores. Nuevas brechas detectadas. -->

- [TESIS] ...

---

## Agradecimientos

[AUTOR] Asesor, institución, participantes.

## Declaraciones

**Conflicto de intereses:** Los autores declaran no tener conflicto de intereses.
**Uso de inteligencia artificial generativa:** [AUTOR] Declarar si se usó para redacción o edición,
según exija la revista. No se usó para la toma de decisiones de investigación.
**Consentimiento informado:** [TESIS] Si participaron personas.
**Disponibilidad de datos y código:** [AUTOR] Repositorio: https://github.com/Mclever2/MentorIA-Tesis

## Referencias

<!-- Solo las citadas. Estilo de la revista (APA 7 por defecto). Vigencia preferente 3-5 años. -->

[TESIS] ...

## Material de soporte

<!-- Instrumentos, rúbrica de 33 ítems, prompts de los agentes, datos agregados. -->

[TESIS/REPO] ...
