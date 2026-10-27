# Evaluación independiente de goles y faltas

Formato publicado primero: `ejemplo-sintetico.json` es ficticio y nunca constituye referencia de jornada 4.
Los tiempos son segundos del archivo original. `interval` abarca la jugada completa, incluido desenlace y reanudación. Tipos: `goal`, `shot_no_goal`, `foul`, `other`. `foul` verificado exige decisión arbitral observable; un contacto ambiguo queda `pending`. Equipo, dorsal y player_id son null salvo evidencia visual o confirmación documentada. Evidencia debe identificar observación, revisor y fecha. Estado: verified/pending/rejected. Grupo: development/holdout.

`coverage` contiene exclusivamente intervalos recorridos con continuidad y revisados para ambos tipos. No declarar cobertura completa con mosaicos. Anotar la duración obtenida del original y SHA-256 completo. Las jugadas completas no cruzan grupos. Reservar preferiblemente la segunda parte completa; mantener sus anotaciones fuera de la rama compartida durante ajustes y proporcionarlas solo a aceptación. No publicar reserva antes de congelar el detector.

Desde outputs/visor-futbol8:

```powershell
python -m evaluacion.medir --round 4 --half 1
python -m evaluacion.medir --round 4 --half 1 --registry-root <registro> --annotations <referencia.json> --analysis-root <resultado-base-aislado> --version <commit-base> --output <informe-base>
python -m evaluacion.medir --round 4 --half 1 --registry-root <registro> --annotations <misma-referencia.json> --analysis-root <resultado-nuevo-aislado> --version <commit-nuevo> --before <informe-base>/informe.json --output <informe-nuevo>
```

`--split holdout` abre aceptación. Tolerancia configurable `--tolerance 3`: diferencia absoluta <=3 segundos. Emparejamiento bipartito determinista de cardinalidad máxima, independiente de equipo y autor; no optimiza el error temporal global. Requiere original compatible con registro y referencia. Lee SQLite en modo solo lectura. No ejecuta el motor ni escribe análisis/revisiones. Ejecutar ambas ramas del motor en raíces aisladas con los mismos originales y parámetros. `--runtime-seconds` registra el tiempo del motor medido externamente; null significa no medido. `--version` debe identificar el commit real; unknown no acredita procedencia.

Salidas: informe.json con métricas, huellas de contratos y errores individualizados; informe.txt con tiempos e intervalos para localizar cada caso. `--before` exige misma referencia, vídeo, parte, partición y tolerancia. Delta positivo en missed/false/duplicates significa empeoramiento. Comparar también runtime_seconds entre informes.

Se evalúan por separado temporal-candidates.json, candidatos publicados y acciones estimated de actions.json (antes de revisión humana). profiles.json aporta dorsal; no se mezclan sus acciones con actions.json. Una etapa ausente aparece no disponible. Revisión humana posterior requiere exportación separada y adaptador pendiente; nunca se deduce de perfiles originales. Acierto de equipo/autor se calcula entre goles emparejados con referencia conocida; ausencia de predicción cuenta como error de atribución. Valores desconocidos no entran en denominadores.

Falsos positivos solo dentro de cobertura revisada y fuera de pendientes; resto sin evaluar. Duplicados cuentan contra precisión. Recall limitado a anotaciones verificadas. Aceptación exige reserva completa, al menos un positivo del tipo, cero omisiones/falsos/duplicados/pendientes/sin evaluar. No extrapolar a otros partidos. El informe incluye cada fallo y el alcance revisado.

## Situación real 2026-10-27

Base origin/develop: b97c6e21a01f48b65d626a0dc501575fb472e951.
Checkout original limpio. Sin AGENTS.md encontrado. Registro temporada.sqlite3 y data/video-library.json consultados sin escribir: únicamente jornada 2 partes 1 y 2. La biblioteca configurada contiene únicamente sus originales. Jornada 4 no registrada: no hay SHA-256 ni anotaciones reales publicables, candidatos de vídeo, revisión continua ni medición base/nueva. Ningún fragmento anterior se tomó como verdad. No se certifica recuento ni mejora.

Petición de datos para plataforma/acciones (PLAN §5.4): registrar los originales de jornada 4 en la biblioteca y proporcionar resultados aislados de develop y mod/acciones/goles-faltas con commit y tiempo medido. Se conserva esta petición aquí para respetar el alcance explícito de la tarea (no editar docs/peticiones). No requiere cambiar contratos. Después generar candidatos con intervalos amplios, revisar partes completas y pedir confirmaciones concretas solo sobre ambigüedades reales. No pedir al usuario una lista exhaustiva de momentos.

Validación: 14 pruebas propias; suite completa y resultado documentados en CHANGELOG. La ruta work/vision-env del PLAN no existe en este equipo; se utiliza S:/visor-futbol8/work/visor-env/Scripts/python.exe. Vídeos y salidas reales deben ir fuera de Git.
