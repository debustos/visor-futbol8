"use strict";
let learningVersion=null,learningPolling=false;
async function refreshLearning(){
 const host=document.getElementById('learning-status');if(!host||typeof state==='undefined'||!state.boot||learningPolling)return;
 learningPolling=true;
 try{
  const q=await api('/api/review/learning');const active=['queued','starting','running'].includes(q.state);const progress=Math.max(0,Math.min(100,Number(q.progress)||0));let description;
  if(q.state==='queued')description='Correcciones guardadas. El entrenamiento comenzará cuando lleves 15 segundos sin guardar otra corrección.';
  else if(active)description=q.stage||'Entrenando con tus correcciones…';
  else if(q.state==='failed')description='La corrección está guardada, pero el entrenamiento se ha interrumpido. '+(q.error||'');
  else if(q.state==='complete'){
   const r=q.result||{};description=`Versión ${q.generation} · ${r.manual_visual_samples||0} muestras visuales revisadas · ${r.identity_model_active?'modelo de apariencia validado':'modelo de apariencia pendiente de validación'}. `;
   description+=r.active_action_models?`${r.active_action_models} tipos de jugada con aprendizaje validado.`:'Las jugadas necesitan más ejemplos aceptados y rechazados para aprender con fiabilidad.';
   if(r.identity_validation?.reason&&!r.identity_model_active)description+=' '+r.identity_validation.reason;
  }else description='Cada confirmación, corrección, rechazo o deshacer actualiza el aprendizaje automáticamente.';
  host.replaceChildren();const title=document.createElement('strong');title.textContent='Aprendizaje automático'+(active?` · ${Math.round(progress)}%`:'');const text=document.createElement('p');text.textContent=description;host.append(title,text);
  if(active){const bar=document.createElement('progress');bar.max=100;bar.value=progress;bar.setAttribute('aria-label','Progreso del reentrenamiento');host.append(bar);}
  const detail=document.createElement('small');detail.textContent='Agrupa cambios seguidos, valida con otras trayectorias y conserva tus correcciones. Alineaciones, cambios y plano se guardan con su categoría.';host.append(detail);
  const version=String(q.generation)+':'+q.state;
  if(learningVersion!==null&&version!==learningVersion){await loadAutomatic();if(typeof reloadSeason==='function')await reloadSeason();}
  learningVersion=version;
 }catch(e){host.textContent='No se puede consultar el aprendizaje automático en este momento.';}
 finally{learningPolling=false;}
}
setInterval(refreshLearning,3000);
const learningInit=setInterval(()=>{if(typeof state!=='undefined'&&state.boot){clearInterval(learningInit);refreshLearning();}},200);
