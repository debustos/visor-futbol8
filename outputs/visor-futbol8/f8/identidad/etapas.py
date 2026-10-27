"""Etapas del análisis que ejecuta este módulo. Ver PLAN.md §5.1.

`orden` es la posición global en todo el pipeline (10 en 10). Para añadir una etapa,
usa un número libre entre sus vecinas; no renumeres etapas existentes.
"""
# (orden, clave, etiqueta, módulo ejecutable, argumentos, peso de progreso)
ETAPAS = [
    (70, 'appearance', 'Aprendiendo la apariencia', 'f8.identidad.extract_appearance_parts', [], 4),
    (80, 'memory', 'Construyendo memoria visual', 'f8.identidad.upgrade_v3', [], 1),
    (110, 'jersey_text', 'Comprobando dorsales completos', 'f8.identidad.read_jersey_text', [], 8),
    (120, 'identities', 'Reconstruyendo identidades', 'f8.identidad.repair_identity_v5', [], 2),
    (140, 'dorsal_guard_seed', 'Validando dorsales antes de aprender apariencia', 'f8.identidad.dorsal_guard', [], 2),
    (150, 'references', 'Ampliando referencias a distintas distancias', 'f8.identidad.reference_bank', [], 5),
    (160, 'far_identity', 'Reconociendo jugadores lejanos con contexto', 'f8.identidad.far_identity', [], 3),
    (180, 'dorsal_guard_final', 'Comprobando identidades después del seguimiento', 'f8.identidad.dorsal_guard', [], 2),
]
