# Notas para el autor sobre el borrador del artículo

Todo se construyó a partir de **Informe de Tesis v14** (`Informe_de_Tesis_-_v14.docx`) siguiendo
`00_lineamientos_imrad.md`. La selección de revista está en `seleccion_revista.md`.

## 1. Entregables en esta carpeta

| Archivo | Qué es | Para qué revista |
|---|---|---|
| `latex/main_es.pdf` (fuentes `latex/main_es.tex`, `latex/references.bib`, `figuras/`) | **Manuscrito principal, en español**, formato IEEE (clase IEEEtran, dos columnas, blanco y negro, citas numéricas IEEE, 12 páginas). En inglés quedan solo el título secundario, el *abstract*, los *index terms*, los nombres propios de herramientas y modelos, las siglas internacionales y los títulos originales de las referencias publicadas en inglés. | IEEE-RITA o IEEE Latin America Transactions (ambas aceptan español con plantilla IEEE). |
| `articulo_imrad.md` y `articulo_imrad.docx` | Borrador **en español**, APA 7, con figuras en escala de grises y encabezados en negro. | RIED o Pixel-Bit (ambas en Word). |
| `latex/main.pdf` (fuente `latex/main.tex`, `latex/figures/`) | Versión **en inglés** del mismo manuscrito, formato IEEE Transactions on Learning Technologies (11 páginas). | Solo si se decide traducir: TLT, o ETHE e IJAIED con cambio de plantilla. |
| `figuras/` y `latex/figures/` | Las mismas tres figuras en español e inglés, regeneradas en escala de grises a partir de los datos de la tesis. | Ambas versiones. |
| `seleccion_revista.md` | Respuesta al prompt del curso: 13 revistas Q1/Q2 gratuitas ordenadas por relevancia, descartes por costo, recomendación y checklist de envío. | Entrega del curso. |
| `00_lineamientos_imrad.md` | Reglas de Codina (2022) y del curso, mapa tesis→artículo y checklist general. | Referencia. |

## 2. Decisiones tomadas

| Decisión | Elección | Motivo |
|---|---|---|
| Idioma | **Español** en el manuscrito principal | Es el idioma del artículo. En un artículo en español con formato IEEE se mantienen en inglés, por convención de las revistas bilingües (IEEE-RITA, RIED): el título secundario, el *abstract* y los *index terms* (además del resumen y las palabras clave en español); los nombres propios de herramientas y modelos (MentorIA, LangGraph, gpt-4.1, ChatGPT, Python, pandas, Seaborn, ScholarOne); las siglas internacionales (LLM, TRL, ORCID, CC BY, APC); y los títulos de las referencias publicadas en inglés, que nunca se traducen. Los nombres de pruebas y estadísticos van en su forma española (d de Cohen, g de Hedges, U de Mann-Whitney, kappa de Fleiss). |
| Formato principal | Clase IEEEtran con `babel` español (TABLA, Fig., Referencias, Resumen) | Es la plantilla de IEEE-RITA e IEEE Latin America Transactions, las revistas IEEE que publican en español. La versión en inglés (TLT) se conserva por si se decide traducir. |
| Figuras | Tres, regeneradas en escala de grises con marcadores y trazos distintos por grupo | La revista no acepta color; las figuras originales de la tesis eran azul y naranja. La Figura 11 del informe se redibuja solo con medias (el rango intercuartílico no está en las tablas). |
| Tablas | 7 en el PDF IEEE (I a VII), cuatro de ellas a doble columna | Las tablas por proyecto (Tablas 11 a 15 del informe) van a material suplementario. |
| Resumen | Un solo párrafo de unas 245 palabras, con *index terms* | Formato IEEE; la versión en español mantiene el resumen estructurado que piden RIED e Informatics in Education. |
| Antecedentes | 12 de los 15 del informe; se omiten Järvelä et al. (2023), Zeng et al. (2025) y Al Azher et al. (2026) | Solo los directamente relacionados con el objeto y las brechas. |
| Nombres propios | Sin nombres de expertos validadores ni de asesores entrevistados | Práctica habitual en artículos. |
| Modelo de MentorIA | No se nombra el proveedor del modelo del sistema de mentoría | Ver discrepancia en la sección 4. |

Correspondencia entre el informe y el artículo (ambas versiones):

| Informe de tesis (v14) | Artículo |
|---|---|
| Resumen / Abstract | Resumen / Abstract |
| 1.1, 2.1, 2.3, 2.4 | Introducción, párrafos 1 y 2 |
| 3.2 Antecedentes y brechas de 6.1.4, 6.2.6, 6.3.4, 6.4.3, 6.5.5 | Introducción, párrafos 2 a 4 |
| 2.2 Objetivos; 4.2 y 4.3 Hipótesis | Introducción, último párrafo |
| 5.1, 5.3, 5.4 | Diseño |
| 5.5 | Población y muestra |
| 5.2 (TRL) + repositorio del sistema | Intervención |
| 5.6.1 a 5.6.7 | Instrumentos y medidas |
| 5.7, Tabla 10 | Procedimiento |
| 5.8 | Análisis de datos |
| 6.1 | Resultados A (Tabla I condensa Tablas 6 a 9) |
| 6.2.1 a 6.2.3 | Resultados B (Tabla II = Tabla 18) |
| 6.2.4 y 6.2.5 | Resultados C (Tabla III = Tabla 24; Fig. 1 = Figura 8) |
| 6.3 | Resultados D (Fig. 2 = Figura 10) |
| 6.4 | Resultados E (Tabla IV = Tabla 28; Fig. 3 = Figura 11) |
| 6.5 | Resultados F (Tabla V condensa Tablas 29 y 30) |
| 6.6 | Resultados G (Tabla VI = Tabla 32) |
| Discusiones 6.x.4, 6.7 Síntesis de brechas, 2.5 Limitaciones | Discusión (Tabla VII condensa Tabla 33) |
| 7 Conclusiones, 8 Recomendaciones | Conclusión numerada y Future Work |

## 3. Pendientes que solo el autor puede resolver

1. **Confirmar el cuartil en Scimago** de la revista elegida (`https://www.scimagojr.com/journalsearch.php?q=1932-8540` para IEEE-RITA; `q=1138-2783` para RIED; `q=1939-1382` para TLT). El sitio bloquea el acceso automatizado desde este entorno; los cuartiles de `seleccion_revista.md` vienen de las webs de las revistas y de agregadores. Confirmar también el límite de páginas de IEEE-RITA en su guía de autores.
2. **ORCID de los tres autores.** IEEE no permite enviar sin ORCID de todos; en la tesis los de los tesistas están vacíos.
3. **Correo institucional de correspondencia** (en el manuscrito figura el personal) y revisión de las **biografías** de los autores, redactadas de forma genérica.
4. **Descripción de MentorIA.** La tesis v14 no describe la arquitectura; el apartado II-C se redactó desde el repositorio. Confirmar los nombres de los agentes y el modelo: la tesis dice que gpt-4o-mini es uno de los modelos que emplea MentorIA; el README del repositorio dice `llama-3.3-70b-versatile` vía Groq. Debe quedar un solo dato coherente en tesis, artículo y repositorio.
5. **Declaración de uso de IA generativa en la redacción.** IEEE exige declararla en los agradecimientos con cita del sistema; RIED e Informatics in Education también la piden.
6. **Disponibilidad de datos.** Confirmar si el repositorio será público al enviar y dónde se depositarán los datos agregados (Zenodo, OSF o repositorio institucional).
7. **Carta de presentación** para ScholarOne (hay un guion en el checklist de `seleccion_revista.md`).
8. **Figura de arquitectura (opcional).** TLT valora la contribución técnica; un diagrama de la red de agentes y del panel evaluador reforzaría el apartado II-C.
9. **Comité de ética.** Verificar si la Facultad exige mencionar una aprobación formal.

## 4. Discrepancias detectadas en la tesis (corregir antes de la versión final)

- **Secciones completas en la semana 4.** El apartado 5.5 dice 32 descripciones del problema (15 y 17) y 24 justificaciones (14 y 10); el apartado 6.5.1 y la Tabla 29 dicen 33 (16 y 17) y 25 (14 y 11). El artículo usa 33 y 25.
- **Figura 6 del informe** (trayectoria de la calidad): las etiquetas del eje x se solapan. Regenerarla.
- **Tabla 30 del informe:** indicar que la fila "Total" del índice de elaboración incluye ambos grupos.
- **Modelo de MentorIA** (pendiente 4).
- El informe cita una "Figura 1" para el esquema del diseño, pero el esquema está en texto; en el artículo se presentó como notación en línea.

## 5. Estado frente al checklist de `00_lineamientos_imrad.md`

- [x] Título, resumen y palabras clave (inglés en el PDF IEEE; español e inglés en el borrador en español).
- [x] Introducción con objeto, problema, implicancias, justificación, oportunidad, brechas, antecedentes pertinentes y objetivos e hipótesis.
- [x] Métodos con tipo y diseño, población y muestra, instrumentos con validez y confiabilidad, procedimiento, análisis en Python y descripción de los sistemas.
- [x] Resultados con tablas con nota al pie, figuras en escala de grises, normalidad y pruebas de hipótesis.
- [x] Discusión con contraste por antecedente, declaración sobre el estado del arte, cierre de brechas por tipo de aporte, limitaciones y trabajo futuro.
- [x] Conclusiones por objetivo con implicancias.
- [x] Agradecimientos, disponibilidad de datos y código, declaración de IA.
- [x] Referencias en estilo IEEE (PDF) y APA 7 (español); 39 entradas, todas citadas.
- [x] Revista elegida y formato adaptado (IEEE TLT); extensión dentro del límite (11 de 14 páginas).
- [ ] Cuartil confirmado en Scimago y ORCID de todos los autores (pendientes 1 y 2).
