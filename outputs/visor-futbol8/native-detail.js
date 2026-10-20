"use strict";
async function refreshNativeDetail(){
 const host=document.getElementById('native-detail');if(!host||typeof state==='undefined'||!state.boot)return;
 try{
  const q=await api('/api/automatic/native-ball-status');
  if(!q||!q.state){host.hidden=true;return;}
  if(q.state==='processing'){
   const value=Math.max(0,Math.min(99,Number(q.progress)||0));
   host.innerHTML=`<strong>Mejorando el seguimiento del balón · ${value.toFixed(1)}%</strong><p>Revisando fotogramas a la velocidad original y comprobando las trayectorias en ambos sentidos.</p><progress max="100" value="${value}" aria-label="Progreso del análisis detallado"></progress><p class="small">Los resultados publicados siguen disponibles mientras se comprueba esta mejora.</p>`;
   host.hidden=false;
  }else if(q.state==='complete'){
   const published=await api('/api/automatic/quality');const native=published.native_ball||{};
   const sameRun=q.run_id?native.run_id===q.run_id:native.run_seconds===q.run_seconds&&native.unique_native_ball_measurements===q.unique_native_ball_measurements;
   host.hidden=sameRun;
   if(!sameRun)host.innerHTML='<strong>Revisión del balón calculada</strong><p>Hay nuevos resultados pendientes de validación. Las fichas muestran la última versión publicada.</p>';
  }else if(q.state==='failed'){
   host.textContent='La mejora del seguimiento se interrumpió. Los resultados anteriores siguen disponibles.';host.hidden=false;
  }else{
   host.hidden=true;
  }
 }catch(e){host.hidden=true;}
}
setInterval(refreshNativeDetail,10000);
const nativeInit=setInterval(()=>{if(typeof state!=='undefined'&&state.boot){clearInterval(nativeInit);refreshNativeDetail();}},150);
