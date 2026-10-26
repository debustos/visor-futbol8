# PLAN de mejora por módulos · visor de fútbol 8

> **Para asistentes de IA (Claude, Copilot, Codex, Cursor…):** lee este archivo entero antes de editar código.
> 1. Averigua en qué **módulo** trabajas: mira el nombre de la rama (`mod/<módulo>/…`) o pregúntalo.
> 2. Edita **solo** archivos dentro de la carpeta de ese módulo (§3) y de su carpeta de tests.
> 3. Si necesitas cambiar algo fuera, **no lo edites**: crea una petición en `docs/peticiones/` (§5.4).
> 4. No reformatees, ni renombres ni muevas archivos de otros módulos, aunque mejore el estilo.
> 5. No cambies un contrato JSON (§4) sin seguir el procedimiento de cambio de contrato.
> 6. Antes de dar la tarea por terminada, ejecuta los tests (§6) e informa del resultado real.

---

## 1. Objetivo

Varias personas van a trabajar a la vez en este repositorio sin pisarse en GitHub. Para conseguirlo:

- **Cada módulo vive en su propia carpeta** y tiene un responsable.
- Los módulos se comunican **solo por contratos explícitos**: archivos JSON entre etapas y funciones públicas en `f8/core`.
- Los pocos archivos compartidos (lista de etapas, rutas HTTP, `index.html`) se sustituyen por **registros por módulo**, para que añadir algo no obligue a editar un archivo común.

Situación de partida: unos 60 módulos Python, 7 JS y 14 tests en una sola carpeta plana `outputs/visor-futbol8/`, con imports planos (`from automatic_core import *`). En ese estado, dos personas que toquen el motor acabarán editando `automatic_core.py`, `analysis_worker.py` o `server.py` y generando conflictos. Por eso hay una **Fase 0** de reestructuración antes del trabajo en paralelo.

---

## 2. Fases

| Fase | Quién | Qué | Paralelo |
|---|---|---|---|
| **0. Reestructuración** | 1 persona (integrador) | Mover archivos a carpetas por módulo, crear registros y contratos. Sin cambiar comportamiento | **No.** El resto no abre PR hasta que se fusione |
| **1. Mejoras por módulo** | Todos | Tareas de §7 dentro de su carpeta | Sí |
| **2. Integración** | Integrador + responsables | Análisis completo de la jornada 2 (ambas partes), comparación con la línea base y actualización de `VERIFICACION.md` | Al final de cada ciclo |

### 2.1 Fase 0 · Reestructuración (un único PR, sin cambios funcionales)

Reglas del PR de Fase 0:
- Usar solo `git mv` para que se conserve el historial. No reescribir lógica.
- Los ~200 tests deben pasar **antes y después** con el mismo resultado.
- Hay que repetir un análisis corto (el fragmento de 6 s ya usado en `pruebas-boton-analisis.json`) y comprobar que `profiles.json` sale idéntico.

Pasos:

1. **Paquete `f8/`** dentro de `outputs/visor-futbol8/` con la estructura de §3. Las carpetas de datos (`data/`, `automatic/`, `media/`, `jornadas/`, `aprendizaje/`, `training/`) **se quedan donde están**: son la raíz de ejecución y siguen ignoradas por Git.
2. **Imports absolutos**: `from automatic_core import X` pasa a `from f8.core.io import X`. Hay que eliminar el `import *` de `analyze_automatic.py`.
3. **Ejecutar etapas como módulos**: el worker lanza `python -m f8.<módulo>.<script>` con `cwd=outputs/visor-futbol8`, en lugar de `python script.py`.
4. **Recolocar los anclajes de ruta** que hoy dependen de `Path(__file__)`:
   - `runtime_context.py` (`MASTER`, `WORK`)
   - `server.py` (`ROOT`)
   - `analysis_jobs.py` (`master`)
   - `learning_jobs.py` (`parents[2]/'work'` y `with_name('review_learning.py')`)
   - `review_learning.py` (`--root` por defecto)

   Todos deben resolver la ruta mediante `f8/core/paths.py` (`APP_DIR`, `WORK_DIR`).
5. **Firmas de código**: `native_ball.py:164` y `visual_shots.py:38` calculan un hash leyendo archivos hermanos por nombre. Hay que actualizar las rutas. Esto invalidará una vez las cachés `native-ball-quality.json` y `visual-shot-quality.json`, y es lo esperado.
6. **Dividir `automatic_core.py`**, que ahora mezcla todo, según §3: E/S y ONNX → `core`; `Detector`, `MemoryTracker`, `kit`, `appearance` → `deteccion`; `select_ball` → `balon`; `Registrar`, `camera_step`, `project` → `campo`; `foot_contacts`, `infer_possession`, `action_candidates` → `acciones`; `jersey_vote`, `number_region` → `identidad`. Se deja un `automatic_core.py` de compatibilidad que solo reexporta y que se borra al final de la Fase 1.
7. **Registro de etapas** (§5.1): eliminar la lista `STEPS` de `analysis_worker.py`.
8. **Registro de rutas HTTP** (§5.2) y **carga de JS por módulo** (§5.3).
9. **Unificar las métricas**: hoy `METRICS` está en `domain.py` y `analytics_v3`, y `METRIC_MAP` en `sequence_engine.py`. Pasan a `f8/core/metricas.py`.
10. **`reanalizar.ps1`** debe llamar al mismo registro de etapas que el botón "Analizar" (`python -m f8.plataforma.pipeline --round N --half M`). Hoy ejecuta 15 etapas de las 24 y da resultados distintos.
11. **Código sin uso** → `legacy/`: `process_half.py`, `validate_half.py`, `commit_v3.py`, `validate_v3.py`, `train_appearance.py`, `visual_memory.py` (+ `upgrade_v3.py` si se confirma que `visual_memory_v5` lo sustituye). No se importa desde `f8/`.
12. **Infraestructura Git**: `.github/CODEOWNERS`, `.gitattributes` con `eol=lf` (§5.5), plantilla de PR y carpeta `docs/peticiones/`.

---

## 3. Mapa de módulos y carpetas

Raíz de código: `outputs/visor-futbol8/`. Cada módulo tiene su carpeta en `f8/`, sus tests en `tests/<módulo>/` y su `CHANGELOG.md` propio.

| Módulo | Carpeta | Archivos actuales que recibe | Responsable |
|---|---|---|---|
| **core** (compartido) | `f8/core/` | `runtime_context`, `write_json`, `ort_session`, `crop`, `iou`, métricas y esquemas de contratos | Integrador |
| **plataforma** | `f8/plataforma/` | `server`, `season_store`, `analysis_jobs`, `analysis_worker`, `registrar_jornada`, `domain`, `prepare_video`*, `make_playback` | _por asignar_ |
| **deteccion** | `f8/deteccion/` | `analyze_automatic` (scan), `Detector`, `MemoryTracker`, `kit`, `appearance`, `identity_stitch` | _por asignar_ |
| **balon** | `f8/balon/` | `refine_ball`, `adaptive_ball`, `native_ball`, `ball_tracker`, `ball_continuity`, `pose_contacts`, `select_ball` | _por asignar_ |
| **identidad** | `f8/identidad/` | `read_jersey_text`, `jersey_font`, `dorsal_guard`, `reference_bank`, `reference_sampling`, `far_identity`, `trajectory_identity`, `identity_recovery`, `visual_memory_v5`, `extract_appearance_parts`, `repair_identity_v5`, `contact_identity`, `jersey_vote` | _por asignar_ |
| **acciones** | `f8/acciones/` | `sequence_engine`, `pass_engine`, `ball_actions`, `automatic_fusion`, `temporal_actions`, `visual_shots`, `action_quality`, `foot_contacts`, `vendor/spot/` | _por asignar_ |
| **campo** | `f8/campo/` | `pitch_geometry`, `goal_geometry`, `Registrar`, `camera_step`, `project`, `prepare_video`* | _por asignar_ |
| **publicacion** | `f8/publicacion/` | `commit_v5`, `analytics_v3`, `presence_engine`, `make_gallery`, `export_heatmaps`, `validate_v5` | _por asignar_ |
| **revision** | `f8/revision/` | `analytics_review`, `learning_jobs`, `review_learning` | _por asignar_ |
| **web** | `web/` | `index.html`, `style.css`, `app.js`, `season-ui.js`, `automatic-ui.js`, `uncertainty-ui.js`, `action-diagnostics.js`, `native-detail.js`, `learning-ui.js` | _por asignar_ |
| **evaluacion** (nuevo) | `evaluacion/` | Nada de momento: conjunto de jugadas etiquetadas y medición de acierto | _por asignar_ |

\* `prepare_video` va en **campo**, porque calcula la proyección. La plataforma solo lo invoca como etapa.

Una persona puede llevar varios módulos. Lo que no puede pasar es que **dos ramas activas toquen el mismo módulo** salvo acuerdo explícito entre ellas.

---

## 4. Contratos entre módulos

Los módulos de visión ya se comunican por archivos JSON, y eso es lo que permite trabajar en paralelo. La Fase 0 los documenta como esquemas en `f8/core/contratos/<nombre>.schema.json`. Cada módulo valida en sus tests que lo que escribe cumple el esquema.

| Contrato | Lo escribe | Lo leen |
|---|---|---|
| `cache/scan.json`, `summaries.json`, `feature-rows.json`, `embeddings.npy` | deteccion | identidad, balon, revision |
| `cache/ball-refinement.json`, `automatic/dense-ball-quality.json`, `native-ball-quality.json` | balon | acciones, publicacion |
| `cache/recovery-v5/records-v5.json`, `identity-segments.json`, `identity-contexts.json`, `memory-quality.json` | identidad | publicacion, revision |
| `automatic/temporal-candidates.json`, `visual-shot-candidates.json` | acciones | publicacion |
| `pitch-calibration.json`, `automatic/geometry-views.json` | campo | deteccion, publicacion |
| `automatic/profiles.json`, `actions.json`, `lineup.json`, `uncertainties.json`, `quality.json`, `review-manifest.json`, `chunks/NNN.json` | publicacion | plataforma, revision, web |
| API HTTP `/api/...` (respuestas JSON) | plataforma, revision | web |

**Procedimiento de cambio de contrato:**
1. Los campos **nuevos y opcionales** se pueden añadir sin pedir permiso. Los lectores deben ignorar campos desconocidos.
2. **Renombrar, quitar o cambiar el significado** de un campo exige un PR propio que solo toque `f8/core/contratos/` y lleve la etiqueta `contrato`. Lo aprueban el integrador y los responsables de todos los módulos lectores. Después, cada lector adapta su código en su propio PR.
3. `null` significa **desconocido**, nunca cero. Esta regla del proyecto no se cambia.

---

## 5. Mecanismos anti-conflicto

### 5.1 Registro de etapas del pipeline

Cada módulo declara sus etapas en `f8/<módulo>/etapas.py`:

```python
ETAPAS = [
    # (orden, clave, etiqueta, módulo ejecutable, argumentos, peso de progreso)
    (210, 'ball', 'Siguiendo el balón', 'f8.balon.refine_ball', [], 12),
]
```

`f8/plataforma/pipeline.py` reúne todas las `ETAPAS` y las ordena por `orden`. Cada módulo usa su **rango reservado** y nadie edita una lista común:

| Rango | Módulo |
|---|---|
| 100–199 | campo (preparación) / deteccion |
| 200–299 | balon |
| 300–399 | identidad |
| 400–499 | acciones |
| 500–599 | publicacion |
| 900–999 | plataforma (reproducción, cierre) |

Las etapas con el mismo prefijo de rango se ejecutan en orden numérico. Si una etapa depende de la salida de otro módulo, lo indica en un comentario con el contrato concreto (§4). Para intercalar una etapa entre dos de otro módulo (hoy `dorsal_guard` se ejecuta antes y después de `native_ball`) se usan números intermedios del propio rango de identidad. Si eso no basta, se abre una petición.

### 5.2 Registro de rutas HTTP

Hoy `server.py` concentra unas 60 rutas en una sola función `route()`. Tras la Fase 0, cada módulo con API la expone en `f8/<módulo>/api.py`:

```python
RUTAS = {('GET', r'/api/review/queue'): lambda app, req: app.review_engine.queue()}
```

`server.py` (plataforma) solo importa y combina los `RUTAS`. Así, revisión añade endpoints sin tocar `server.py`.

### 5.3 Frontend por módulo

- Cada vista tiene su archivo en `web/modulos/<vista>.js` y `web/modulos/<vista>.css`.
- `index.html` carga una lista declarada en `web/modulos.json`. Una línea por archivo y en orden alfabético reduce los conflictos a líneas independientes.
- El cache-busting `?v=N`, que hoy se edita a mano en `index.html`, se sustituye por un hash que calcula el servidor. Así deja de ser un punto de conflicto.

### 5.4 Peticiones entre módulos

Cuando necesitas un cambio en una carpeta que no es tuya:
1. Crea `docs/peticiones/AAAA-MM-DD-<de>-a-<para>-<tema>.md` con qué necesitas, por qué y qué contrato afecta. Un archivo nuevo por petición nunca entra en conflicto.
2. Mientras tanto, trabaja con un adaptador **dentro de tu carpeta** (por ejemplo, leer un campo opcional si existe).
3. Lo cierra el responsable del módulo destino, en su rama, con referencia a la petición.

### 5.5 Reglas Git

- **Ramas**: `mod/<módulo>/<tema-corto>` (por ejemplo `mod/balon/detector-portería`). Las ramas transversales, `core/<tema>` o `contrato/<tema>`, solo las abre el integrador.
- **PR pequeños**: un objetivo por PR, sin pasar de ~400 líneas cambiadas salvo que se mueva código. Rebase sobre `main` antes de pedir revisión.
- **CODEOWNERS** (`.github/CODEOWNERS`): cada carpeta `f8/<módulo>/`, `tests/<módulo>/` y `web/` exige la aprobación de su responsable. `f8/core/` y `PLAN.md` exigen la del integrador. Hay que activar la protección de rama en `main` (PR obligatorio y tests en verde).
- **Finales de línea**: el equipo trabaja en Windows. En `.gitattributes` va `* text=auto eol=lf`, con `*.ps1` y `*.cmd` en `eol=crlf`. Sin esto, un cambio de CRLF marca el archivo entero como modificado.
- **Formato**: el código actual es muy denso (muchas sentencias por línea). **No se reformatea un archivo entero en un PR con cambios de lógica.** Cada responsable puede reformatear su carpeta en un PR aparte, solo de formato y sin otros cambios, avisando antes. Nadie reformatea carpetas ajenas.
- **Datos**: nunca subir vídeos, pesos, SQLite, cachés ni JSON generados (ya están en `.gitignore`). Los fixtures de tests van en `tests/<módulo>/fixtures/`, pequeños y sintéticos o recortados.
- **Documentación**: cada módulo anota sus cambios en `f8/<módulo>/CHANGELOG.md`. Los informes históricos (`MEJORA-*.md`, `RESULTADO.md`) se mueven a `docs/historico/` en la Fase 0 y no se vuelven a editar. Solo el integrador actualiza `VERIFICACION.md`, en la Fase 2.

---

## 6. Tests y verificación

```powershell
# todos
.\work\vision-env\Scripts\python.exe -B -m unittest discover -s outputs/visor-futbol8/tests -t outputs/visor-futbol8
# solo un módulo
.\work\vision-env\Scripts\python.exe -B -m unittest discover -s outputs/visor-futbol8/tests/balon -t outputs/visor-futbol8
```

- Todo PR debe pasar **todos** los tests, no solo los de su módulo.
- Los tests no deben requerir `work/` (modelos) ni vídeos reales. Lo que necesite modelos se marca con `@unittest.skipUnless(MODELOS_DISPONIBLES, ...)`.
- Recomendado: GitHub Actions en Windows que ejecute los tests sin modelos en cada PR (`.github/workflows/tests.yml`, del integrador).
- **Pasar los tests no demuestra que el análisis acierte en el vídeo.** Toda mejora de precisión se demuestra con la medición de `evaluacion/` (§7.10), contra la línea base.

---

## 7. Plan de mejora por módulo

Las prioridades salen de los informes actuales: balón localizado en el 48,6 % de las muestras, identidad en el 59 % de las detecciones, gol conocido detectado 0 de 1, segunda parte de la jornada 2 sin terminar y cinco jugadores sin observaciones fiables.

Cada tarea indica su **criterio de aceptación**. P1 = prioridad alta.

### 7.1 core (integrador)
- P1. Ejecutar la Fase 0 completa.
- P1. `f8/core/paths.py`, `f8/core/metricas.py` y los esquemas de `f8/core/contratos/`.
- P2. Borrar el shim `automatic_core.py` cuando ningún módulo lo importe.
- **No hace**: lógica de visión ni de negocio.

### 7.2 plataforma
- P1. **Terminar y robustecer la segunda parte de la jornada 2**: reproducir el fallo de la fase de jugadas y permitir reanudar desde la última etapa completada, sin repetir la detección. *Aceptación: jornada 2 con 2 de 2 partes analizadas.*
- P1. **Quitar los valores fijos de la primera versión**:
  - `media/primera-compatible.mp4` → `media/reproduccion.mp4`, con migración del nombre antiguo;
  - nombres de exportación "primera-parte" → incluir jornada y parte;
  - `App.export()` con `'part':'primera'` fijo;
  - `seed_current` asume la jornada 2 y busca `SEGUNDA PARTE.MP4`;
  - `probe()` deduce la parte de si el nombre contiene "PRIMERA".
- P1. `reanalizar.ps1` debe usar el mismo pipeline que el botón (en coordinación con core durante la Fase 0).
- P2. Registro de rutas (§5.2) y separar `server.py`, que hoy tiene ~60 rutas en un solo `route()`.
- P2. Comprobación de que los modelos de `modelos.json` están presentes antes de encolar (verificando los SHA-256), con un error claro.
- P3. Instalación desde cero comprobada en un equipo limpio (pendiente según `VERIFICACION.md`).
- **No hace**: modificar etapas de visión ni la lógica de revisión.

### 7.3 deteccion
- P1. Medir y reducir los cortes de trayectoria del `MemoryTracker`: transiciones nombre ↔ sin nombre por minuto, con el informe de `trajectory_identity` como métrica.
- P2. Hacer configurables los umbrales HSV de `kit()` por partido (equipación rival distinta), en `pitch-calibration.json` o un `equipaciones.json` por jornada.
- P2. Evaluar un detector de personas mayor o afinado con tomas reales, en comparación con YOLO11s.
- **No hace**: OCR ni nombres. Entrega cajas, kit y `track_id`.

### 7.4 balon (impacto directo en pases, tiros y goles)
- P1. **Conjunto de evaluación del balón** (con evaluacion): fotogramas reales anotados (centro del balón o "no visible") en vuelo, desenfoque, oclusión y fondo de portería. *Métrica: precisión y recall de localización, con la línea base actual.*
- P1. Afinar el detector con esas tomas. *Aceptación: subir del 48,6 % sin aumentar las falsas detecciones (por ejemplo, la bota blanca confundida con el balón).*
- P2. Recuperar el balón en la llegada a portería del gol del 15:44, donde ahora se pierde.
- **Regla**: nunca interpolar. Un balón devuelto siempre es una medida del detector.

### 7.5 identidad
- P1. Cobertura de los jugadores sin observaciones fiables (Lain, Mayora, Fernandito, Alfaro, Resu): comprobar primero si jugaron. Si lo hicieron, conseguir referencias por dorsal. *Aceptación: nombre aceptado solo con evidencia de dorsal o revisión, nunca por descarte.*
- P1. Identidad lejana (<80 px): el especialista funciona a 68 % en la prueba interna, pero Busi solo tiene 2 contextos. Validarlo en la segunda parte y en otros partidos.
- P2. `jersey_vote`: el dorsal 9 se confunde con un 5 y hay recortes 99→9, 16→6, 41→14. Añadir tests con esos casos.
- **No hace**: decidir acciones. Entrega `player_id` por caja y trayectoria.

### 7.6 acciones
- P1. **Tiros y goles**: hoy son solo propuestas temporales. Combinar el vuelo medido del balón (balon), los postes (campo) y la salida tras contacto. *Primera condición de aceptación: recuperar el gol de Busi del 15:44 a partir del vídeo, sin introducirlo como regla.*
- P2. Separar pase, despeje y tiro según la dirección del vuelo hacia la portería, y no solo por el cambio de poseedor.
- P2. Faltas, regates y pérdidas: siguen como candidatos hasta tener evaluación propia. No promoverlos a estimados para inflar recuentos.
- **No hace**: atribuir nombres. Usa el `player_id` que le llega.

### 7.7 campo
- P1. Dimensiones y correspondencias reales de un campo F8 para una calibración métrica. Hoy el plano es relativo.
- P2. Sustituir los tiempos fijos de referencia de `make_registrar` (60/300/994/1200 s, propios del primer vídeo) por una selección automática de vistas.
- P2. Inferir la dirección de ataque sin depender del portero (`season_store.part_info`), o al menos exponer la inferencia como contrato de campo.
- P3. Detectar ambas porterías y su línea en cada encuadre (requisito de 7.6).

### 7.8 publicacion
- P1. **Conservar las revisiones al reanalizar**: hoy `source_key` incluye el hash de `scan.json` (`commit_v5.py:29`). Si se repite la detección, todas las decisiones humanas dejan de aplicarse. Diseñar con revision un mapeo de decisiones antiguas a la nueva base: por tiempo + trayectoria, y si no hay correspondencia clara, pendiente de nueva revisión. *Aceptación: un test reanaliza y comprueba que las decisiones con correspondencia única se mantienen.*
- P2. Separar `commit_v5.commit()` (una función de ~60 líneas muy densas) en pasos testeables.
- P2. Corregir el docstring de `validate_v5.py` (dice "v3").
- **No hace**: cambiar el significado de `null`, "candidato" o "estimado" en las fichas.

### 7.9 revision
- P1. Mapeo de decisiones entre versiones del análisis (junto con publicacion, ver 7.8).
- P1. **Validar el aprendizaje desde revisiones** con revisiones reales: ¿mejora la identidad en contextos reservados? Si no, desactivarlo por defecto.
- P2. Unificar los dos sistemas de revisión: el manual antiguo (tabla `items` + `domain.validate_event`) y el automático (`automatic_reviews`). Decidir cuál queda y migrar.
- P2. Las validaciones de asistencia y gol están duplicadas en `server.validate_context` y en `ReviewEngine.validate`. Dejar una sola implementación.

### 7.10 evaluacion (nuevo, transversal pero aditivo)
- P1. Formato de anotación de jugadas verificadas (gol del 15:44, pases completados, controles, despejes, paradas, ejemplos **sin** acción) en `evaluacion/anotaciones/jNNN-pM.json`.
- P1. Script `python -m evaluacion.medir --round N --half M` que compare `actions.json` y `profiles.json` con las anotaciones. Debe dar precisión y recall por acción y acierto de atribución por jugador, **por separado**.
- P1. Particiones por **secuencia completa**: fotogramas vecinos de una jugada no se reparten entre entrenamiento y prueba.
- P2. Una línea base guardada (`evaluacion/linea-base.json`) para que cada PR de visión muestre su efecto.
- Este módulo solo lee contratos; nunca los escribe.

### 7.11 web
- P1. Dividir en `web/modulos/` (§5.3) y quitar el `?v=N` manual.
- P2. `app.js` contiene la interfaz de la revisión manual antigua. Alinearla con la decisión de 7.9.
- P2. Mostrar las métricas de `evaluacion` (precisión medida) junto a las fichas cuando existan.
- **No hace**: calcular estadísticas en el navegador. Muestra lo que devuelve la API.

---

## 8. Dependencias entre tareas

```
Fase 0 (core) ──► todo lo demás
evaluacion 7.10 ──► medir mejoras de balon 7.4, identidad 7.5, acciones 7.6
balon 7.4 + campo 7.7 (porterías) ──► acciones 7.6 (tiros/goles)
publicacion 7.8 ⇄ revision 7.9 (conservar revisiones): PR coordinado
plataforma 7.2 (2.ª parte) ──► integración Fase 2
```

Las tareas sin flecha pueden empezar en cuanto termine la Fase 0.

---

## 9. Checklist de PR

- [ ] La rama sigue `mod/<módulo>/<tema>` y solo toca `f8/<módulo>/`, `tests/<módulo>/` y `f8/<módulo>/CHANGELOG.md`.
- [ ] Los cambios fuera de mi carpeta están justificados por una petición en `docs/peticiones/` y aprobados por su responsable.
- [ ] No hay reformateos de archivos ajenos ni cambios de fin de línea.
- [ ] Los contratos JSON no cambian, o solo se añaden campos opcionales.
- [ ] Todos los tests pasan (pegar el resultado en el PR).
- [ ] Si afecta a la precisión: resultado de `evaluacion` frente a la línea base.
- [ ] No hay vídeos, pesos, SQLite ni JSON generados en el diff.
