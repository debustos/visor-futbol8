# Diagnóstico y correcciones de acciones — jornada 2, primera parte

El motor actual no ofrece estadísticas completas fiables. La referencia proporcionada por el usuario es un gol de Busi (#41) en el minuto 15:44. El motor no lo detectó y el modelo temporal ni siquiera propuso un gol en ese momento. En este ejemplo conocido, la detección de goles es 0 de 1; no se ha medido todavía la exactitud de todos los pases o tiros del partido.

## Causas comprobadas

- Los tiros y goles solo eran propuestas del modelo temporal. El cálculo mostraba cero para cualquier jugador observado aunque la métrica no tuviera un detector automático validado.
- El balón está localizado en 10.222 de 21.023 muestras (48,6 %). Más imágenes de apariencia no resuelven los contactos y vuelos perdidos del balón.
- En la jugada del gol, una trayectoria que heredaba la identidad de Busi contenía a Alpha, cuyo dorsal 22 se lee claramente. Una etiqueta estable puede seguir siendo incorrecta.
- La asociación de tiros tomaba el último contacto próximo a la propuesta temporal. Una recepción del portero podía interpretarse como autoría de tiro.
- Dos etiquetas temporales coincidentes del mismo tiro podían conservar la menos probable.
- La búsqueda inicial del balón estaba condicionada a disponer de una proyección del campo, aunque se puede detectar en la imagen sin ella.

## Cambios aplicados

Se añade una comprobación automática de dorsales que contradicen una identidad heredada. Detectó tres contextos problemáticos en la primera parte. La nueva lectura local confirma dos fotogramas independientes del 22 y corrige 260 observaciones entre 15:28,54 y 15:45,71. Dos contextos con evidencia incompatible o insuficiente quedan sin nombre, en lugar de asignar otro por intuición. Se retiran tres fotos contaminadas de las galerías. Las correcciones manuales del usuario se conservan.

Las propuestas de tiro requieren ahora un contacto seguido de salida medida del balón para proponer autor. No se convierte una recepción o parada en un tiro del portero. Se conserva la clasificación temporal más fuerte y todas las alternativas como evidencia.

El detector busca el balón aunque no haya proyección del campo. Esta mejora ya forma parte de los siguientes análisis. La prueba adicional de 14 fotogramas del gol sin proyección confirmó que el modelo pierde el balón al llegar a la portería: eliminar esa dependencia no recupera por sí solo el gol.

El visor muestra la discrepancia «1 gol indicado / 0 detectados» y permite abrir el clip. La referencia no se presenta como detección automática ni inventa una asistencia. Las métricas sin detector validado aparecen pendientes de validar, no como cero deportivo. La comprobación aparece también por jornada y en el total.

Se conservan 26 pases aceptados parcialmente; con las revisiones actuales, 17 tienen emisor identificado y 9 quedan sin emisor. No hay prueba de que sean todos los pases del partido. No se promovieron candidatos para aumentar el recuento.

## Qué necesita el siguiente desarrollo

1. Preparar un conjunto de jugadas verificadas: el gol del 15:44, pases completados, controles, despejes, paradas y ejemplos sin acción. Reservar secuencias completas para evaluación; fotogramas vecinos de una misma jugada no deben repartirse entre entrenamiento y prueba.
2. Entrenar y evaluar el detector del balón con las tomas reales: balón pequeño, desenfoque, oclusiones, vuelo y fondo de portería. Incorporar seguimiento por medidas de imagen con detección de cámara; no rellenar huecos por interpolación y contarlos como prueba.
3. Detectar contacto, golpeo, vuelo y recepción; distinguir pase, despeje y tiro hacia la portería de fútbol 8. La intención no se deduce de cambiar de propietario.
4. Detectar ambas porterías y su línea en cada encuadre, incluyendo el movimiento de cámara. Un balón acercándose a la portería no demuestra por sí solo que haya cruzado la línea.
5. Medir precisión y recuperación de acciones y atribución a jugador por separado. La primera condición de aceptación será recuperar este gol de Busi mediante evidencia del vídeo; introducirlo como regla o dato comunicado no sería una mejora automática.

He podido programar los cambios, reprocesar datos, leer dorsales y revisar este ejemplo. Para obtener estadísticas completas hace falta continuar con datos de evaluación y entrenamiento; la ayuda útil sería confirmar ejemplos ambiguos o aportar vídeo donde balón y dorsales sean más visibles. No necesitas registrar manualmente todas las acciones para usar el visor, pero todavía no puede prometerse detección automática fiable de todas las estadísticas.
