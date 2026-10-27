"""Etapas del análisis que ejecuta este módulo. Ver PLAN.md §5.1.

`orden` es la posición global en todo el pipeline (10 en 10). Para añadir una etapa,
usa un número libre entre sus vecinas; no renumeres etapas existentes.
"""
# (orden, clave, etiqueta, módulo ejecutable, argumentos, peso de progreso)
ETAPAS = [
    (30, 'temporal', 'Buscando jugadas', 'f8.acciones.temporal_actions', [], 8),
    (190, 'visual_shots', 'Buscando vuelos hacia las porterías', 'f8.acciones.visual_shots', [], 3),
]
