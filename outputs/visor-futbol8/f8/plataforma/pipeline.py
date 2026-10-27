"""Analysis stages declared by each module in f8/<module>/etapas.py, run in global `orden` order.

Each entry is (orden, clave, etiqueta, módulo ejecutable, argumentos, peso de progreso).
`orden` is the position in the whole pipeline, not a per-module range: stages of
different modules interleave because each one consumes the files of the previous.
"""
from f8.core.registro import declarations


def validate(steps):
    """steps: (owner, entry) pairs. Duplicate positions or keys would make the order ambiguous."""
    orders={};keys={}
    for owner,entry in steps:
        if len(entry)!=6:raise ValueError(f'{owner}: cada etapa tiene 6 campos')
        order,key,label,module,args,weight=entry
        if not isinstance(order,int) or isinstance(order,bool):raise ValueError(f'{owner}/{key}: orden debe ser entero')
        if not module.startswith('f8.') or not isinstance(args,list) or not weight>0:raise ValueError(f'{owner}/{key}: etapa inválida')
        if order in orders:raise ValueError(f'Orden {order} repetido en {orders[order]} y {owner}')
        if key in keys:raise ValueError(f'Clave {key} repetida en {keys[key]} y {owner}')
        orders[order]=owner;keys[key]=owner
    return sorted((entry for _,entry in steps),key=lambda e:e[0])


def pipeline_steps(found=None):
    found=declarations('etapas') if found is None else found
    return validate([(owner,tuple(entry)) for owner,module in found for entry in module.ETAPAS])
