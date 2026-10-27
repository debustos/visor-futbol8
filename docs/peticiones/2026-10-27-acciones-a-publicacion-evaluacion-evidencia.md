# Acciones → publicación, evaluación, campo y balón: evidencia independiente

Rama solicitante: `mod/acciones/goles-faltas`. Petición según PLAN.md §5.4;
no se modifica código de otros módulos ni se cambia un contrato compartido.

## Contratos y entradas para evaluación

Se mantienen `temporal-candidates.json`, `visual-shot-candidates.json` y la forma
existente de `actions.json`. Se añaden solo campos opcionales:

- Candidato temporal: `timestamp`, `frame`, `timestamp_basis` (PTS del MOV).
- Acción: `proposal_evidence` (todas las propuestas agrupadas),
  `complementary_evidence`, `event_validation`, `outcome_validation`, `goal_end`.
- Falta pendiente: `foul_role=null`, `committed_by=null`, `received_by=null`,
  `decision_state=pending`. El `kind=foul_committed` existente es el contenedor
  de compatibilidad para una falta sin rol resuelto, nunca atribución al equipo
  ni al jugador: ambos quedan desconocidos. Se solicita a core un contrato
  propio para una falta neutra y la adaptación coordinada de los lectores.
- Calidad de secuencia: `rejected_proposals` conserva propuestas con tiempos
  inválidos y el motivo. No deben entrar en recuentos deportivos.

`python -m f8.acciones.review_candidates --temporal <archivo> --source <MOV>
--duration <duración> --output <carpeta-aislada> [--records <records-v5.json>]`
exporta `actions.json`, `sequence-quality.json` y `review-intervals.json` para
el evaluador, sin escribir publicación ni inventar registros ausentes. Comprueba
la huella del MOV. Los resultados sin registros dejan equipo y autor pendientes.
La comparación debe medir eventos, equipo y autor por separado; las faltas se
comparan como infracción propuesta independientemente del rol sin resolver.
El evaluador no se implementa ni se ajusta en esta rama; las anteriores selecciones
visuales de jornada 4 no se usan como anotaciones fiables.

## Cambios solicitados a sus responsables

1. **Publicación**: validar `temporal-metadata.json` (huella de origen, estado y
   cobertura completa), igual que ya se comprueba la calidad visual; avisar si
   el análisis temporal es parcial o pertenece a otro vídeo. Conservar goles
   rivales y sin autor en acciones/revisión y mantenerlos fuera de fichas naranja.
   Mostrar las propuestas rechazadas por tiempo en revisión técnica.
   **Plataforma (bloqueo de integración)**: `analysis_worker.py` importa
   `pipeline_steps` pero sigue ejecutando su `STEPS` local con nombres planos
   (`prepare_video.py`, `temporal_actions.py`, `commit_v5.py`...), resueltos
   respecto a `f8/plataforma/`, donde ya no están. Sustituir esa lista por el
   registro modular y probar un job real. Esta rama ejecuta módulos directamente
   en un destino aislado; no se afirma que el botón Analizar publique estos
   resultados. No se modifica plataforma desde acciones.
2. **Core + publicación + revisión + evaluación**: acordar en PR de contrato
   el tipo neutro de falta. No convertir `foul_role=null` en falta cometida por
   el equipo naranja ni exigir nombre para revisar una infracción.
3. **Balón/campo/plataforma**: exponer PTS y huella del origen en registros,
   geometría y conversiones. Los registros actuales fechados con frame/FPS no
   permiten probar sincronía VFR general. Se necesitan marcas medidas, nunca
   interpolación del balón. Acciones usa ya PTS al decodificar originales.
   Exponer además una orientación de análisis explícita por vídeo: en el MOV
   de segunda parte de jornada 4, la matriz declarada de 90° deja el campo
   lateral al obedecerla. `temporal_actions --orientation encoded` permite
   analizar los píxeles originales derechos sin regla específica del partido.
   El valor por defecto sigue siendo `display`; la plataforma debe propagar
   una elección consistente a detección, geometría, balón y publicación.
   El exportador aislado impide mezclar registros de otra orientación.
4. **Campo**: proporcionar porterías verificadas cuando falta homografía. El
   buscador actual necesita calibración; abrir una ventana temporal sin balón
   no crea por sí mismo trayectoria, portería o gol.
5. **Evaluación**: entregar anotaciones independientes por secuencia completa,
   partición de aceptación y versión del evaluador; informar TP/FP/FN de goles
   de ambos equipos y faltas, y atribución por separado. Esta rama no puede
   certificar cero omisiones/invenciones con el módulo de evaluación aún vacío.

Ni saque de centro, ni etiqueta temporal, ni acercamiento a postes certifican un
gol por sí solos. Los tiros, goles y faltas de esta rama siguen como candidatos.
