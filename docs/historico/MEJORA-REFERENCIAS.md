# Referencias visuales ampliadas — jornada 2, primera parte

El banco contiene 687 fotos reales, frente a las 54 del visor anterior. Cada jugador con identidad respaldada dispone de hasta 64 fotos. Busi tiene 64: 16 lejanas, 30 a media distancia y 18 cercanas; 11 muestran una lectura del dorsal y 53 proceden de continuidad física con una identidad respaldada. El visor permite filtrar por distancia y por tipo y abrir la evidencia en el vídeo.

El modelo utiliza 2833 muestras reales y 154 variantes reducidas para entrenamiento. Las variantes no se presentan como fotos adicionales ni recuperan información ausente. Solo se aprende de trayectorias respaldadas por dorsales en instantes independientes, referencias visuales verificadas o el uniforme del portero. Una identidad propuesta por apariencia no se usa para entrenarse a sí misma.

Los análisis siguientes extraerán apariencia cada 0,45 s y conservarán hasta 24 recortes de dorsal por trayectoria, repartidos entre distancias y separados en el tiempo. La ampliación de referencias se ejecuta automáticamente antes de generar las estadísticas finales.

## Resultado y límites

Se recuperaron 31 trayectorias previamente sin identificar, con 3610 observaciones aceptadas, después del control de exclusividad. Se conservan los nombres durante cada trayectoria y las revisiones del usuario.

En 2677 muestras de 134 contextos reservados para prueba, la coincidencia con etiquetas derivadas de dorsales pasó del 82,89 % al 85,88 %. Es una prueba interna con etiquetas indirectas, no una medición independiente de la exactitud en todo el partido. En las 200 muestras lejanas pasó del 63,5 % al 61,5 %: ampliar fotos por sí solo no resolvió el problema a distancia. Por ello se exige validación específica por jugador para asignar nuevas identidades lejanas. Busi y Adri no superaron el criterio para asignar nuevos nombres basándose únicamente en este modelo de apariencia; sus identidades respaldadas por dorsal y continuidad se conservan.

No hay referencias fiables para Lain, Mayora, Fernandito, Alfaro y Resu en esta prueba; no se atribuyen imágenes de otros jugadores a sus fichas. La segunda parte sigue pendiente de terminar su análisis.

Se verificaron los 21023 registros de la primera parte, la exclusividad de identidades, las once métricas, los mapas, los 26 pases estimados y dos controles de vídeo que no deben producir pases. Las fotos se mantienen aisladas por archivo de origen.
