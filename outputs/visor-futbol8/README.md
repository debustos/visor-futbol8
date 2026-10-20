# Visor de fútbol 8 · jornadas, temporada y revisión

El proyecto completo está en `S:\visor-futbol8`. Abre `S:\visor-futbol8\ABRIR-VISOR.cmd`, ejecuta `iniciar-visor.ps1` o visita http://127.0.0.1:8768/. El equipo naranja y Razquin disponen de fichas con once métricas, referencias visuales y mapa cenital. Visor v6: botones de análisis y progreso; motor v5 con memoria de apariencia activa y fichas con detecciones, estimaciones e incertidumbres. Los resultados siguen siendo parciales. Consulta RESULTADO.md para la cobertura comprobada.

## Jornadas y total de temporada

La pantalla inicial **Jornadas y total** reúne los dos vídeos de cada jornada. Los archivos actuales están registrados como **jornada 2**: primera parte analizada y segunda parte recibida; su estado de análisis se muestra en la tabla.

- Selecciona **Total de temporada**, una jornada completa o una de sus partes en **Estadísticas y mapa**.
- Pulsa un jugador: verás sus once métricas, mapa cenital, cobertura y jugadas del alcance seleccionado.
- La tabla inferior del jugador compara sus estadísticas por jornada. La tabla desplegable reúne a los 16 jugadores.
- Las acciones abren el vídeo y el segundo correctos. El selector **Vídeo para fichas, jugadas y revisión** fija la parte utilizada por las otras pestañas.
- Puedes descargar el mapa PNG y los datos CSV/JSON de una jornada o de la temporada.

El acumulado suma confirmadas y estimadas por separado; los candidatos no suman. Las partes sin análisis conservan N/D y se muestran como pendientes. Los mapas acumulan los segundos de cada posición, con ataque hacia arriba: la segunda parte no se mezcla en el sentido contrario. Las posiciones cuya orientación no esté resuelta se excluyen y se informa de su tiempo. Todo el plano sigue siendo aproximado.

Para añadir otro partido, despliega **Añadir vídeos de otra jornada**, indica su número y las rutas locales de las partes. También puedo registrarlos cuando me los envíes con el número de jornada. El registro conserva los originales en su unidad, comprueba su contenido con SHA-256 y evita registrar el mismo vídeo en dos jornadas. No sustituye una parte que ya tenga otro vídeo. Registrar es recibir el archivo; no ejecuta por sí solo el análisis.

`temporada.sqlite3` guarda la relación jornada/parte. Cada vídeo nuevo dispone de una carpeta, una base de revisiones y una caché independientes. La primera parte de la jornada 2 utiliza el análisis ya existente, que se ha conservado. La temporada usa la plantilla de dorsales que enviaste.

## Analizar una parte desde el visor

En la tabla **Jornadas**, cada vídeo pendiente tiene su botón **Analizar**. Al pulsarlo se ejecuta el motor completo: preparación del campo, detección, seguimiento, identidad, estadísticas, mapas, validación y reproducción. La barra muestra porcentaje y fase; alcanza el **100 %** cuando termina todo el proceso. Es un avance por etapas, no una predicción del tiempo restante.

El trabajo se guarda en SQLite y corre en un proceso independiente. Puedes recargar o cerrar la pestaña; sigue trabajando mientras el ordenador permanece encendido. Si inicias varias partes, se ponen en cola y se procesa una a la vez. Pulsar dos veces no duplica el trabajo. Una parte ya analizada no ofrece otro botón de inicio. Si falla o el proceso se interrumpe, aparece el error y **Reintentar análisis**. El resultado de una etapa intermedia no se suma todavía a la temporada.

Al terminar se actualizan las fichas, mapas y acumulados. Si estabas viendo esa parte, también se recarga su vídeo compatible. Los modelos y el entorno local de `work/` deben permanecer disponibles y la unidad de los vídeos debe estar conectada.

La preparación busca correspondencias con líneas y referencias de vídeos calibrados para obtener una proyección propia. Si no consigue una correspondencia válida, conserva la posición como desconocida y muestra un aviso: puede analizar jugadores, pero el mapa carecerá de posiciones fiables. La finalización del proceso no certifica la precisión deportiva ni convierte datos desconocidos en totales.

## Revisar tú las incertidumbres

1. Entra en **Revisar incertidumbres** y filtra por acciones, identidades, ocho iniciales, cambios o plano del campo.
2. Selecciona una propuesta y pulsa **Ver fragmento**. Puedes pausar, cambiar la velocidad y desplazarte por el vídeo.
3. **Confirmar** acepta los datos mostrados. **Guardar corrección** conserva los cambios de jugador, acción, receptor, resultado o tiempo. **Rechazar** excluye la propuesta. **Deshacer decisión** restaura su estado automático.
4. En identidades, selecciona el jugador y limita la corrección a su intervalo. También puedes pulsar una caja del vídeo en esta sección para revisar su segmento A. Una corrección manual desplaza una atribución automática incompatible; dos correcciones humanas simultáneas del mismo jugador se rechazan.
5. La alineación requiere ocho jugadores distintos. Un cambio necesita saliente, entrante y momento. Una aparición tardía se propone para revisar, sin afirmar que fuera una sustitución.
6. En el plano, comprueba las marcas azules y blancas detectadas. Aceptar permite usar el plano relativo en ese intervalo; excluir lo retira del mapa. No certifica medidas reales ni ajusta las coordenadas del terreno.
7. Si falta una jugada o cambio, usa **Incidencia omitida**, introduce el segundo y añádela para revisar. Completa sus datos y confirma tras ver el vídeo.

Las decisiones persisten en SQLite, tienen historial y se pueden exportar con el análisis revisado, las estadísticas CSV o las etiquetas para evaluación. Las etiquetas no revisadas no son ejemplos negativos. La asistencia debe vincularse a un gol confirmado de otro jugador; el sistema protege ese vínculo al corregir o deshacer.

## Lectura de estadísticas y mapas

- **Confirmadas por revisión**: acciones comprobadas por ti. No son necesariamente todos los eventos del partido.
- **≈**: estimaciones automáticas con cobertura parcial.
- **Candidatos**: propuestas que todavía no suman como estimadas o confirmadas.
- **0 detectados**: ninguna acción aceptada por el motor en los tramos observados; no demuestra cero en todo el partido.
- **Sin observación / N/D**: no hay datos atribuibles a ese jugador o parte.

El CSV revisado conserva cuatro columnas por métrica: confirmadas, estimadas, candidatas y detectadas en tramos observados. Las fichas priorizan las confirmadas y muestran aparte estimaciones adicionales. Los mapas pesan cada posición por los segundos observados; aumentar la frecuencia de análisis no aumenta artificialmente el calor. La ficha muestra cobertura de identidad y cobertura del plano utilizable. Las barras son presencia observada, no minutos jugados.

## Mejoras del motor

- `visual_memory.py` reúne referencias próximas a lecturas de dorsal y rasgos de pelo, medias y botas. La segunda pasada usa votos visuales, posición y enlaces en ambos sentidos. Corta discontinuidades y dorsales incompatibles y excluye identidades duplicadas en el mismo fotograma.
- `adaptive_ball.py` detecta de nuevo jugadores y balón a 15 muestras/s alrededor de contactos y propuestas de acción. Combina estas ventanas con la base de 5 muestras/s. El balón no se interpola. Las cajas nuevas se asocian solo cuando hay una correspondencia única con las identidades cercanas.
- `sequence_engine.py` distingue contacto, salida, viaje del balón y recepción. Un pase estimado exige trayectoria medida; cambios de equipo, tiros, faltas y regates inciertos quedan para revisar. Este motor usa reglas de secuencia; no equivale a un clasificador deportivo entrenado y validado independientemente.
- `pitch_geometry.py` detecta líneas azules y blancas, comprueba su compatibilidad con la proyección y excluye planos incompatibles. El registro de cámara se actualiza durante el análisis. La geometría mantiene coordenadas relativas y referencias de portería; faltan dimensiones y correspondencias F8 verificadas para una calibración exacta.
- `presence_engine.py` usa presencia sostenida y cruces de banda emparejados. No convierte una desaparición del encuadre en cambio.
- `analytics_review.py` integra tus decisiones en fichas, acciones, mapas y alineación. En la siguiente ejecución de la memoria, las identidades revisadas del mismo vídeo y detecciones pueden servir de referencias. Los datos T antiguos no se utilizan.

## Repetir el análisis

```powershell
.\reanalizar.ps1 -Jornada 2 -Parte 1 -ReusarDetecciones -ReusarDorsales
```

Elige `-Jornada N -Parte 1` o `-Parte 2` para procesar un vídeo registrado. Sin los parámetros de reutilización, se repiten también detección y OCR. El script prepara una proyección propia mediante `prepare_video.py`; si no se encuentra una correspondencia válida, analiza sin inventar posiciones del campo. Los modelos se comparten, pero los resultados y cachés se guardan por jornada y parte. Los scripts terminan con error si falla una etapa. La ruta del vídeo actual es `S:\PRIMERA PARTE.MP4`; los pesos y el entorno están en `work/`, fuera del ZIP. `media/primera-compatible.mp4` es una copia H.264 para reproducción; el original sigue siendo la entrada del análisis.

Los modelos, datos y ejecución son locales. Consulta `JORNADAS.md` para el estado de la temporada y `RESULTADO.md` para las cifras del motor v5 y sus límites. Las pruebas de software y del navegador comprueban funcionamiento; la precisión deportiva independiente sigue pendiente. Consulta la tabla Jornadas para el estado actualizado de la segunda parte.

## Reparación v5

`read_jersey_text.py` lee números completos; `repair_identity_v5.py` reconstruye identidad por dorsal, apariencia y continuidad; `commit_v5.py` publica las fichas sin borrar revisiones. Las referencias verificadas de entrenamiento se limitan al vídeo y a la huella de sus detecciones. El flujo de `reanalizar.ps1` ejecuta estas etapas. Los ejemplos actuales de goles, faltas y otras métricas siguen siendo insuficientes para obtener totales fiables: véase RESULTADO.md.
