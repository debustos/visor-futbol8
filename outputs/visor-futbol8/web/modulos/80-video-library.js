'use strict';

// The library belongs to the season, independently of the selected match half.
const libraryState={snapshot:null,timer:null,previewEnd:null,loading:false,lastCompleted:null};
const libraryCard=document.createElement('div');
libraryCard.className='card video-library';
libraryCard.innerHTML=`<div class="season-title"><div><span class="section-label">ORIGINALES Y COMPROBACIONES</span><h2>Biblioteca de vídeos</h2></div><button id="library-scan" class="button secondary" type="button">Comprobar vídeos nuevos</button></div>
<p class="small">Deja los originales en la carpeta configurada. Se registran por jornada y parte; el análisis se inicia desde la tabla de Jornadas.</p>
<details id="library-settings"><summary>Configurar carpeta una vez</summary><form id="library-config" class="library-form">
<label>Carpeta local o sincronizada<input id="library-directory" required placeholder="C:\\Futbol8Datos"></label>
<label>Temporada de esta biblioteca<input id="library-season" required pattern="temporada-[0-9]{4}(-[0-9]{4})?" placeholder="temporada-2026"></label>
<p class="small">Se crearán originales/temporada-2026/, ejemplos/ y resultados/. Dentro de la temporada, usa jornada-002/primera.mp4 y segunda.mp4. El registro actual admite una temporada; cambiar esta carpeta no crea otro registro.</p>
<p class="small">Google Drive: descarga o sincroniza los originales completos antes de comprobarlos. Puedes conservar su ubicación para reutilizar el análisis.</p>
<button class="button primary" type="submit">Guardar carpeta y comprobar</button></form></details>
<p id="library-directory-info" class="small library-path"></p><p id="library-status" role="status" aria-live="polite"></p>
<div class="table-wrap"><table id="library-files"></table></div><details><summary>Comprobar modelos del inventario</summary><p class="small">Estas comprobaciones incluyen los modelos de modelos.json; OCR y otros recursos adicionales se comprueban al ejecutar sus etapas.</p><ul id="library-models" class="small"></ul></details>
<details id="library-examples"><summary>Ejemplos compartidos para comprobar mejoras</summary><p class="small">Guarda intervalos del original. Desarrollo sirve para ajustar; reserva, para comprobar. Estos ejemplos no son confirmaciones deportivas.</p>
<form id="library-example-form" class="library-form"><label>Parte registrada<select id="library-example-part" required></select></label>
<label>Nombre del ejemplo<input id="library-example-label" maxlength="160" required placeholder="Cruce de jugadores"></label>
<div class="two-fields"><label>Inicio (segundos)<input id="library-example-start" type="number" min="0" step="any" required value="0"></label><label>Fin (segundos)<input id="library-example-end" type="number" min="0" step="any" required></label></div>
<div class="two-fields"><label>Qué comprobar<select id="library-example-category"><option value="balon">Balón</option><option value="identidad">Identidad</option><option value="acciones">Acciones</option><option value="campo">Campo</option><option value="otro">Otro</option></select></label>
<label>Grupo<select id="library-example-split"><option value="desarrollo">Desarrollo</option><option value="reserva">Reserva</option></select></label></div>
<button type="submit" class="button primary">Guardar ejemplo</button></form>
<div class="library-catalogue-actions"><button id="library-export" type="button" class="button secondary">Exportar catálogo</button><label class="button secondary">Importar catálogo<input id="library-import" type="file" accept=".json,application/json" class="sr-only"></label></div>
<p id="library-catalogue-status" class="small" role="status"></p><div id="library-example-list"></div>
<video id="library-preview" class="library-preview" controls preload="metadata" playsinline hidden aria-label="Fragmento del vídeo original"></video></details>`;
$('season').firstElementChild.after(libraryCard);

const libraryLabels={pending:'Pendiente',ready:'Listo para analizar',registered:'Ya registrado',duplicate:'Duplicado',incomplete:'Copia pendiente',needs_metadata:'Revisar nombre',conflict:'Conflicto',error:'No disponible'};

function renderLibrary(snapshot){
 libraryState.snapshot=snapshot;
 const busy=snapshot.state==='scanning';
 $('library-scan').disabled=busy||!snapshot.directory;
 $('library-config').querySelector('button').disabled=busy;
 if(document.activeElement!==$('library-directory')&&!$('library-directory').value)$('library-directory').value=snapshot.directory||snapshot.suggested_directory;
 if(document.activeElement!==$('library-season')&&!$('library-season').value)$('library-season').value=snapshot.season;
 if(!snapshot.directory)$('library-settings').open=true;
 $('library-directory-info').textContent=snapshot.directory?`${snapshot.directory} · ${snapshot.season}`:'Configura la carpeta una vez para empezar.';
 const count=snapshot.files.filter(f=>f.state==='ready').length;
 const verified=snapshot.models.filter(m=>m.state==='verified').length;
 const modelSummary=snapshot.models.length?` Modelos del inventario: ${verified}/${snapshot.models.length} verificados.${verified<snapshot.models.length?' Revisa los modelos antes de analizar.':''}`:'';
 $('library-status').textContent=busy?'Comprobando originales y modelos… Puedes seguir usando el visor.':snapshot.error||(!snapshot.directory?'':snapshot.state==='complete'?`Comprobación terminada · ${count} parte${count===1?' nueva registrada':'s nuevas registradas'}.${modelSummary}`:'Biblioteca configurada.');
 $('library-files').innerHTML=snapshot.files.length?'<thead><tr><th>Jornada / parte</th><th>Archivo</th><th>Estado</th></tr></thead><tbody>'+snapshot.files.map(f=>`<tr><td>${f.round?`J${f.round}`:'Sin jornada'}${f.half?` · P${f.half}`:''}</td><td><span class="library-path">${escape(f.name)}</span>${f.width?`<small>${f.width} × ${f.height} · ${clock(f.duration)}</small>`:''}${f.sha256?`<details><summary>Huella del original</summary><small class="library-path">${escape(f.sha256)}</small></details>`:''}</td><td><strong>${escape(libraryLabels[f.state]||f.state)}</strong><small>${escape(f.message)}</small></td></tr>`).join('')+'</tbody>':'';
 $('library-models').innerHTML=snapshot.models.map(m=>`<li>${escape(m.file)}: ${m.state==='verified'?'verificado':m.state==='missing'?'no disponible':'huella distinta del inventario'}</li>`).join('')||'<li>Los modelos se comprueban junto con los vídeos.</li>';
 const options=(seasonState.registry?.matches||[]).flatMap(m=>m.parts.map(p=>`<option value="${m.round}:${p.half}">Jornada ${m.round} · parte ${p.half}</option>`)).join('');
 if($('library-example-part').innerHTML!==options){const previous=$('library-example-part').value;$('library-example-part').innerHTML=options;if([...$('library-example-part').options].some(o=>o.value===previous))$('library-example-part').value=previous;}
 $('library-example-form').querySelector('button').disabled=!snapshot.directory||!options;
 $('library-export').disabled=!snapshot.directory;
 $('library-catalogue-status').textContent=snapshot.catalogue_error||`${snapshot.examples.length} ejemplo${snapshot.examples.length===1?'':'s'} · el catálogo conserva la huella del original y los tiempos, sin rutas de tu equipo.`;
 $('library-example-list').innerHTML=snapshot.examples.map((e,i)=>`<div class="library-example"><div><strong>${escape(e.label)}</strong><small>J${e.round} · P${e.half} · ${e.start}–${e.end} s · ${escape(e.category)} · ${escape(e.split)}</small></div><div class="library-catalogue-actions"><button class="button compact" type="button" data-library-example="${i}" ${e.available?'':'disabled'}>${e.available?'Ver fragmento':'Original no disponible'}</button><button class="button compact" type="button" data-library-remove="${i}">Quitar</button></div></div>`).join('');
 $('library-example-list').querySelectorAll('[data-library-example]').forEach(button=>button.onclick=()=>playLibraryExample(snapshot.examples[Number(button.dataset.libraryExample)]));
 $('library-example-list').querySelectorAll('[data-library-remove]').forEach(button=>button.onclick=async()=>{try{renderLibrary(await seasonRequest('/api/season/library/examples','POST',{remove:snapshot.examples[Number(button.dataset.libraryRemove)].id}));}catch(error){toast(error.message,true);}});
 clearTimeout(libraryState.timer);
 if(busy)libraryState.timer=setTimeout(()=>loadLibrary(),1000);
 else if(snapshot.files.some(f=>f.state==='incomplete'))libraryState.timer=setTimeout(()=>scanLibrary(),15000);
 if(snapshot.state==='complete'&&snapshot.checked_at!==libraryState.lastCompleted){libraryState.lastCompleted=snapshot.checked_at;reloadSeason().then(()=>renderLibrary(snapshot));}
}

async function loadLibrary(){
 try{renderLibrary(await seasonRequest('/api/season/library'));}
 catch(error){$('library-status').textContent=error.message;}
}

async function scanLibrary(){
 if(libraryState.loading)return;
 libraryState.loading=true;$('library-scan').disabled=true;
 try{renderLibrary(await seasonRequest('/api/season/library/scan','POST',{}));}
 catch(error){$('library-status').textContent=error.message;$('library-scan').disabled=false;}
 finally{libraryState.loading=false;}
}

$('library-config').onsubmit=async event=>{
 event.preventDefault();
 try{renderLibrary(await seasonRequest('/api/season/library/config','POST',{directory:$('library-directory').value.trim(),season:$('library-season').value.trim()}));$('library-settings').open=false;}
 catch(error){$('library-status').textContent=error.message;}
};
$('library-scan').onclick=scanLibrary;
$('library-example-form').onsubmit=async event=>{
 event.preventDefault();const [round,half]=$('library-example-part').value.split(':').map(Number);
 try{renderLibrary(await seasonRequest('/api/season/library/examples','POST',{round,half,start:Number($('library-example-start').value),end:Number($('library-example-end').value),label:$('library-example-label').value,category:$('library-example-category').value,split:$('library-example-split').value}));toast('Ejemplo guardado.');}
 catch(error){toast(error.message,true);}
};
$('library-export').onclick=async()=>{
 try{const catalogue=await seasonRequest('/api/season/library/catalogue');const url=URL.createObjectURL(new Blob([JSON.stringify(catalogue,null,2)],{type:'application/json'}));const a=document.createElement('a');a.href=url;a.download='catalogo.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}
 catch(error){toast(error.message,true);}
};
$('library-import').onchange=async event=>{
 const file=event.target.files[0];if(!file)return;
 try{if(file.size>28000)throw new Error('El catálogo es demasiado grande para esta importación (máximo 28 KB).');renderLibrary(await seasonRequest('/api/season/library/examples','POST',{catalogue:JSON.parse(await file.text())}));toast('Catálogo incorporado. Los originales se reconocen por su huella.');}
 catch(error){toast(error.message,true);}finally{event.target.value='';}
};
function playLibraryExample(example){
 const preview=$('library-preview');preview.hidden=false;preview.pause();libraryState.previewEnd=example.end;
 preview.onloadedmetadata=()=>{preview.currentTime=example.start;preview.play().catch(()=>{});};
 preview.src=`/media?round=${example.round}&half=${example.half}`;preview.load();
}
$('library-preview').ontimeupdate=()=>{if(libraryState.previewEnd!==null&&$('library-preview').currentTime>=libraryState.previewEnd)$('library-preview').pause();};
$('library-preview').onerror=()=>toast('El navegador no puede reproducir este formato. El visor usará la copia compatible cuando el análisis la genere.',true);

// Wait for the host season token, even if bootstrap has already selected a half.
const libraryInit=setInterval(()=>{
 if(!seasonState.registry)return;
 clearInterval(libraryInit);
 seasonRequest('/api/season/library').then(snapshot=>snapshot.directory?scanLibrary():renderLibrary(snapshot)).catch(error=>{$('library-status').textContent=error.message;});
},150);
