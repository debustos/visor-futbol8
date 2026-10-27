# Código retirado

Ninguno de estos archivos se importa ni se ejecuta desde `f8/`, el pipeline ni los tests. Se conservan por si hay que consultar cómo funcionaban las versiones anteriores del motor. Sus imports son los antiguos (planos) y **no funcionan** tal cual.

| Archivo | Sustituido por |
|---|---|
| `process_half.py`, `validate_half.py` | `f8/deteccion/analyze_automatic.py`, `f8/publicacion/validate_v5.py` |
| `commit_v3.py`, `validate_v3.py` | `f8/publicacion/commit_v5.py`, `f8/publicacion/validate_v5.py` |
| `train_appearance.py` | `f8/identidad/reference_bank.py`, `f8/identidad/far_identity.py` |

No añadas código nuevo aquí. Si nadie los necesita al cerrar la Fase 1, se borran.
