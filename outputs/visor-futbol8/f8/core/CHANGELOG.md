# Cambios · core

Una entrada por PR fusionado, la más reciente arriba: fecha, rama y qué cambia para los demás módulos.

## 2026-10-27 · core/fase-0
- Código movido a esta carpeta sin cambios de lógica (Fase 0, ver PLAN.md §2.1).
- `automatic_core.py` dividido entre `core/io.py`, `deteccion/modelos.py`, `campo/proyeccion.py`, `identidad/dorsales.py`, `balon/seleccion.py`, `acciones/contactos.py` y `publicacion/alineacion_basica.py`. `f8/automatic_core.py` solo reexporta y se borrará al cerrar la Fase 1.
- Nuevos `core/paths.py` (rutas fijas), `core/metricas.py` (las once métricas y `METRIC_MAP`, antes en tres sitios) y `core/registro.py`.
