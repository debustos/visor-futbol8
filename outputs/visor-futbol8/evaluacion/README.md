# Evaluación

Módulo nuevo, vacío al cerrar la Fase 0. Su objetivo es medir **si el análisis acierta en el vídeo**, que los tests de software no comprueban. Las tareas están en [PLAN.md §7.10](../../../PLAN.md).

- `anotaciones/jNNN-pM.json`: jugadas verificadas a mano, incluidos ejemplos **sin** acción.
- `python -m evaluacion.medir --round N --half M`: compara `actions.json` y `profiles.json` con las anotaciones y da precisión y recall por acción y acierto de atribución por jugador, por separado.
- `linea-base.json`: el resultado de referencia que cada PR de visión debe comparar.

Este módulo solo lee contratos ([f8/core/contratos](../f8/core/contratos/README.md)); nunca los escribe.
