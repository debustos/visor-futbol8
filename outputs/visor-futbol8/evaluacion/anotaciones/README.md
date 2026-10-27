# Referencia independiente

El objetivo actual es J2, por indicación del usuario. Las referencias iniciales j002-p1.json y j002-p2.json están en `S:/visor-futbol8/work/evaluacion-j2/preparacion-inicial-20261027/`: huellas de originales reales y metadatos comprobados, sin anotaciones deportivas ni cobertura. No son una referencia verificada de eventos. El objetivo anterior J4 queda pendiente y sus identidades no se reutilizan. `../ejemplo-sintetico.json` sirve exclusivamente para comprobar el software.

Cada documento tiene schema_version=1, round, half, sha256 del original completo, duration en segundos, coverage con listas development/holdout, events y synthetic=false. Mantener también video_timing (frame_count, average_fps, time_base, is_variable_rate y procedimiento de comprobación), review_provenance (observador, fecha, método y recorrido continuo) y negative_examples. Son metadatos locales de auditoría, no contratos de los detectores. No incluir datos de reserva en la rama donde se ajusten umbrales.

Cada evento registra id único, sequence_id estable para la jugada y sus repeticiones, kind, time, interval=[inicio,fin], team, player_id, jersey_number, status, split, evidence y provenance={observer,method,date}. Se exige procedencia y sequence_id para verified no sintético. Evidencia explica qué se observa y cómo se decide, no solo una etiqueta. Añadir frame_index y pts_seconds si se ha verificado la correspondencia. Equipo/autor desconocidos son null: no completar por descarte. Una observación comprobada por el evaluador puede ser verified con su procedencia; no atribuirla al usuario. Una confirmación humana se documenta aparte con autor/fecha/decisión explícitos.

Estados: verified (comprobado), pending (propuesta provisional), ambiguous (no resoluble con la evidencia disponible), rejected (propuesta descartada). Un intervalo no revisado se expresa por ausencia de coverage, nunca como negativo. `shot_no_goal` permite registrar tiros comprobados sin gol; `other` permite describir contactos o caídas sin falta. Una falta verified requiere evidencia de que fue señalada, no solo contacto. Si existe duda específica de falta, registrar foul+ambiguous. `negative_examples` puede contener id, interval, split, sequence_id, evidence y provenance de un tramo revisado sin gol ni falta: la autoridad para contar falsos positivos sigue siendo coverage.

En faltas, actor_role indica a quién corresponden team/player_id: offender (infractor, valor por defecto) o beneficiary (quien la recibe). El adaptador conserva el papel de foul_committed/foul_won. Un acierto temporal sigue contando aunque el papel no coincida, pero la atribución se considera desconocida para ese papel; no se compara al receptor como infractor. No se deduce el equipo contrario a partir del equipo del receptor. En goles, player_id corresponde al goleador.

Recorrer ambas partes originales completas de principio a fin a velocidad que permita comprobar las acciones; registrar bloques contiguos solo al terminarlos. Los candidatos se consultan después para contrastar la referencia, no para seleccionar qué revisar. Anotar todos los goles de ambos equipos, tiros sin gol y confusores. Un gol se registra una sola vez; su celebración y repetición amplían interval o se describen como other con el mismo sequence_id. Mantener toda esa secuencia en un grupo y evitar cortes en mitad de la jugada. Reservar preferiblemente la segunda parte completa; congelar versión/configuración antes de abrirla.

Para MOV, comprobar el original con ffprobe si está disponible:

```powershell
ffprobe -v error -select_streams v:0 -show_entries stream=duration,start_time,r_frame_rate,avg_frame_rate,nb_frames,time_base -show_entries format=duration,start_time -of json 'RUTA/ORIGINAL.MOV'
ffprobe -v error -select_streams v:0 -show_frames -show_entries frame=best_effort_timestamp_time -of csv=p=0 'RUTA/ORIGINAL.MOV' > 'SALIDA-AISLADA/pts.csv'
Get-FileHash -Algorithm SHA256 'RUTA/ORIGINAL.MOV'
```

Verificar principio, final y varios puntos intermedios comparando el fotograma del original con la reproducción. Con tasa variable no usar frame/fps medio: asociar frame_index al PTS real normalizado al origen temporal del reproductor. Documentar start_time y cualquier offset demostrado; no aplicarlo por suposición. No usar tiempos de clips antiguos, transcodificaciones ni selecciones anteriores como referencia. No se han ejecutado estas comprobaciones sobre J4 porque faltan sus rutas.

La validación del JSON comprueba coherencia estructural, no que una persona haya visto el vídeo ni que su descripción sea cierta. Sin recorrido continuo documentado, no declarar exhaustividad aunque la CLI produzca métricas parciales.
