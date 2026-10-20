# Reparación v5 · jornada 2, primera parte

La identificación y las fichas se han mejorado, pero **todavía no existe un análisis completo y fiable de todos los jugadores y las once estadísticas**. Esta versión vuelve a recorrer las detecciones de toda la primera parte, publica los resultados y distingue lo observado de lo desconocido. La segunda parte permanece recibida y pendiente de procesar.

| Comprobación | Antes | v5 |
|---|---:|---:|
| Observaciones con identidad | 36481 | 57769 |
| Jugadores con alguna identidad observada | 10 | 11 |
| Segundos identificados de Busi | 157,9 | 367.0 |
| Segundos proyectados de Busi | 148,4 | 322.1 |
| Estimaciones de acción aceptadas | 2 | 6 |
| Propuestas inciertas de acción | 34 | 66 |

Se identifican 59.1% de las detecciones del equipo naranja y portero. Esta cifra mide cobertura, **no precisión**. Los 11 jugadores tienen observaciones parciales; no están identificados durante todos sus minutos.

## Qué se ha corregido

- Lectura del dorsal completo en 2.189 imágenes y corroboración de su forma impresa. Se han revisado 40 referencias de entrenamiento en imágenes originales. Se guardan con la huella del vídeo y de sus detecciones para evitar aplicarlas a otros jugadores o partidos. Tú no has tenido que identificar esas referencias. No se han registrado goles ni otras acciones como confirmadas durante este trabajo.
- Lecturas recortadas de 99 como 9, 16 como 6 y 41 como 14. El dorsal 9 de Arras tiene una forma que puede parecer 5; se comprobaron imágenes ampliadas antes de cerrar las referencias. Un ejemplo de la trayectoria A926 intercambiaba 7, 16 y 11; ahora se corta con sus pruebas de dorsal.
- Memoria de apariencia con pelo, camiseta, pantalón, medias y botas. Entrenamiento y comprobación separados por trayectoria. Recupera 228 segmentos por apariencia y 23 por continuidad de imagen. Los umbrales comparados con OCR son una comprobación interna, no una evaluación independiente de identidades reales.
- Compensación del movimiento de cámara al enlazar cajas. Una proyección del campo que salta ya no corta por sí sola a una persona que permanece visible. Se evita que dos cajas lleven la misma identidad simultáneamente.
- Contactos de un solo toque con balón de confianza suficiente, y pases a compañeros sin nombre cuando se observan dos personas distintas. Una recuperación usa la identidad y el segundo del jugador que recupera, también al recalcular revisiones.
- Filtro de contactos débiles: se encontró una bota blanca confundida con el balón. Los contactos por debajo de 0,65 no generan estimaciones aceptadas. Se revisaron fotogramas originales de los contactos de mayor confianza; siguen siendo estimaciones, no confirmaciones deportivas.
- Fichas, tablas y CSV con recuentos de detecciones en tramos observados. Un jugador sin observaciones conserva el estado desconocido. Los candidatos se muestran aparte y no se suman a las estimaciones. Se conserva la revisión manual, su historial y su aislamiento por parte/jornada.

## Estadísticas que se muestran ahora

Hay cinco pases estimados y una recuperación estimada. Las otras 66 propuestas son inciertas, algunas sin autor. **Estas seis acciones son una fracción pequeña del partido, no sus totales.** Las faltas, tiros, grandes ocasiones, regates, pérdidas y asistencias requieren mejorar y evaluar sus clasificadores antes de contarlas automáticamente como acciones fiables.

«0 detectados» significa cero acciones aceptadas por el motor en el material atribuible al jugador. No demuestra cero goles, pases, faltas ni otras acciones en el partido. «Sin observación» significa que no hay identidad disponible. Las once tarjetas existen para todos, pero no convierten la ausencia de evidencia en una estadística completa.

La plantilla contiene 16 nombres; no prueba que jugaran los 16. Siguen sin observaciones fiables Lain, Mayora, Fernandito, Alfaro y Resu. No se afirma que no participaran. Los ocho iniciales y cambios siguen sujetos a presencia observable: hay 7 candidatos iniciales y 0 cambios emparejados, sin certificación de la alineación.

Los mapas son planos relativos aproximados, ponderados por tiempo observado. El de Busi reúne 3274 posiciones y 322.1 segundos proyectados. Sus 367 segundos de identidad representan un 25% aproximado del vídeo de la primera parte, no todos sus minutos jugados.

## Verificación

Pasaron 75 pruebas de lógica, persistencia, API, revisión y acumulado. Se verificaron los 14.508 tiempos de muestra, incluidos primer y último fotograma, identidades exclusivas, las 16 fichas con once métricas y la ponderación temporal de los mapas. También se comprobó el navegador en 1440, 1000 y 390 píxeles, selección de jugador, mapas, segunda parte pendiente, saltos a jugadas y exportaciones. Las pruebas con decisiones ficticias se hicieron en datos aislados.

El flujo reproducible está en `reanalizar.ps1`, `read_jersey_text.py`, `repair_identity_v5.py` y `commit_v5.py`. Usa los modelos y el entorno ya disponibles en `work/`, que no se incluyen en el ZIP. La copia previa a esta reparación permanece en `work/antes-identidad-v5`.

Para llegar al sistema completo hay que mejorar el detector del balón y los clasificadores de acciones con ejemplos etiquetados y medir acierto/errores por identidad y estadística. Una interfaz que muestre números no resuelve esa carencia. Este resultado no justifica prometer identificación perfecta ni totales automáticos fiables.

## Controles de análisis del visor v6

Los vídeos pendientes tienen **Analizar**, barra de porcentaje y fase, cola persistente, prevención de duplicados y **Reintentar análisis** si fallan. El 100 % requiere terminar el motor, la validación y la copia de reproducción. Los datos se incorporan a la temporada al finalizar. Se comprobó el recorrido completo con un fragmento original de 6,068 segundos en datos aislados. La primera parte conserva sus datos y revisiones. El análisis de la segunda parte se interrumpió en la fase de jugadas; se conservan sus detecciones para continuar el trabajo. Las cifras deportivas anteriores no han cambiado.
