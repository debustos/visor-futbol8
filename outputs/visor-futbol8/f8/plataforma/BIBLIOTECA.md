# Biblioteca de vídeos y ejemplos

En **Jornadas → Biblioteca de vídeos → Configurar carpeta una vez**, acepta la
ruta propuesta o indica una carpeta local, de disco externo o sincronizada con
Drive. Usa originales completamente descargados. Guardar prepara esta estructura:

```text
Futbol8Datos/
  originales/
    temporada-2026/
      jornada-002/
        primera.mp4
        segunda.mp4
      jornada-003/
        primera.mp4
  ejemplos/
    catalogo.json
  resultados/
```

Se admiten MP4, MOV, MKV y AVI; también nombres `PRIMERA PARTE` / `SEGUNDA PARTE`
y `parte-1` / `parte-2`. Una sola temporada se corresponde con el registro actual.
Cambiar la temporada o la carpeta no crea otra base de temporada ni sustituye
partes existentes. `resultados/` queda preparada para exportaciones manuales;
los análisis y cachés siguen en las ubicaciones actuales del programa.

## Incorporación

Al abrir el visor se comprueba la carpeta configurada en segundo plano. El botón
**Comprobar vídeos nuevos** repite la comprobación. Se muestran los archivos
registrados, duplicados, incompletos, ilegibles, ambiguos o pendientes de nombre.
Los archivos recientes o temporales se vuelven a comprobar mientras la página
está abierta. Una copia muy reciente se deja esperar al menos diez segundos.

Se calcula SHA-256, se leen los metadatos y se decodifican muestras del inicio,
centro y final. Si tamaño o fecha cambian durante la comprobación, no se registra.
Estas comprobaciones detectan problemas comunes; no garantizan que todos los
fotogramas de una descarga sean íntegros. Para verificar una transferencia entre
equipos, compara también su SHA-256 con el original del emisor.

Un archivo sin cambios reutiliza su comprobación por ruta, tamaño y fecha; no
vuelve a leer todos sus bytes en cada visita. También se verifican los hashes de
los modelos de `modelos.json` en `work/`, reutilizando comprobaciones sin cambios.
Ese inventario no contiene todos los recursos OCR y temporales del motor.

Un archivo válido se registra usando el mecanismo habitual, sin ejecutar modelos.
Pulsa **Analizar** cuando quieras procesar la parte. Los originales mantienen su
ubicación; una parte ocupada nunca se reemplaza y sus revisiones se conservan.
Si una misma parte contiene varios vídeos, resuelve la ambigüedad en la carpeta.

La configuración y las comprobaciones están en `data/video-library.json` de esta
copia del visor, fuera de Git. Mantén una ubicación estable de los originales:
las cachés de identidad también comprueban su ruta y fecha. Cada equipo genera o
revalida sus propias cachés. No compartas bases SQLite activas como si fueran
archivos de intercambio.

## Ejemplos compartidos

En **Ejemplos compartidos para comprobar mejoras**, selecciona una parte
registrada, escribe nombre, inicio y fin en segundos, categoría y grupo
(`desarrollo` o `reserva`). **Ver fragmento** abre ese intervalo y se detiene al
llegar al final. Usa la reproducción compatible cuando existe; los motores siguen
leyendo el original. Puedes quitar ejemplos y volver a guardarlos corregidos.

`ejemplos/catalogo.json` guarda intervalos y huellas SHA-256, sin rutas del equipo
ni copias de vídeo. **Exportar catálogo** descarga el catálogo; el compañero puede
importarlo y registrar sus originales. Los ejemplos quedan disponibles cuando
coinciden temporada, jornada, parte y huella. Importar incorpora IDs nuevos,
conserva los idénticos y rechaza conflictos de contenido. Una importación no
modifica las estadísticas ni confirma acciones deportivas.

No se permite solapamiento entre desarrollo y reserva en un mismo original.
Además, asignad una jugada completa a un solo grupo, aunque sus fragmentos no se
solapen: el programa no sabe si dos intervalos vecinos pertenecen a la misma
secuencia. Las anotaciones deportivas verificadas y los benchmarks siguen siendo
un paso distinto; guardar un ejemplo no ejecuta una evaluación de precisión.

Un solo responsable debe editar el catálogo compartido a la vez. Para intercambiar
cambios entre equipos, usad exportación/importación y evitad ediciones concurrentes
del archivo sincronizado. Los vídeos y datos permanecen fuera de GitHub.

## API

Rutas adicionales declaradas en `f8/plataforma/api.py`:

- `GET /api/season/library`: configuración, comprobación y ejemplos disponibles.
- `POST /api/season/library/config`: `directory` absoluta y `season`.
- `POST /api/season/library/scan`: inicia comprobación; el cliente consulta el GET.
- `GET /api/season/library/catalogue`: catálogo portable versión 1.
- `POST /api/season/library/examples`: nuevo intervalo, `{catalogue: ...}` para
  importar, o `{remove: "id"}` para quitar.

Los POST requieren el token del registro de temporada, incluso si el visor tiene
otra parte seleccionada. No se añade ningún descargador de enlaces de Drive.
