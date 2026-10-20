 'use strict';
function metricDisplay(m){
 if(!m)return 'Sin análisis';
 const values=[];
 if(m.confirmed_value!=null)values.push(`${m.confirmed_value} ✓`);
 if(m.value!=null)values.push(`≈ ${m.value}`);
 if(values.length)return values.join(' · ');
 if(m.detected_value!=null)return `${m.detected_value} detectados`;
 return m.analysis_state==='candidate_only'?'Pendiente de validar':'Sin observación';
}
function metricSubtext(m){
 if(m?.confirmed_value!=null||m?.value!=null)return 'Acciones disponibles; recuento parcial';
 if(m?.analysis_state==='candidate_only')return 'El motor aún no valida automáticamente esta métrica';
 return m?.detected_value!=null?'En tramos observados; faltan acciones fuera del seguimiento':'Sin evidencia atribuible suficiente';
}
function renderActionDiagnostics(id,checks){
 const host=$(id);if(!host)return;
 host.innerHTML=(checks||[]).map(q=>{
  const g=q.goal_check;
  return `<div class="action-diagnostic ${g?.state==='count_mismatch'?'failed':''}"><h3>${q.round?`Jornada ${q.round} · parte ${q.half} · `:''}Comprobación de acciones</h3>${g?`<p><strong>${g.state==='count_mismatch'?'El análisis no coincide con el resultado conocido':'El recuento coincide; falta comprobar la jugada'}</strong><br>Goles del equipo indicados por ti: <b>${g.declared}</b> · detectados automáticamente: <b>${g.automatically_detected}</b> · jugadas de gol revisadas: <b>${g.reviewed_events}</b>.</p>${(g.observations||[]).map(v=>`<button class="button secondary compact" data-known-goal="${v.time}" data-round="${q.round||''}" data-half="${q.half||''}">Ver gol indicado: #${escape(String(v.player_id||'').split('-').pop())} · ${clock(v.time)}</button>`).join('')}<p class="small">Tu referencia se usa para comprobar el motor. El gol comunicado se conserva como referencia de comprobación; no suma como detección automática.</p>`:''}<p>Balón localizado en ${q.ball_sample_coverage_percent==null?'muestras sin evaluar':`${q.ball_sample_coverage_percent}% de las muestras`} · tiros aceptados: ${q.automatic_shots} · propuestas de tiro pendientes: ${q.shot_candidates}.</p><p class="small">Pases y robos tienen detección parcial. Goles, tiros y las demás métricas aún requieren validar la acción. Procesar todo el vídeo no garantiza haber detectado todas las jugadas.</p></div>`;
 }).join('');
 host.querySelectorAll('[data-known-goal]').forEach(button=>button.onclick=async()=>{if(button.dataset.round)await switchMatchHalf(Number(button.dataset.round),Number(button.dataset.half));showTab('review');seek(Math.max(0,Number(button.dataset.knownGoal)-5));});
 host.hidden=!checks?.length;
}
