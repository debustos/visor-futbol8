# Jornadas y temporada · visor v6

El visor está disponible en http://127.0.0.1:8768/?v=analizar-partes-v6. La pantalla **Jornadas y total** incluye las fichas, once métricas y mapas de cada jugador, por jornada y acumulados durante la temporada.

## Jornada registrada

| Jornada | Primera parte | Segunda parte | Análisis disponible |
|---|---|---|---|
| 2 | PRIMERA PARTE.MP4 · 24:28,65 | SEGUNDA PARTE.MP4 · 25:16,32 | 1 de 2 partes |

No se ha añadido una jornada 1 ficticia ni se ha convertido la segunda parte pendiente en ceros. El acumulado actual contiene las observaciones de la primera parte de la jornada 2. La segunda parte tiene las detecciones calculadas, pero el análisis se interrumpió en la fase de jugadas. El visor conserva su estado y ofrece **Reintentar análisis**.

## Funcionamiento

Selecciona temporada, jornada o parte; después pulsa un jugador. Su mapa suma los segundos observados en las zonas del campo y mantiene un sentido de ataque común. Las once estadísticas separan acciones confirmadas por revisión, estimaciones y propuestas candidatas. Cada jugada conserva jornada, parte y tiempo local, y abre el vídeo correspondiente.

La tabla del jugador muestra su evolución por jornadas. Hay una tabla desplegable para comparar a todos los jugadores en el alcance elegido. Los CSV y JSON mantienen N/D, cobertura, partes pendientes y los recuentos separados; puedes descargar el mapa como PNG.

Las revisiones pertenecen a cada vídeo y actualizan las sumas de jornada y temporada. Corregir una acción de una parte no modifica otra con un identificador o segundo parecido. Confirmar, corregir, rechazar y deshacer siguen disponibles en **Revisar incertidumbres**.

Los nuevos vídeos se registran por jornada y parte, con fecha y rival opcionales. El registro comprueba la duración y el SHA-256, evita vídeos duplicados y conserva los análisis anteriores. Los originales siguen en su ubicación; no se han duplicado ni alterado. El registro no inicia automáticamente los modelos. `reanalizar.ps1` admite jornada y parte y mantiene sus cachés separadas; prepara su proyección antes de ejecutar los modelos.

## Botón y barra por parte

Cada parte pendiente ofrece **Analizar**, y su fila muestra porcentaje y fase hasta la finalización. Los análisis simultáneos se ponen en cola. Los trabajos persisten al recargar o cerrar el navegador, y un fallo ofrece **Reintentar análisis**. Las fichas y los acumulados se actualizan automáticamente al terminar. La barra refleja etapas y muestras procesadas; no estima minutos restantes.

## Resultado y límites actuales

El motor v5 recorre 14.508 muestras en toda la primera parte: once identidades parcialmente observadas, seis acciones estimadas y 66 candidatas. Para Busi hay 367 s de identidad observada y 322,13 s de posiciones proyectadas. Las fichas y CSV muestran las detecciones en los tramos observados y distinguen la falta de observación. El mapa y las sumas no equivalen a todos sus minutos ni a todos sus eventos.

En temporada, la cobertura respecto al vídeo recibido incluye también la segunda parte pendiente: no debe confundirse con la cobertura respecto a los 24:28 ya analizados. La pantalla muestra ambos porcentajes. La proyección del campo sigue siendo relativa y aproximada. Si no se resuelve el sentido de ataque, las posiciones de ese intervalo no entran en el mapa acumulado.

La organización por jornadas ya funciona. La identificación automática completa de todos los jugadores y la extracción fiable de todas las acciones siguen pendientes; incorporar más partidos no resuelve por sí solo esas limitaciones.

## Comprobaciones

Pasaron **89 pruebas de software**. Incluyen sumas de varias partes y jornadas, N/D frente a cero explícito, ponderación por segundos, giro de ambos ejes al cambiar el sentido de ataque, duplicados por contenido y aislamiento de sesiones, bases de revisión y archivos de vídeo.

Se comprobó la jornada 2 real en un navegador aislado: selección de jugador y alcance, segunda parte pendiente, acceso a incertidumbres, apertura de jugadas en el segundo correcto y anchuras de 1440, 1000 y 390 píxeles. No se detectaron errores JavaScript ni desbordamiento horizontal.

En un escenario aislado de dos jornadas y tres partes analizadas, se verificaron confirmación, recarga, persistencia, deshacer y actualización del acumulado sin contaminar otros vídeos. También se registró una nueva jornada desde la interfaz, que quedó pendiente y conservó las anteriores. Las acciones ficticias de estas pruebas no se escribieron en el partido real. Estas comprobaciones verifican el programa; no miden su precisión deportiva.

Pruebas: `test_season.py`, `pruebas-jornadas-interfaz.json` y `pruebas-jornadas-multiples.json`. Instrucciones completas en `README.md`. La copia empaquetada actual se llama `visor-jornadas.zip`; incluye código, resultados y registros, con vídeos, pesos y entorno excluidos.

Se verificó el botón con un fragmento real de **6,068 segundos** en una jornada aislada: lanzó el motor completo, conservó el trabajo tras recargar, rechazó la duplicación y llegó al 100 % después de generar y validar 16 fichas, 11 campos por ficha, 16 mapas y vídeo compatible. El fragmento produjo 82 muestras; esta prueba no analizó la segunda parte real ni mide acierto deportivo. `pruebas-boton-analisis.json` conserva sus resultados. Las capturas de progreso y finalización proceden de esa prueba aislada.

Las pruebas de interfaz aisladas también comprueban cola, barra y cabecera, progreso al recargar, error con porcentaje conservado, reintento y diseño móvil: `pruebas-controles-analisis.json`.

Al empaquetar, los resultados de una parte que sigue ejecutándose se excluyen del ZIP; solo en la base de la copia se deja disponible para reintentar. El proceso del visor original continúa.
