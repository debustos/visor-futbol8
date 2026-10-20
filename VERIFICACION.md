# Verificación de la publicación

Fecha: 21 de octubre de 2026.

- **200 pruebas de software superadas** con Python 3.12 y el entorno existente del proyecto.
- Comando: `python -B -m unittest discover -s outputs/visor-futbol8 -p "test_*.py"`.
- Sintaxis Python comprobada en los archivos publicados.
- Arranque de la copia con metadatos vacíos, sin vídeos ni bases de datos del partido.
- HTTP 200 en la página, `/api/bootstrap`, `/api/review/learning` y `/learning-ui.js`.
- Preparación ejecutada dos veces: conserva los metadatos existentes.
- Comprobación básica de patrones de credenciales antes de publicar: sin hallazgos.

En la copia publicada se cierran explícitamente las conexiones de lectura SQLite del aprendizaje y las conexiones de sus pruebas; esto evita bloqueos de archivos temporales en Windows.

No se ha reinstalado el entorno desde cero ni repetido el entrenamiento completo con vídeos reales para esta publicación. Estas comprobaciones no certifican identificación perfecta, detección de todos los pases, tiros y goles ni mejora del modelo en el partido.

Los vídeos, capturas, pesos, cachés y bases SQLite quedan fuera de Git. El código original y los datos en `S:\visor-futbol8` se conservan. Esta copia para GitHub está en `S:\visor-futbol8-github`.
