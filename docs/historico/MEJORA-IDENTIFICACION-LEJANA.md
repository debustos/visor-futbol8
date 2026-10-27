# Identificación lejana — motor 9

Aplicada a la jornada 2, primera parte. También forma parte del proceso automático de análisis de las próximas partes y jornadas.

Se ha añadido un especialista que reduce el peso de la representación global de la camiseta y compara regiones del pelo, medias y botas. La selección y el entrenamiento se realizan dentro de grupos de trayectoria. Las etiquetas proceden de dorsales o referencias respaldadas: las propuestas del propio modelo no entrenan su identidad.

## Prueba interna

| Conjunto | Imágenes | Contextos reservados | Motor anterior | Especialista |
|---|---:|---:|---:|---:|
| Jugadores lejanos, menos de 80 píxeles de altura | 200 | 35 | 61,5 % | 68,0 % |
| Busi lejano | 29 | 2 | 27,6 % | 86,2 % |

Los porcentajes miden coincidencia de predicciones visuales con etiquetas derivadas de dorsales. Se emplean tres particiones externas por trayectoria; la elección del modelo se hace con particiones internas que no utilizan las etiquetas externas. No es una medición independiente de la exactitud deportiva en todo el partido. Hay pocas tomas lejanas de algunos jugadores, especialmente solo dos contextos de Busi. Se necesita probar en otros partidos para medir la generalización.

En imágenes grandes y en el conjunto completo, el especialista aislado rinde peor que el motor general. Por eso se conserva el motor general y se utiliza este módulo únicamente para proponer identidades de jugadores pequeños que siguen sin identificar. Las identidades ya aceptadas se conservan.

## Decisión temporal

Una propuesta exige una ventana de hasta ocho segundos, al menos ocho observaciones originales y seis segundos de duración; no admite huecos mayores de 2,1 segundos. Se exige acuerdo entre fotogramas, separación entre candidatos y validación por jugador. La precisión se comprueba también equilibrando el peso de cada contexto: una trayectoria larga no puede ocultar el fallo en otro jugador.

Cuando hay al menos tres imágenes con altura de 80 píxeles o más, esas tomas ayudan a respaldar una secuencia que también contiene vistas más pequeñas. Si todas las referencias son muy lejanas, hace falta superar además el umbral específico para ese caso. Busi aún no dispone de validación suficiente para asignarle una trayectoria exclusivamente lejana por apariencia; sí puede conservar su identidad a distancia cuando la secuencia contiene evidencia más clara.

## Resultado aplicado

Se recuperaron automáticamente dos trayectorias de Busi, alrededor de 10:24–10:35 y 10:46–10:55. Añaden 323 observaciones, 107 con menos de 80 píxeles de altura. La cobertura de identidad de Busi pasa de 360,4 a 380,6 segundos, y el tiempo proyectado sobre el campo de 319,9 a 333,1 segundos.

La validación no encontró cambios ni pérdidas de nombres anteriormente aceptados. Se mantuvieron los 26 pases estimados, los controles negativos de pases, las once métricas de las 16 fichas y las revisiones del usuario. Los resultados siguen siendo parciales y las nuevas identidades son estimaciones revisables.
