# Visor de fútbol 8

Aplicación local para revisar partidos por jornada, identificar jugadores del equipo naranja y su portero, consultar estadísticas parciales y mapas de calor y corregir incertidumbres.

Este repositorio contiene el código del visor, los motores de análisis, las pruebas, la plantilla de jugadores y la documentación. El análisis deportivo sigue en desarrollo: no detecta todas las acciones ni todas las identidades de forma fiable. Las pruebas de software no certifican precisión en vídeo.

## Instalación en Windows

Usa Python 3.12 y PowerShell. Desde la raíz del repositorio:

```powershell
py -3.12 -m venv work/vision-env
.\work\vision-env\Scripts\python.exe -m pip install -r outputs/visor-futbol8/requirements-automatic-lock.txt
.\work\vision-env\Scripts\python.exe preparar-proyecto.py
.\ABRIR-VISOR.cmd
```

El visor escucha únicamente en `http://127.0.0.1:8768/`. Los requisitos fijan las versiones del entorno de desarrollo; la instalación desde cero debe comprobarse en el equipo destino. Registrar vídeos requiere que estén disponibles en ese equipo.

La preparación crea una temporada vacía y no sobrescribe archivos existentes. Añade los vídeos de cada jornada en el visor y adapta `outputs/visor-futbol8/plantilla.json` si cambia la plantilla.

## Modelos y datos locales

No se incluyen vídeos, capturas de jugadores, revisiones SQLite, análisis generados, pesos de modelos, entornos Python ni cachés. Permanecen en el proyecto original, `S:\visor-futbol8`. Clonar este repositorio **no restaura automáticamente** las jornadas analizadas ni sus correcciones.

Para analizar vídeos necesitas además los modelos y recursos locales utilizados por el motor. `outputs/visor-futbol8/modelos.json` describe los principales pesos, procedencia y hashes. El entorno existente contiene también recursos OCR, del modelo temporal y de dorsales. La instalación de dependencias por sí sola no los prepara todos. Para continuar con los partidos actuales, utiliza el proyecto original o restaura sus carpetas de datos y recursos en una copia local antes de abrir el visor; no sobrescribas datos más recientes.

## Aprendizaje a partir de correcciones

Se incluye el trabajo de reentrenamiento: `learning_jobs.py`, `review_learning.py`, el estado en la interfaz y `autoentrenar-revisiones.ps1`. Agrupa cambios durante 15 segundos, guarda trabajos persistentes y contempla deshacer correcciones. La parte de aprendizaje sigue pendiente de validación completa con las revisiones reales del partido; no se presenta como un detector deportivo ya validado.

## Pruebas

Desde la raíz, con las dependencias instaladas:

```powershell
.\work\vision-env\Scripts\python.exe -B -m unittest discover -s outputs/visor-futbol8 -p "test_*.py"
```

Consulta `VERIFICACION.md` para el resultado de la comprobación de esta entrega.

## Estructura

- `outputs/visor-futbol8/`: aplicación, motores y pruebas.
- `outputs/visor-futbol8/vendor/` y `licenses/`: código de terceros y sus avisos de licencia.
- `preparar-proyecto.py`: preparación local sin datos del partido.
- `ABRIR-VISOR.cmd`: acceso al visor en Windows.
- `work/`: entorno, modelos y cachés locales; excluida de Git.

El [manual del visor](outputs/visor-futbol8/README.md) y los informes históricos documentan las iteraciones anteriores; sus cifras y rutas describen el entorno original. Las imágenes y exportaciones mencionadas en ellos permanecen fuera de Git.

La publicación inicial conserva la organización de carpetas necesaria para resolver las rutas del motor. No cambia ni elimina el historial local de 10 GB del proyecto original. Las siguientes subidas deben hacerse desde esta copia limpia.
