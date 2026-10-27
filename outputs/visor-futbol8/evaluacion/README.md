# Evaluación independiente de goles y faltas

## Objetivo actual: J2 (indicación del usuario)

Se conserva la rama aislada existente; el cambio de jornada no modifica datos, navegación ni detectores. Originales de ambas partes comprobados contra el SHA-256 del registro. Parte 1: 1468,6467 s, 44051 fotogramas, 29,99428045 FPS medios. Parte 2: 1516,3183 s, 45481 fotogramas, 29,99436134 FPS medios. Se decodificaron seis fotogramas de cada original, al principio/centro/final, registrando sus tiempos observados. Esto no es una revisión visual continua ni una auditoría de todos los PTS.

Preparación real: 5,399 s incluyendo huellas completas y muestras temporales, sin inferencia. Salida aislada: `S:/visor-futbol8/work/evaluacion-j2/preparacion-inicial-20261027/`, con `preparacion.json`, `j002-p1.json` y `j002-p2.json`. Las referencias identifican originales reales, pero están `unreviewed`, sin eventos, negativos ni cobertura. No hay confirmaciones humanas. Línea base y comparación deportivas siguen null.

En ambas raíces registradas (`jornadas/j002/parte-1` y `parte-2`) faltan actions.json, profiles.json y temporal-candidates.json; sus status.json indican análisis pendiente. También faltan acciones/perfiles en la raíz antigua. La copia de temporales del archivo balon-fiabilidad apunta a una ruta antigua y carece de vínculo verificado con la huella original: no se incorpora como salida fiable ni se toma como verdad. Petición a acciones/publicación: proporcionar las salidas aisladas base/nueva para ambas partes, sus versiones/configuración y tiempos, sin ejecutar aquí el análisis completo.

Comando de preparación (cada ejecución exige carpeta nueva; solo requiere el OpenCV ya utilizado por el proyecto):

```powershell
Set-Location 'C:/Users/debus/.codex/worktrees/evaluacion-auditoria-j4/visor-futbol8/outputs/visor-futbol8'
& 'S:/visor-futbol8/work/visor-env/Scripts/python.exe' -B -m evaluacion.preparar --round 2 --registry-root S:/visor-futbol8/outputs/visor-futbol8 --output ('S:/visor-futbol8/work/evaluacion-j2/preparacion-' + [DateTime]::UtcNow.ToString('yyyyMMdd-HHmmss'))
& 'S:/visor-futbol8/work/visor-env/Scripts/python.exe' -B -m evaluacion.medir --round 2 --half 1 --registry-root S:/visor-futbol8/outputs/visor-futbol8 --annotations S:/visor-futbol8/work/evaluacion-j2/preparacion-inicial-20261027/j002-p1.json --output S:/visor-futbol8/work/evaluacion-j2/base-p1
& 'S:/visor-futbol8/work/visor-env/Scripts/python.exe' -B -m evaluacion.medir --round 2 --half 2 --registry-root S:/visor-futbol8/outputs/visor-futbol8 --annotations S:/visor-futbol8/work/evaluacion-j2/preparacion-inicial-20261027/j002-p2.json --output S:/visor-futbol8/work/evaluacion-j2/base-p2
```

Las órdenes de medir siguen pendientes de los contratos reales. Cuando estén disponibles, indicar --actions/--profiles/--temporal y versiones reales, revisar ambas partes completas antes de consultar propuestas y mantener la segunda parte reservada durante los ajustes. El módulo no transforma la preparación técnica en evidencia deportiva.

## Formato y medición

Formato publicado primero: `ejemplo-sintetico.json` es ficticio y nunca constituye referencia de jornada 4.
Los tiempos son segundos del archivo original. `interval` abarca la jugada completa, incluido desenlace y reanudación. Tipos: `goal`, `shot_no_goal`, `foul`, `other`. `foul` verificado exige decisión arbitral observable; un contacto ambiguo queda `ambiguous`. Equipo, dorsal y player_id son null salvo evidencia visual o confirmación documentada. Estado: verified/pending/ambiguous/rejected. Grupo: development/holdout. El [manual de anotación](anotaciones/README.md) detalla procedencia, secuencias, negativos y comprobación temporal del MOV.

`coverage` contiene exclusivamente intervalos recorridos con continuidad y revisados para ambos tipos. No declarar cobertura completa con mosaicos. Anotar la duración obtenida del original y SHA-256 completo. Las jugadas completas no cruzan grupos. Reservar preferiblemente la segunda parte completa; mantener sus anotaciones fuera de la rama compartida durante ajustes y proporcionarlas solo a aceptación. No publicar reserva antes de congelar el detector.

Desde outputs/visor-futbol8:

```powershell
python -m evaluacion.medir --round 4 --half 1
python -m evaluacion.medir --round 4 --half 1 --registry-root <registro> --annotations <referencia.json> --analysis-root <resultado-base-aislado> --version <commit-base> --output <informe-base>
python -m evaluacion.medir --round 4 --half 1 --registry-root <registro> --annotations <misma-referencia.json> --analysis-root <resultado-nuevo-aislado> --version <commit-nuevo> --before <informe-base>/informe.json --output <informe-nuevo>
python -m evaluacion.medir --round 4 --half 2 --video <original.mov> --annotations <referencia-p2.json> --actions <actions.json> --profiles <profiles.json> --temporal <temporal-candidates.json> --confirmed-actions <acciones-revisadas.json> --split holdout --version <commit> --output <carpeta-nueva>
```

`--split holdout` abre aceptación. Tolerancia configurable `--tolerance 3`: diferencia absoluta <=3 segundos. Emparejamiento bipartito determinista de cardinalidad máxima, independiente de equipo y autor; no optimiza el error temporal global. Requiere original compatible con registro y referencia. Lee SQLite en modo solo lectura. No ejecuta el motor ni escribe análisis/revisiones. Ejecutar ambas ramas del motor en raíces aisladas con los mismos originales y parámetros. `--runtime-seconds` registra el tiempo del motor medido externamente; null significa no medido. `--version` debe identificar el commit real; unknown no acredita procedencia.

Salidas: informe.json con métricas, huellas y rutas de entradas, SHA del evaluador, versión de Python, tiempo del evaluador (hasta preparar el informe, sin escritura), y errores individualizados; informe.txt con tiempos e intervalos para localizar cada caso. `--before` exige misma referencia, vídeo, parte, partición, tolerancia, etapas y SHA del evaluador: recalcular salidas anteriores si cambia la medición. Incluye diferencias de precisión, recall, error temporal y tiempo del detector cuando esté medido. Delta positivo en missed/false/duplicates significa empeoramiento. `--output` debe estar ausente o vacío; nunca sobrescribe informes. Una ruta temporal explícita inexistente es un error, no una etapa silenciosamente ausente.

Se evalúan por separado temporal-candidates.json, candidatos publicados, acciones estimated de actions.json y confirmadas de la exportación opcional --confirmed-actions. Esta última debe ser una lista de acciones efectivas del sistema de revisión, con state=confirmed; se ignoran allí candidatos/estimados/rechazados y nunca se promueven automáticamente. Su estado es el declarado en esa entrada, no una confirmación de la referencia por el usuario. profiles.json aporta dorsal; no se cuentan sus acciones otra vez. Una etapa ausente aparece no disponible. Adaptación local: Goal/goal y shot+outcome=goal son goles; Foul/foul/foul_won/foul_committed son faltas. Conserva equipo rival y autor null; team=unresolved se contabiliza desconocido. Acierto de equipo/autor y contadores unknown_reference/unknown_prediction se calculan entre eventos emparejados, por separado del acierto deportivo. Referencia desconocida no entra en el denominador de atribución; predicción desconocida frente a referencia conocida sí cuenta como error.

Falsos positivos solo dentro de cobertura revisada y fuera de pendientes/ambigüedades del mismo tipo; resto sin evaluar. Un contacto dudoso no oculta un falso gol. Duplicados cuentan contra precisión, incluso junto a un positivo verificado fuera de cobertura negativa. Recall limitado a anotaciones verificadas. Cada propuesta se asigna a una sola partición: primero bloque revisado [inicio, fin), incluyendo el último instante del vídeo; fuera de bloques, secuencia del mismo tipo más cercana dentro de su intervalo ampliado por la tolerancia (empates por id). Las propuestas de otra partición figuran en outside_split. Se rechazan coberturas solapadas, secuencias que crucen grupos y un mismo sequence_id repartido entre ellos. Aceptación exige reserva de toda la parte, al menos un positivo del tipo, cero omisiones/falsos/duplicados/pendientes/sin evaluar y referencia no sintética. No extrapolar a otros partidos. El informe incluye cada fallo y los segundos revisados; no son una medida de cobertura del detector.

## Situación inicial J4 · 2026-10-27 (sustituida por J2)

Base de esta auditoría origin/develop: bec337ed23e11e26e0827e52bcd75c7b82f2f12c, que ya incluía el evaluador inicial. Su responsable confirmó que su trabajo había terminado y liberó el módulo. Se usa otro worktree en mod/evaluacion/goles-faltas-j4; no se cambió la rama del checkout compartido.
Checkout original limpio. Sin AGENTS.md encontrado. Registro temporada.sqlite3 y data/video-library.json consultados sin escribir: únicamente jornada 2 partes 1 y 2. La biblioteca configurada contiene únicamente sus originales. Jornada 4 no registrada: no hay SHA-256 ni anotaciones reales publicables, candidatos de vídeo, revisión continua ni medición base/nueva. Ningún fragmento anterior se tomó como verdad. No se certifica recuento ni mejora.

Petición de datos para plataforma/acciones (PLAN §5.4): registrar los originales de jornada 4 en la biblioteca y proporcionar resultados aislados de develop y mod/acciones/goles-faltas con commit y tiempo medido. Se conserva esta petición aquí para respetar el alcance explícito de la tarea (no editar docs/peticiones). No requiere cambiar contratos. Después generar candidatos con intervalos amplios, revisar partes completas y pedir confirmaciones concretas solo sobre ambigüedades reales. No pedir al usuario una lista exhaustiva de momentos.

Validación inicial: las 14 pruebas existentes pasan (0,008 s); nueve regresiones adicionales reproducen siete fallos y dos errores. Tras la corrección pasan esas nueve y las comprobaciones adicionales de CLI. Son pruebas sintéticas de contratos, no precisión deportiva ni una comparación de velocidad del detector. La suite completa y su resultado se documentan en CHANGELOG. La ruta work/vision-env del PLAN no existe en este equipo; se utiliza S:/visor-futbol8/work/visor-env/Scripts/python.exe. Vídeos y salidas reales deben ir fuera de Git.

Comandos exactos de comprobación en este equipo (36 pruebas del módulo incluidas en las 274 totales):

```powershell
Set-Location 'C:/Users/debus/.codex/worktrees/evaluacion-auditoria-j4/visor-futbol8'
$env:TEMP = 'S:/visor-futbol8/work/tmp'
$env:TMP = $env:TEMP
& 'S:/visor-futbol8/work/visor-env/Scripts/python.exe' -B -m unittest discover -s outputs/visor-futbol8/tests/evaluacion -t outputs/visor-futbol8
& 'S:/visor-futbol8/work/visor-env/Scripts/python.exe' -B -m unittest discover -s outputs/visor-futbol8/tests -t outputs/visor-futbol8
Set-Location outputs/visor-futbol8
& 'S:/visor-futbol8/work/visor-env/Scripts/python.exe' -B -m evaluacion.medir --round 4 --half 1 --registry-root S:/visor-futbol8/outputs/visor-futbol8 --output S:/visor-futbol8/work/evaluacion-auditoria/pendiente-j4-p1
& 'S:/visor-futbol8/work/visor-env/Scripts/python.exe' -B -m evaluacion.medir --round 4 --half 2 --registry-root S:/visor-futbol8/outputs/visor-futbol8 --output S:/visor-futbol8/work/evaluacion-auditoria/pendiente-j4-p2
```

Las dos últimas órdenes deben fallar con código 2 mientras J4 no esté registrada, sin crear carpetas de informes. No constituyen una evaluación deportiva. Las pruebas de CLI usan bytes ficticios y verifican explícitamente que no cambien las entradas; no comprueban decodificación ni tiempos de MOV reales.
