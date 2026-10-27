# Cambios · web

## 2026-10-27 · develop · biblioteca de vídeos
- Módulo 80 con configuración persistente, estado de incorporación y modelos,
  ejemplos por intervalos, reproducción y catálogo exportable/importable.
- La comprobación se consulta sin bloquear las vistas existentes; nuevos registros
  actualizan la tabla de jornadas. Layout adaptado a pantallas pequeñas.

Una entrada por PR fusionado, la más reciente arriba: fecha, rama y qué cambia para los demás módulos.

## 2026-10-27 · core/fase-0
- Código movido a esta carpeta sin cambios de lógica (Fase 0, ver PLAN.md §2.1).
- Los scripts están en `web/modulos/NN-nombre.js` y la página los carga en orden de nombre con versión por hash; ya no hay `?v=N` manual. Las URL antiguas (`/app.js`…) ya no existen.
