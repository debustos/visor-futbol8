"""Etapas del análisis que ejecuta este módulo. Ver PLAN.md §5.1.

`orden` es la posición global en todo el pipeline (10 en 10). Para añadir una etapa,
usa un número libre entre sus vecinas; no renumeres etapas existentes.
"""
# (orden, clave, etiqueta, módulo ejecutable, argumentos, peso de progreso)
ETAPAS = [
    (130, 'context', 'Fijando identidades por trayectoria', 'f8.publicacion.commit_v5', [], 1),
    (200, 'commit', 'Generando estadísticas', 'f8.publicacion.commit_v5', [], 1),
    (210, 'gallery', 'Preparando fichas', 'f8.publicacion.make_gallery', [], 1),
    (220, 'maps', 'Dibujando mapas de calor', 'f8.publicacion.export_heatmaps', [], 1),
    (230, 'validation', 'Comprobando los resultados', 'f8.publicacion.validate_v5', [], 1),
]
