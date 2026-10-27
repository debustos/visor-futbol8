"""Etapas del análisis que ejecuta este módulo. Ver PLAN.md §5.1.

`orden` es la posición global en todo el pipeline (10 en 10). Para añadir una etapa,
usa un número libre entre sus vecinas; no renumeres etapas existentes.
"""
# (orden, clave, etiqueta, módulo ejecutable, argumentos, peso de progreso)
ETAPAS = [
    (240, 'playback', 'Preparando el vídeo del visor', 'f8.plataforma.make_playback', [], 3),
]
