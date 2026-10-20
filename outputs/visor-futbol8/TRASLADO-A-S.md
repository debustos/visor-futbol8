# Proyecto trasladado al disco S:

La carpeta principal es `S:\visor-futbol8`. Abre `S:\visor-futbol8\ABRIR-VISOR.cmd` para iniciar el visor en http://127.0.0.1:8768/.

Se han trasladado código, modelos, entorno de Python, datos, vídeos compatibles, cachés, revisiones, registros y pruebas. Los vídeos originales ya estaban en `S:\PRIMERA PARTE.MP4` y `S:\SEGUNDA PARTE.MP4`; conservan su ubicación.

La copia del proyecto y su Python se verificó con SHA-256: 56.323 archivos y 7.434.060.323 bytes, sin diferencias. Después se actualizaron las rutas y se comprobó la integridad de 34 bases de datos. Las 89 pruebas pasaron desde S:, el navegador verificó fichas, mapas, revisión y diseño móvil, y el detector procesó un fotograma original mediante DirectML.

Las carpetas anteriores `outputs`, `work` y `Ultralytics` en C: son enlaces a S:. Los archivos originales del proyecto en C: se retiraron después de verificar la nueva instalación. Los enlaces conservan las rutas antiguas sin duplicar el proyecto. Se liberaron aproximadamente 4.30 GiB en C:.

El análisis de la segunda parte ya estaba interrumpido en la fase de jugadas antes del traslado. Se conservan sus detecciones y el estado de error; el visor ofrece Reintentar análisis. La primera parte conserva sus resultados y revisiones.

Los informes son `verificacion-traslado.json`, `traslado-a-s.json` y `pruebas-runtime-en-s.json`.
