# Cambios · identidad

Una entrada por PR fusionado, la más reciente arriba: fecha, rama y qué cambia para los demás módulos.

## 2026-10-27 · mod/identidad/fiabilidad-rendimiento (pendiente de integración)

Base: Fase 0, `b3711e2`. Copia aislada en el worktree `identidad-fiabilidad`.

- Causa: `local_dorsal_guard` tenía nivel de evidencia 4, pero faltaba en `HARD` de `trajectory_identity.py`. Al estabilizar de nuevo, una corrección local podía absorber otro dorsal aceptado y extender su nombre al segmento incompatible. Se añade como ancla que corta el contexto ante contradicción, conservando continuidad en observaciones desconocidas compatibles.
- `dorsal_guard.py`: reutiliza relecturas por fotograma, tiempo, track y caja exacta. La huella exige vídeo (ruta, tamaño, mtime), SHA-256 de scan, código, pesos OCR y versiones. Reutiliza también resultados vacíos; reintenta fallos de decodificación. El lector y el vídeo se abren solo si hay alguna lectura pendiente. La nueva caché interna es `CACHE/dorsal-recheck-cache.json`; la lista de relecturas existente conserva su formato. El informe añade el campo opcional `ocr_cache`.
- Pruebas nuevas: `tests/identidad/test_local_dorsal.py` y comparación reproducible `tests/identidad/compare_contexts.py`. Sin dependencias de proyecto nuevas ni cambios en etapas, umbrales, contratos de identidad o balón.

Revisión de las etapas: OCR completo ya verificaba vídeo/scan; reparación ya eliminaba recortes de un dígito y separaba dorsales incompatibles; referencias ya usaban contextos respaldados y validación agrupada; identidad lejana ya tenía validación anidada y abstención por clase; continuidad ya aplicaba exclusividad y respetaba revisiones. No se repiten esas mejoras. Las dos pasadas registradas de dorsal guard guardaban relecturas, pero no las reutilizaban. Las características y referencias existentes no se recalculan en esta intervención.

### Medición limitada a regresiones sintéticas

Antes de editar lógica se guardaron fuentes y salidas en `tests/identidad/.venv/evidence/` (ignorado, local): `trajectory_identity.py`, `dorsal_guard.py`, `before.json`; después, `after.json`, `reproduced-before.json` y `tests-after.txt`.
Siete secuencias completas independientes, 16 observaciones: dorsal legible seguido de vista lejana, cruce, salida/reentrada, contradicciones 22/41 en ambos sentidos y 16/11, apariencia débil seguida de dorsal. No hay ajuste ni entrenamiento; todos los ejemplos son regresiones, sin estimación de generalización. Tests aparte conservan abstenciones para 9/5 y 41/14, y protección ante 99→9 y 16→6.

| Medida | Fase 0 | Cambio |
|---|---:|---:|
| Atribuciones correctas / incorrectas | 10 / 3 | 13 / 0 |
| Sin identidad (abstenciones) | 3 | 3 |
| Acierto entre asignadas | 76,92 % | 100 % |
| Cobertura asignada | 81,25 % | 81,25 % |
| Cambios injustificados / duplicados simultáneos | 0 / 0 | 0 / 0 |
| Mediana por secuencia, ms, reproducción caliente | 0,085 | 0,088 |

Tiempo: 30 repeticiones por secuencia después de una de calentamiento; excluye imports y copias. La primera captura previa dio 0,124 ms. Estos tiempos pequeños y variables **no prueban aceleración**. Huella idéntica de entradas: `fc45d5bd61c5e061fd4283b61991dc0bdb5cff087c14c93763e48f3839f3227e`.
En la regresión de repetición de etapa, con lector simulado, las relecturas nuevas pasan de 4 a 0, sin volver a construir el lector/decodificador y con salidas idénticas. No se ha medido ahorro de tiempo OCR real ni el coste de verificar hashes sobre modelos reales.

### Reproducción y pruebas

Desde `outputs/visor-futbol8`, con Python 3.12 y las dependencias de tests del repositorio:

```powershell
python -B -m tests.identidad.compare_contexts --baseline-ref b3711e2
python -B -m tests.identidad.compare_contexts
python -B -m unittest tests.identidad.test_local_dorsal -v
python -B -m unittest discover -s tests -t .
```

La comparación previa ejecuta la función de estabilización del commit base sin modificar el checkout; las funciones dependientes de decisión no han cambiado. En esta máquina no existe `work/vision-env`; se usó el Python 3.12.14 incluido en Codex:

```powershell
$env:PYTHONPATH = (Join-Path $PWD 'tests/identidad/.venv/deps')
& 'C:\Users\marti\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -B -m unittest discover -s tests -t .
```

Dependencias locales de prueba: numpy 2.5.4, OpenCV 5.0.0.93, scipy 1.18.1, scikit-learn 1.9.1, matplotlib 3.11.2, Pillow 13.0.0; no se altera ningún requirements. Base: **208 tests OK, 11,641 s**. Final: **217 tests OK, 11,096 s**. La salida «No se pudo leer el vídeo» pertenece a la prueba de vídeo ausente y no implica fallo de suite. `git diff --check` sin errores.

### Validación real pendiente

Esta copia no contiene vídeos, scan/OCR de partidos, revisiones ni modelos; `S:\visor-futbol8` tampoco está disponible. No se puede determinar el fallo más frecuente real, comprobar si jugaron los cinco jugadores citados en PLAN.md, ni afirmar mejora de precisión deportiva o tiempo total. El criterio de aceptación en vídeo sigue pendiente.

Cuando se restauren datos, conservar ROOT y CACHE originales y trabajar con copias aisladas, mismo vídeo y scan fijo. Reservar secuencias completas para comprobar, separadas de referencias y ajuste; no usar fotogramas vecinos como evaluación. Congelar records/OCR/features/revisiones y sus hashes antes de ejecutar ambas versiones. Seleccionar fragmentos anotados con dorsal legible, jugador lejano/sin dorsal, cruces, salida/reentrada y confusión documentada. Comparar correctas, incorrectas, abstenciones, cambios injustificados y tiempo contra esas anotaciones.
Para iterar este cambio basta ejecutar `python -B -m f8.identidad.trajectory_identity --records <entrada-fija> --output <salida-aislada>` y, si hay contradicciones, `python -B -m f8.identidad.dorsal_guard --records <entrada-fija> --output <salida-aislada>`, con `FOOTBALL_VIEWER_ROOT`, `FOOTBALL_CACHE_ROOT` y `FOOTBALL_VIDEO_SOURCE` apuntando a las copias y al vídeo correcto. Repetir guard sobre la misma entrada para medir caché fría/caliente. No ampliar a partido completo hasta verificar el fragmento real corto. No se requieren peticiones ni cambios externos para esta corrección.

## 2026-10-27 · core/fase-0
- Código movido a esta carpeta sin cambios de lógica (Fase 0, ver PLAN.md §2.1).
