# Cambios · web

Una entrada por PR fusionado, la más reciente arriba: fecha, rama y qué cambia para los demás módulos.

## 2026-10-27 · core/fase-0
- Código movido a esta carpeta sin cambios de lógica (Fase 0, ver PLAN.md §2.1).
- Los scripts están en `web/modulos/NN-nombre.js` y la página los carga en orden de nombre con versión por hash; ya no hay `?v=N` manual. Las URL antiguas (`/app.js`…) ya no existen.
