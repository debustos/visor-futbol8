"""HTTP routes declared by each module in f8/<module>/api.py. server.py combines them without listing them.

api.py exposes RUTAS={('GET', r'/api/...'): handler}. The handler receives
(app, match, query) for GET or (app, match, body) for POST and returns JSON data.
Built-in server.py routes are tried first; declared routes cannot replace them.
"""
import re
from f8.core.registro import declarations


def load_routes(found=None):
    found=declarations('api') if found is None else found
    routes=[];seen={}
    for owner,module in found:
        for (method,pattern),handler in getattr(module,'RUTAS',{}).items():
            key=(method.upper(),pattern)
            if key[0] not in ('GET','POST'):raise ValueError(f'{owner}: método no admitido {method}')
            if key in seen:raise ValueError(f'Ruta {key[0]} {pattern} declarada en {seen[key]} y {owner}')
            seen[key]=owner;routes.append((key[0],re.compile(pattern),handler))
    return routes


def find_route(routes,method,path):
    for m,pattern,handler in routes:
        match=pattern.fullmatch(path)
        if m==method and match:return handler,match
    return None,None
