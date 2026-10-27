"""Etapas del análisis que ejecuta este módulo. Ver PLAN.md §5.1.

`orden` es la posición global en todo el pipeline (10 en 10). Para añadir una etapa,
usa un número libre entre sus vecinas; no renumeres etapas existentes.
"""
# (orden, clave, etiqueta, módulo ejecutable, argumentos, peso de progreso)
ETAPAS = [
    (50, 'ball', 'Siguiendo el balón', 'f8.balon.refine_ball', [], 12),
    (90, 'dense_ball', 'Revisando contactos y pases', 'f8.balon.adaptive_ball', [], 19),
    (100, 'ball_continuity', 'Comprobando la trayectoria del balón', 'f8.balon.ball_continuity', [], 2),
    (170, 'native_ball', 'Revisando vuelos del balón a velocidad original', 'f8.balon.native_ball', ['--no-pose'], 24),
]
