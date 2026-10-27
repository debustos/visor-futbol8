# Cambios · plataforma

Una entrada por PR fusionado, la más reciente arriba: fecha, rama y qué cambia para los demás módulos.

## 2026-10-27 · core/fase-0
- Código movido a esta carpeta sin cambios de lógica (Fase 0, ver PLAN.md §2.1).
- Las etapas del análisis se declaran en `f8/<módulo>/etapas.py` y las reúne `pipeline.py`; `analysis_worker.STEPS` se calcula a partir de ellas con el mismo orden.
- `reanalizar.ps1` usa ahora el mismo pipeline y cola que el botón Analizar (antes ejecutaba 15 de las 24 etapas).
- Rutas HTTP declarables por módulo en `f8/<módulo>/api.py` (`rutas.py`); la página se genera con `paginas.py`.
