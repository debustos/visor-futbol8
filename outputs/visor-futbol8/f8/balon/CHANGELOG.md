# Cambios · balon

Una entrada por PR fusionado, la más reciente arriba: fecha, rama y qué cambia para los demás módulos.

## 2026-10-27 · mod/balon/fiabilidad-rendimiento
- `ball_tracker.predict` omite el flujo óptico y la homografía cuando no hay una
  semilla medida o el intervalo no permite seguimiento. Antes calculaba la cámara
  y descartaba su resultado inmediatamente. El seguimiento activo conserva la
  compensación de cámara. No cambian candidatos, umbrales, modelos, resolución,
  frecuencia, contratos ni la prohibición de interpolar.
- Cinco pruebas de regresión de pérdida, readquisición y compensación de cámara;
  tres pruebas de las métricas (una posición incorrecta cuenta como falso positivo
  y como balón visible perdido; cobertura y precisión se calculan por separado).
- Benchmark reproducible en `tests/balon/benchmark_native_ball.py`, cuatro
  fragmentos en `tests/balon/fixtures/native-benchmark.json` y una comprobación
  adicional de llegada a portería en `fixtures/native-arrival.json`. Esta última
  pertenece a la misma secuencia de desarrollo que el tiro, nunca a la reserva.
  Las anotaciones visuales del asistente son provisionales: doce fotogramas
  evaluables y ocho desconocidos excluidos, sin negativos de balón no visible.
  Los tiempos del manifiesto solo se usan para evaluar, nunca en el motor.
- Se reutilizan modelos y registros archivados; no se ejecutan detección inicial,
  OCR, identidad ni publicación. Todos los resultados quedan en
  `work/balon-fiabilidad/`, sin modificar los datos del visor o las revisiones.
- Revisión del flujo: `refine_ball` ya combina teselas nativas y readquisición
  local; `adaptive_ball` reutiliza los jugadores de muestras base; `native_ball`
  añade dos pasadas y ventanas solapadas; `ball_continuity` puntúa detecciones
  existentes. No se eliminan solapes, inferencias ni búsquedas, porque hacerlo
  puede alterar la recuperación. Se elimina el trabajo de cámara cuyo resultado
  se descartaba antes de usarlo en `MeasuredBallTracker.predict`.

### Medición realizada

Tracker con píxeles reales y candidatos archivados, siete repeticiones alternadas
por versión, sin decodificación, calibración o inferencias dentro del cronómetro:

| Fragmento | Muestras | Mediana antes (s) | Mediana después (s) | Cámara antes → después |
|---|---:|---:|---:|---:|
| Contacto, desarrollo | 16 | 0,449527 | 0,275121 | 15 → 9 |
| Tiro, desarrollo | 16 | 0,455112 | 0,284712 | 15 → 9 |
| Saque, reserva | 8 | 0,237812 | 0,000050 | 7 → 0 |
| Área de portería, reserva | 16 | 0,439617 | 0,000106 | 15 → 0 |

Suma de medianas: **1,582068 → 0,559989 s (−64,6 %)**. Las 56 salidas
coinciden exactamente, en todas las repeticiones. Los intervalos sin semilla
quedan casi sin trabajo de tracking; sus inferencias de readquisición siguen
ejecutándose en el flujo completo. Este porcentaje no se extrapola al partido.

Comprobación completa de `native_ball.analyze_span`, con modelos:

| Fragmento (segundos de vídeo) | Tiempo antes (s) | Después (s) | Cámara antes → después |
|---|---:|---:|---:|
| 60–60,8 | 63,952 | 43,106 | 48 → 31 |
| 943,6–944,4 | 48,694 | 42,053 | 48 → 42 |
| 300–300,8, reserva | 71,837 | 62,257 | 48 → 0 |
| 1200–1200,8, reserva | 74,348 | 71,378 | 48 → 0 |
| 944,6–945,2, llegada (una ejecución por versión) | 36,238 | 39,325 | 36 → 31 |

En las primeras cuatro filas, antes es la mediana de tres ejecuciones y después una
ejecución: **258,831 → 218,794 s** sumados. Son tiempos observados con variación
importante (por ejemplo, 54,763–67,412 s antes en el primer fragmento), sin
alternancia del flujo completo y con cachés del sistema calientes. No demuestran
por sí solos una aceleración global del 15,5 %; la medición alternada anterior
es la evidencia del ahorro localizado. Las inferencias conservan sus contadores.
La llegada a portería tarda más en la ejecución posterior, pese a requerir menos
registro de cámara; esto refuerza la limitación de los tiempos globales aislados.

Se han examinado **119 fotogramas nativos** en cinco fragmentos, conservando
exactamente el JSON completo de cada ventana: posiciones, cajas, confianza,
candidatos, contactos e identidades. En el flujo nativo se pasa de **228 a 104**
llamadas de cámara, sin reducir las llamadas de inferencia.

Anotaciones provisionales sobre doce fotogramas con balón visible:

| Calidad | Antes | Después |
|---|---:|---:|
| Localizaciones correctas | 3 | 3 |
| Balones visibles perdidos | 9 | 9 |
| Falsas localizaciones | 2 | 2 |
| Cobertura (posiciones emitidas / muestras evaluables) | 5/12 | 5/12 |
| Precisión (correctas / emitidas) | 3/5 | 3/5 |
| Recall (correctas / visibles) | 3/12 | 3/12 |

Ocho muestras desconocidas se excluyen. Los dos falsos positivos y las pérdidas
existentes siguen presentes, incluida la bota antes del tiro; **esta entrega no
mejora la precisión deportiva**. Los tres aciertos están en la llegada a portería.
Los resultados son de una muestra difícil y pequeña, no del partido completo.
`--compare-directory` exige igualdad exacta y recalcula también la calidad de la
base con el mismo manifiesto, sin volver a ejecutar los modelos. Los informes y
salidas completos están en `work/balon-fiabilidad/{before,after,before-arrival,after-arrival,replay}/`.

Vídeo SHA-256: `2e00490f64f6f19b6d9682059425f91e17379dc57f6a3408743b60749d729331`.
Registros SHA-256: `153719aaff741582f9e5b426421edd0b2c46d95ce94ba3f103632619f254c9b6`.
Los pesos recuperados coinciden con los SHA-256 de `modelos.json`.

Pruebas: **208 OK antes, 216 OK después**; registro local en
`work/balon-fiabilidad/tests-before.log` y `tests-after.log`. Las pruebas sintéticas
no acreditan precisión deportiva. Siguen pendientes una muestra más amplia con
negativos revisados por una persona, otros partidos y una medición con DirectML.

### Reproducción desde la raíz del repositorio

Requiere el vídeo original `S:/PRIMERA PARTE.MP4` (SHA-256 en el manifiesto) y
la copia local `S:/visor-futbol8.rar`. El entorno de esta medición es
`work/visor-env`: Python 3.12.14, OpenCV 5.0.0, NumPy 2.5.4, SciPy 1.18.1,
ONNX Runtime 1.31.1 CPU. No se cambian los requisitos del proyecto.

```powershell
New-Item -ItemType Directory -Force work/balon-fiabilidad/archive | Out-Null
tar -xf S:/visor-futbol8.rar -C work/balon-fiabilidad/archive visor-futbol8/work/football-ball-detection.onnx visor-futbol8/work/yolo11s.onnx visor-futbol8/work/automatic-half/recovery-v5/records-v5.json
$taskBallPython = 'S:/visor-futbol8/work/visor-env/Scripts/python.exe'
$taskBallModels = 'S:/visor-futbol8/work/balon-fiabilidad/archive/visor-futbol8/work'
$taskBallResults = 'S:/visor-futbol8/work/balon-fiabilidad'
Push-Location outputs/visor-futbol8
$taskBallArgs = @('--video', 'S:/PRIMERA PARTE.MP4', '--models', $taskBallModels, '--records', "$taskBallModels/automatic-half/recovery-v5/records-v5.json", '--manifest', 'tests/balon/fixtures/native-benchmark.json')
& $taskBallPython -B -m tests.balon.benchmark_native_ball @taskBallArgs --tracker-ref b3711e2f --output "$taskBallResults/before" --repeats 3
& $taskBallPython -B -m tests.balon.benchmark_native_ball @taskBallArgs --output "$taskBallResults/after" --repeats 1 --compare-directory "$taskBallResults/before"
& $taskBallPython -B -m tests.balon.benchmark_native_ball @taskBallArgs --tracker-ref b3711e2f --replay-compare --output "$taskBallResults/replay" --repeats 7
$taskBallArrivalArgs = @('--video', 'S:/PRIMERA PARTE.MP4', '--models', $taskBallModels, '--records', "$taskBallModels/automatic-half/recovery-v5/records-v5.json", '--manifest', 'tests/balon/fixtures/native-arrival.json')
& $taskBallPython -B -m tests.balon.benchmark_native_ball @taskBallArrivalArgs --tracker-ref b3711e2f --output "$taskBallResults/before-arrival" --repeats 1
& $taskBallPython -B -m tests.balon.benchmark_native_ball @taskBallArrivalArgs --output "$taskBallResults/after-arrival" --repeats 1 --compare-directory "$taskBallResults/before-arrival"
Pop-Location
$env:TEMP = 'S:/visor-futbol8/work/tmp'
$env:TMP = $env:TEMP
& $taskBallPython -B -m unittest discover -s outputs/visor-futbol8/tests -t outputs/visor-futbol8
```

La medida completa ejecuta `native_ball.analyze_span` a 1920×1080 y 29,994 fps,
sin pose, con OpenCV a un hilo y cada sesión ONNX a cuatro. Excluye carga de
modelos y calentamiento, incluye decodificación, inferencias, cámara y asociación.
`--replay-compare` aísla el tracker con píxeles reales y candidatos de la caché:
excluye inferencias, decodificación y calibración del cronómetro, alterna las dos
versiones y exige igualdad exacta de sus salidas. No equivale al tiempo del flujo
completo. Cada secuencia reservada pertenece a una jugada diferente; no se han
ajustado umbrales con ninguna de ellas.

## 2026-10-27 · core/fase-0
- Código movido a esta carpeta sin cambios de lógica (Fase 0, ver PLAN.md §2.1).
- La firma de código de `native_ball.py` incluye los archivos en que se dividió `automatic_core.py`: la caché `native-ball-checkpoint` se invalidará una vez.
