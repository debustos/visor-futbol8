# Cambios · acciones

Una entrada por PR fusionado, la más reciente arriba: fecha, rama y qué cambia para los demás módulos.

## 2026-10-27 · mod/acciones/goles-faltas (borrador, aceptación pendiente)

- Se conservan tiros/goles rivales y sin autor; la salida medida permite proponer
  equipo/contacto, pero no nombrar al goleador mediante un cuerpo próximo.
- Se agrupan etiquetas compatibles de tiro/gol conservando toda su evidencia;
  no se encadenan ventanas ni se fusionan eventos de una misma clase cercanos.
- Faltas sin autor ni rol deducidos del poseedor. Las señales de falta y saque de
  centro se adjuntan como evidencia candidata, nunca confirman una acción.
- Búsqueda temporal completa independiente del balón, con PTS del MOV y caché
  de muestras ligada al origen y al código. Las ventanas temporales también
  abren revisión visual aunque falte balón. No se inventan medidas en los huecos.
- Se conservan propuestas con tiempos inválidos en diagnóstico; no pasan a
  acciones. `review_candidates` exporta resultados aislados para evaluación.
- Orientación temporal explícita `display` (por defecto) o `encoded`, registrada
  en calidad y en la caché. Corrige entradas con matriz de rotación incompatible
  con la imagen del campo sin una regla de jornada. Los clips mantienen audio,
  PTS y orientación; registros y candidatos deben compartir coordenadas.
- Coordinación pendiente en
  [petición a publicación/evaluación](../../../../../docs/peticiones/2026-10-27-acciones-a-publicacion-evaluacion-evidencia.md).

### Recorrido auditado antes de editar

Registro declarado: `temporal` (30) → publicación contextual (130) →
`visual_shots` (190) → publicación final (200).
`temporal_actions` produce `automatic/temporal-candidates.json` a partir del
vídeo; la fusión intermedia de detección usa `automatic_fusion.enrich`.
`visual_shots` añade `visual-shot-candidates.json` y su calidad. `commit_v5`
valida la procedencia visual, concatena ambas entradas y llama a
`sequence_actions(..., short_contacts=True)`; publica acciones y la cola sin
exigir autor. Las fichas filtran por `player_id`. Se eliminan el descarte rival
de secuencia y la dependencia de nombre en la fusión intermedia. La publicación
actual no valida la procedencia temporal: se solicita su corrección al módulo.

**Diferencia entre registro y ejecución activa:** `analysis_worker.py` importa
`pipeline_steps` pero `run()` pasa todavía su `STEPS` local con scripts planos
a `Pipeline`. Esos archivos se buscan dentro de `f8/plataforma/` y ya no están.
Se solicita reparar el worker en plataforma. Las ejecuciones reales de esta rama
son por módulos explícitos en un destino aislado; no prueban el botón Analizar.

En el checkout compartido, ambas partes de jornada 4 tenían solo metadatos y
estado `waiting/pending`; no había scan, OCR, trayectorias, candidatos ni modelos.
Se recuperó únicamente el peso temporal declarado y se preparó un entorno local
ignorado. No se ha ejecutado detección de balón/identidades ni reconstruido
porterías sin sus recursos. No se usan los fragmentos seleccionados antes como
referencia de acierto.

### Verificación y reproducción

Base: `origin/develop` = `b97c6e21a01f48b65d626a0dc501575fb472e951`.
Modelo: E2E-Spot SoccerNet-v2 `soccer_rny002gsm_gru_rgb/checkpoint_088.pt`,
SHA-256 `2d8376e96198c07f3e73c1712ffb1a4b2524feb4baa609479935c86d6eeb4ba3`.
Python 3.12; torch 2.14.1, torchvision 0.29.1, timm 1.0.30, OpenCV 5.0.0.93,
NumPy 2.5.4, SciPy 1.18.1, scikit-learn 1.9.1. Bibliotecas instaladas solo en
`work/test-runtime` y `work/temporal-runtime`; sin cambios de requirements.

Comandos desde la raíz del checkout aislado (añadir ambos runtimes a PYTHONPATH
y `outputs/visor-futbol8` para ejecutar los módulos):

```powershell
# Suite completa exigida por PLAN.md, con el intérprete disponible equivalente
& $python -B -m unittest discover -s outputs/visor-futbol8/tests -t outputs/visor-futbol8
# Comparación sintética: mismo script, entradas y 101 repeticiones por caso
& $python -B outputs/visor-futbol8/tests/acciones/benchmark_proposals.py --code-root work/baseline/outputs/visor-futbol8
& $python -B outputs/visor-futbol8/tests/acciones/benchmark_proposals.py --code-root outputs/visor-futbol8
# Cada parte usa FOOTBALL_CACHE_ROOT diferente bajo work/goal-foul-validation
& $python -B -u -m f8.acciones.temporal_actions --source $MOV --output $aislado
# Si la matriz de presentación deja el campo girado, elección explícita:
& $python -B -u -m f8.acciones.temporal_actions --source $MOV --orientation encoded --output $aislado
& $python -B -m f8.acciones.video_time --source $MOV --output $indicePTS
& $python -B -m f8.acciones.review_candidates --temporal $candidatos --source $MOV --duration $duracion --output $revision
# Añadir --ffmpeg <ejecutable> exporta todos los intervalos agrupados con audio
```

Suite base: **238 OK**, 30,631 s. Comparación sintética inicial, mediana por
invocación en el mismo equipo:

Suite final: **259 OK**, 15,807 s (incluye HTTP/E/S; estos tiempos de suite no
son una medición de velocidad del detector). Regresiones de acciones: equipo
rival, autor ausente, pérdida de balón, tiros sin gol, duplicados, contacto sin
falta, tiempos incorrectos, huella de origen y orientación de coordenadas.

| Caso | Antes | Después | Tiempo antes/después |
|---|---|---|---|
| Gol rival con salida medida | descartado | candidato rival sin nombre naranja | 0,243/0,277 ms |
| Gol sin autor | conservado | conservado con evidencia | 0,019/0,029 ms |
| Tiro fuera | tiro candidato | tiro candidato | 0,021/0,029 ms |
| Gol + tiro solapados | 2 propuestas | 1 con ambas evidencias | 0,028/0,037 ms |
| Falta junto a poseedor conocido | atribuida al poseedor | rol/autor pendientes | 0,152/0,176 ms |
| Tiempo incoherente con PTS | admitido | diagnóstico, fuera de acciones | 0,018/0,013 ms |

Estos casos demuestran regresiones de software, no precisión deportiva. La
aceptación de cero goles omitidos/inventados exige las anotaciones y el evaluador
independiente. No se declaran recuentos del partido certificados.

### Resultados reales disponibles (sin anotaciones de aceptación)

MOV originales, sin reconversión previa: primera parte 1.469,808333 s,
44.086 fotogramas, 1.618.372.473 bytes; segunda 1.585,730 s, 47.563 fotogramas,
1.747.053.158 bytes. Se decodifican todas las muestras del archivo, se infiere
a 2 Hz y se revisan intervalos candidatos; no se usan anotaciones para buscar.

Primera parte completa: **35 etiquetas temporales; 0 Goal, 9 Foul y 1 Shots off
target**. Tiempo 520,05 s, 2.940 muestras. Máximo score Goal **0,0164283**, inferior
al umbral previo de 0,2, que no se ha ajustado con esta jornada. El motor anterior
y el nuevo conservan las mismas 10 propuestas de acción anónimas con estas
entradas reales: mediana 101 repeticiones **0,185 → 0,440 ms** (solo secuencia;
se reutilizan las mismas probabilidades/candidatos, sin repetir inferencia).

Se exportan sus 9 intervalos agrupados, con las 10 acciones conservadas. Los
9 clips tienen exactamente el número de fotogramas originales cuyos PTS caen
en el intervalo (509–555 por clip); correlación gris del primer fotograma
original/exportado **0,9913–0,9952** tras compresión. Se usa el siguiente PTS
disponible si el inicio cae entre fotogramas, sin desplazar la secuencia por FPS
medio. Auditoría completa de tiempos: 193,282 s; error máximo frame/FPS frente
a PTS **1,760 ms**. Exportación con audio: 39,125 s adicionales a 4,391 s de
preparación de secuencia.

Observaciones de revisión, **no anotaciones verificadas ni TP/FP**:

| Intervalo original, parte 1 | Propuesta | Evidencia y límite |
|---|---|---|
| 177,500–194,500 s | Falta, score 0,8226 | Contacto e interrupción; decisión y roles pendientes |
| 417,511667–434,511667 s | Falta, score 0,8370 | Caída e interrupción visibles; falta/autor pendientes |
| 722,503333–739,503333 s | Tiro fuera, score 0,2544 | Pausa/cambio de encuadre; no basta para certificar tiro ni gol |

Segunda parte obedeciendo la rotación de presentación: 567,27 s, 3.172 muestras,
una etiqueta Kick-off y **0 goles/tiros/faltas**. Máximo Goal **0,0044267**,
máximo Foul **0,0095383**. Se inspeccionó la entrada y el campo estaba de lado;
los píxeles codificados son 1920×1080, la matriz declarada gira 90°. Esta salida
se conserva aparte; se repite únicamente la etapa temporal con `--orientation
encoded`. Error máximo de frame/FPS frente a PTS **1,795 ms**.

Segunda parte con orientación explícita corregida: **32 etiquetas; 0 Goal,
0 tiros, 1 Foul**, 3.172 muestras, 418,49 s. Máximo Goal **0,0096791**. La falta
se propone en 1.186,521667 s (score 0,4508), con contexto
1.181,521667–1.198,521667 s; se observa una caída/interrupción pero permanecen
pendientes decisión arbitral, infractor y receptor. Su clip tiene 509 fotogramas,
los mismos que el intervalo original por PTS, orientación 0° y correlación gris
inicial 0,992176. Exportación: 3,078 s; preparación: 2,750 s. Sobre las mismas
32 etiquetas, secuencia anterior/nueva: **0,034 → 0,177 ms**, 101 repeticiones,
una falta conservada en ambos casos. Los tiempos de inferencia con orientaciones
distintas son descriptivos y no una comparación controlada de rendimiento.

La etapa visual de primera parte se ejecutó sin registros disponibles, como
comprobación explícita de ese caso: **9 ventanas, 154,5 s de vídeo, 1.544 imágenes**
en 22,33 s; antes el selector con esos mismos registros vacíos devolvía cero
ventanas. Resultado: cero muestras de balón/portería y cero propuestas visuales,
sin generar goles de la ausencia de datos. Esto demuestra cobertura de revisión,
no detección de goles. No se ejecutan etapas de OCR/detección sin sus recursos.

Las salidas, probabilidades, clips y comprobaciones están solo en
`work/goal-foul-validation/` del checkout aislado y no se suben a Git. El módulo
`evaluacion` de la base sigue vacío: TP, FP, FN y acierto de equipo/autor no son
calculables aún. **La aceptación de cero goles omitidos/inventados no está
demostrada**. Tampoco se dispone de trayectorias/porterías de jornada 4 para
clasificar automáticamente paradas, despejes o cruces de línea.

## 2026-10-27 · core/fase-0
- Código movido a esta carpeta sin cambios de lógica (Fase 0, ver PLAN.md §2.1).
- `vendor/spot` se mueve a `f8/acciones/vendor/spot`. La firma de `visual_shots.py` apunta a `f8/campo/goal_geometry.py` (sin cambio de contenido).
