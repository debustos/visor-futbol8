"""Etapas del análisis que ejecuta este módulo. Ver PLAN.md §5.1.

`orden` es la posición global en todo el pipeline (10 en 10). Para añadir una etapa,
usa un número libre entre sus vecinas; no renumeres etapas existentes.
"""
# (orden, clave, etiqueta, módulo ejecutable, argumentos, peso de progreso)
ETAPAS = [
    (20, 'detection', 'Detectando jugadores', 'f8.deteccion.analyze_automatic', ['--scan-only'], 25),
    (40, 'jersey', 'Leyendo dorsales', 'f8.deteccion.analyze_automatic', ['--resume'], 10),
    (60, 'fusion', 'Relacionando jugadores y acciones', 'f8.deteccion.analyze_automatic', ['--resume', '--reuse-ocr'], 1),
]
