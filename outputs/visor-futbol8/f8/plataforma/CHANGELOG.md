# Cambios · plataforma

Una entrada por PR fusionado, la más reciente arriba: fecha, rama y qué cambia para los demás módulos.

## 2026-10-27 · develop · biblioteca local
- Carpeta configurada una vez, detección por temporada/jornada/parte y comprobación
  en segundo plano al abrir el visor o desde el botón. Registra usando SeasonStore,
  conserva partes existentes y revisiones y no inicia el análisis automáticamente.
- SHA-256, metadatos y decodificación de tres muestras; archivos recientes,
  temporales, ambiguos y cambiantes se dejan pendientes. Las comprobaciones de
  vídeos y modelos sin cambios se reutilizan para evitar lecturas completas.
- Catálogo portable con intervalos, huella del original y grupos desarrollo/reserva;
  importación sin sobrescribir IDs incompatibles y protección ante solapamientos.
- Rutas declaradas por módulo con token de temporada; manual en BIBLIOTECA.md.
- Corregida la comprobación de ruta de preparar-proyecto.py tras la Fase 0,
  necesaria para preparar una instalación vacía con la biblioteca.
- Verificación: 238 tests OK (13 nuevos de biblioteca y preparación), sintaxis JS
  y `git diff --check`. Navegador con vídeo sintético aislado: configuración,
  alta de jornada, ejemplo 0,5–1,5 s, pausa al final y recarga sin duplicados.
  No se han ejecutado modelos ni modificado datos de partidos reales.

## 2026-10-27 · core/fase-0
- Código movido a esta carpeta sin cambios de lógica (Fase 0, ver PLAN.md §2.1).
- Las etapas del análisis se declaran en `f8/<módulo>/etapas.py` y las reúne `pipeline.py`; `analysis_worker.STEPS` se calcula a partir de ellas con el mismo orden.
- `reanalizar.ps1` usa ahora el mismo pipeline y cola que el botón Analizar (antes ejecutaba 15 de las 24 etapas).
- Rutas HTTP declarables por módulo en `f8/<módulo>/api.py` (`rutas.py`); la página se genera con `paginas.py`.
