# Evaluación

## Cambio de objetivo a J2 · 2026-10-27
- Por indicación expresa del usuario se utiliza J2, ambas partes, conservando la rama/worktree aislados existentes y el historial de la preparación J4.
- Nuevo comando local evaluacion.preparar: lee registro en modo solo lectura, comprueba SHA-256 completo de ambos originales, FPS/fotogramas/duración y seis fotogramas por vídeo con PTS observado. No carga detectores, ejecuta análisis ni escribe resultados publicados. Exige salida nueva.
- Ejecución real en work/evaluacion-j2/preparacion-inicial-20261027: 5.399 s. Parte 1: 1468.6467 s y 44051 fotogramas; parte 2: 1516.3183 s y 45481 fotogramas. Ambas huellas coinciden con el registro. Muestras temporales decodificadas correctamente; no constituye revisión continua ni validación completa de PTS.
- Referencias iniciales j002-p1.json/j002-p2.json e informe técnico aislados. Cero segundos de cobertura deportiva, sin eventos/negativos/confirmaciones humanas. Línea base actualizada a J2 con huellas/duraciones; métricas y comparación null.
- Faltan actions.json/profiles.json/temporal-candidates.json en las dos raíces registradas, ambas con análisis pendiente; faltan acciones/perfiles también en la raíz antigua. Copia archivada de temporales con procedencia insuficiente excluida de medición. Petición de salidas reales base/nueva documentada en README.
- CLI real de J2 partes 1 y 2: código 2 por actions.json ausente, sin crear informe ni carpeta de salida. No se sustituyen entradas ausentes por listas vacías.
- Seis regresiones nuevas de preparación (sin vídeo/modelos). Suite completa: 280 OK, 9.742 s; 42 pruebas del módulo. git diff --check correcto. Sin commit ni publicación.

## Auditoría independiente · 2026-10-27
- Continuación coordinada: el responsable anterior liberó el módulo. Worktree propio evaluacion-auditoria-j4, rama mod/evaluacion/goles-faltas-j4 desde origin/develop bec337ed; checkout compartido conservado limpio en mod/web/diseno-visual. Sin commits ni publicación en esta intervención.
- Corregida la omisión de shot+outcome=goal y foul_won/foul_committed; conservación de rival/autor desconocido y del papel infractor/receptor para no confundir atribuciones.
- Pendientes/ambiguos separados por tipo, coberturas y secuencias sin cruce entre desarrollo/reserva; referencias sintéticas nunca acreditan aceptación. Procedencia exigida en eventos reales verificados.
- Rutas explícitas de original/acciones/perfiles/temporales/revisión, confirmaciones separadas, salidas nuevas sin sobrescritura; informes con hashes, rutas, versión de Python, tiempo del evaluador y diferencias comparables. Una comparación requiere el mismo evaluador.
- Referencia inicial de software: 14 pruebas previas OK (0.008 s); nueve regresiones nuevas reproducían 7 fallos y 2 errores (0.021 s). Ahora 36 pruebas del módulo incluidas en la suite completa: 274 OK (9.409 s). Pruebas de contratos/IO sintéticas, sin afirmar precisión deportiva ni mejora de velocidad del detector.
- CLI real contra registro original: J4 parte 1 y parte 2 devuelven código 2 (no registradas), sin crear salidas. El registro y biblioteca disponibles solo aportan J2. No se ejecutó análisis, inferencia ni entrenamiento.
- Línea base de ambas partes: cero segundos revisados; duración/huellas/métricas/comparación real null. Pendientes originales MOV, comprobación de PTS/fotogramas, recorrido continuo de ambas partes, anotaciones independientes, reserva y salidas base/nueva con versiones/tiempos. No existen confirmaciones humanas inventadas.

## 2026-10-27
- Formato v1 y ejemplo sintético, sin anotaciones reales inventadas.
- Evaluador de goles/faltas: emparejamiento uno a uno, alcance revisado, pendientes, atribución independiente, etapas separadas y comparación de entradas idénticas.
- Línea base explícitamente pendiente: jornada 4 ausente del registro y biblioteca configurada.
- Pruebas módulo: 14 OK. Suite completa: 252 OK (17.301 s), usando work/visor-env/Scripts/python.exe en lugar del entorno inexistente indicado en PLAN.
- CLI real --round 4 --half 1 con registro original: salida 2, jornada/parte no registrada. No se generaron métricas aparentes.
- Pendiente: revisión continua y clips de jornada 4, anotaciones verificadas, reserva cerrada, resultados de ambas ramas, ejecución real y aceptación. Exportación posterior a revisión humana aún no soportada.
