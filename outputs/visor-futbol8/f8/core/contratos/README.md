# Contratos entre módulos

Los módulos se comunican mediante estos archivos. Quien **escribe** un contrato no cambia el significado de sus campos sin seguir el procedimiento de [PLAN.md §4](../../../../../PLAN.md). Quien **lee** ignora los campos que no conoce.

Rutas: `ROOT` es la raíz de la parte analizada (`outputs/visor-futbol8` o `jornadas/jNNN/parte-N`). `CACHE` es su caché en `work/` (ver `f8/core/runtime_context.py`).

> Estado: inventario hecho en la Fase 0 a partir del código. Los esquemas formales (`<nombre>.schema.json`) y su validación en tests están **pendientes**. Es la primera tarea de core en la Fase 1. Hasta entonces, esta tabla y el código productor son la referencia.

| Contrato | Escribe | Leen | Campos principales |
|---|---|---|---|
| `CACHE/scan.json` | deteccion (`analyze_automatic --scan-only`) | identidad, balon, publicacion | lista por muestra: `frame`, `time`, `tracks[]` (`id`, `box`, `confidence`, `kit`, `kit_score`, `position`), `ball`, `calibration`, `possession` |
| `CACHE/summaries.json`, `feature-rows.json`, `embeddings.npy` | deteccion | identidad, revision | resumen por tracklet (`id`, `kit_counts`, `embedding_rows`, `ocr_candidates`); filas de embeddings |
| `CACHE/labels.json`, `ROOT/automatic/jersey-evidence.json` | deteccion (`--resume`) | deteccion (`--reuse-ocr`), identidad | `track_id → {number, evidence}` |
| `ROOT/pitch-calibration.json`, `automatic/geometry-views.json` | campo | deteccion, publicacion, revision | `matrix` (o `null` si no hay proyección); vistas con `frame`, `time`, `state`, `reason` |
| `ROOT/automatic/temporal-candidates.json` | acciones (`temporal_actions`) | publicacion, deteccion | `time`, `class`, `score` |
| `CACHE/ball-refinement.json`, `automatic/ball-refinement-quality.json`, `dense-ball-quality.json`, `ball-continuity-quality.json`, `native-ball-quality.json` | balon | deteccion, publicacion | balón medido por muestra (nunca interpolado); calidad con `source_key`/`source` |
| `CACHE/recovery-v5/records-v5.json`, `identity-segments.json`, `identity-contexts.json`, `memory-quality.json` | identidad | publicacion, revision | muestras con `player_id` e `identity` por caja; contextos con `id`, `player_id`, `raw_track_ids`, `start`, `end` |
| `ROOT/automatic/reference-bank-quality.json`, `far-identity-quality.json`, `dorsal-guard-quality.json` | identidad | publicacion | calidad con `source_fingerprint` |
| `ROOT/automatic/visual-shot-candidates.json`, `visual-shot-quality.json` | acciones | publicacion | propuestas de tiro con su evidencia |
| `ROOT/automatic/profiles.json` | publicacion | plataforma, revision, web | por jugador: `id`, `jersey_number`, `nickname`, `samples`, `visible_seconds`, `metrics{clave: {value, confirmed_value, detected_value, candidates, state}}`, `heatmap_points[]`, `actions[]` |
| `ROOT/automatic/actions.json` | publicacion | revision, plataforma, web | `id`, `kind`, `time`, `player_id`, `receiver_id`, `state` (`estimated`/`candidate`), `outcome`, `source_track`, `target_track`, `sequence` |
| `ROOT/automatic/uncertainties.json` | publicacion | revision, web | cola de revisión: `id`, `category` (`identity`/`event`/`lineup`/`substitution`/`geometry`), `priority`, `time`, intervalos de evidencia |
| `ROOT/automatic/review-manifest.json` | publicacion | revision, plataforma | `source_key`: las decisiones humanas solo se aplican a esta versión del análisis |
| `ROOT/automatic/lineup.json`, `quality.json`, `status.json`, `chunks/NNN.json` | publicacion | plataforma, revision, web | alineación probable, diagnóstico, estado y muestras por minuto |
| API `/api/...` | plataforma, revision | web | respuestas JSON; `null` es desconocido |

Reglas que no cambian:
- `null` significa **desconocido**, nunca cero.
- Los candidatos no suman como estimados ni como confirmados.
- Ningún módulo inventa posiciones del balón ni de jugadores en los huecos.
