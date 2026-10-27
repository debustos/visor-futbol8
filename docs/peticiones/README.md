# Peticiones entre módulos

Si necesitas un cambio en una carpeta que no es tuya, **no la edites**. Crea aquí un archivo nuevo. Como cada petición es un archivo distinto, nunca generan conflictos.

Nombre: `AAAA-MM-DD-<de>-a-<para>-<tema>.md`, por ejemplo `2026-11-03-acciones-a-balon-vuelo-hacia-porteria.md`.

```markdown
# <tema>
- De: <módulo> (<persona>)
- Para: <módulo>
- Contrato afectado: <archivo o función, o "ninguno">

## Qué necesito
## Por qué
## Mientras tanto
(adaptador que uso dentro de mi carpeta)
```

El responsable del módulo destino la resuelve en su rama, cita el archivo en el PR y borra la petición en ese mismo PR.
