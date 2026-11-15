(function(){
var token=sessionStorage.getItem('afisha_admin_token')||'';
var panel=document.getElementById('panel');
var loginBox=document.getElementById('login-box');
function headers(){return {'Content-Type':'application/json','X-Admin-Token':token}}
async function api(path,opts){opts=opts||{};opts.headers=opts.body instanceof FormData?{'X-Admin-Token':token}:headers();var r=await fetch(path,opts);var d=null;try{d=await r.json()}catch(e){}if(!r.ok)throw new Error((d&&d.message)||('HTTP '+r.status));return d}
function el(tag,text){var e=document.createElement(tag);if(text!==undefined)e.textContent=text;return e}
function show(tab){document.querySelectorAll('#tabs button').forEach(function(b){b.classList.toggle('on',b.dataset.tab===tab)});['events','subs','feedback','journal','traces'].forEach(function(t){document.getElementById('tab-'+t).hidden=t!==tab});if(tab==='subs')loadSubs();if(tab==='feedback')loadFeedback();if(tab==='journal')loadJournal();if(tab==='traces')loadTraces()}
async function loadOverview(){try{var d=await api('/api/v1/admin/overview');var o=document.getElementById('overview');o.textContent='';[['Всего событий',d.events_total],['Опубликовано',d.published],['Подписки',d.subscriptions],['Обращения',d.feedback]].forEach(function(p){var c=el('div');c.append(el('b',String(p[1])),el('span',p[0]));o.append(c)});var h=await fetch('/health').then(function(r){return r.json()});document.getElementById('health-line').textContent='Health: '+h.status+' · версия '+h.version+' · опубликовано: '+h.events_published}catch(e){document.getElementById('health-line').textContent='Ошибка: '+e.message}}
async function loadEvents(){try{var list=await api('/api/v1/admin/events?'+new URLSearchParams(document.getElementById('status-filter').value?{status:document.getElementById('status-filter').value}:{}));var box=document.getElementById('events-list');box.textContent='';var t=el('table');var head=el('tr');['Название','Дата','Город','Цена','Статус',''].forEach(function(h){head.append(el('th',h))});t.append(head);list.forEach(function(e){var tr=el('tr');tr.append(el('td',e.title));tr.append(el('td',new Date(e.date_start).toLocaleString('ru-RU')));tr.append(el('td',e.city));tr.append(el('td',e.is_free?'Бесплатно':e.price_min+'–'+e.price_max+' ₽'));var td=el('td');var sel=el('select');['опубликовано','черновик','отменено'].forEach(function(s){var o=el('option',s);o.value=s;if(s===e.status)o.selected=true;sel.append(o)});sel.addEventListener('change',async function(){try{await api('/api/v1/admin/events/'+e.id+'/status',{method:'PATCH',body:JSON.stringify({status:sel.value})});loadOverview()}catch(err){alert(err.message);loadEvents()}});td.append(sel);tr.append(td);var td2=el('td');var edit=el('button','Править');edit.className='btn ghost';edit.addEventListener('click',function(){editEvent(e)});td2.append(edit);tr.append(td2);t.append(tr)});box.append(t)}catch(e){document.getElementById('events-list').textContent='Ошибка: '+e.message}}
async function loadSubs(){try{var list=await api('/api/v1/admin/subscriptions');var box=document.getElementById('subs-list');box.textContent='';if(!list.length){box.textContent='Подписок пока нет.';return}list.forEach(function(s){var d=el('div');d.textContent=s.city+' · '+(s.category||'все категории')+' · '+s.period+' · '+s.id;box.append(d)})}catch(e){document.getElementById('subs-list').textContent='Ошибка: '+e.message}}
async function loadFeedback(){try{var list=await api('/api/v1/admin/feedback');var box=document.getElementById('feedback-list');box.textContent='';if(!list.length){box.textContent='Обращений пока нет.';return}list.forEach(function(f){var d=el('div');d.textContent=(f.event_id||'')+' · '+f.text;box.append(d)})}catch(e){document.getElementById('feedback-list').textContent='Ошибка: '+e.message}}
async function loadJournal(){var out=document.getElementById('journal');try{out.textContent=JSON.stringify(await api('/api/v1/admin/journal'),null,2)}catch(e){out.textContent=e.message}}
async function loadTraces(){
  const select=document.getElementById('trace-session');
  select.replaceChildren();
  try{
    for(const trace of await api('/api/v1/admin/traces')){
      const option=el('option',new Date(trace.created_at).toLocaleString('ru-RU')+' · '+trace.event_ids.length+' карточек');
      option.value=trace.id;
      select.append(option);
    }
  }catch(error){document.getElementById('trace-out').textContent=error.message}
}
function openPanel(){loginBox.hidden=true;panel.hidden=false;loadOverview();loadEvents()}

document.getElementById('login-form').addEventListener('submit',async function(e){e.preventDefault();token=document.getElementById('token').value.trim();if(!token)return;try{await api('/api/v1/admin/overview');sessionStorage.setItem('afisha_admin_token',token);document.getElementById('login-error').textContent='';openPanel()}catch(err){document.getElementById('login-error').textContent='Неверный токен: '+err.message}});
document.getElementById('logout').addEventListener('click',function(){sessionStorage.removeItem('afisha_admin_token');location.reload()});
document.getElementById('tabs').addEventListener('click',function(e){if(e.target.dataset&&e.target.dataset.tab)show(e.target.dataset.tab)});
document.getElementById('trace-form').addEventListener('submit',async function(e){e.preventDefault();var out=document.getElementById('trace-out');var sid=document.getElementById('trace-session').value.trim();if(!sid)return;out.textContent='Загрузка…';try{var d=await api('/api/v1/admin/traces/'+encodeURIComponent(sid));out.textContent=JSON.stringify(d,null,2)}catch(err){out.textContent='Ошибка: '+err.message}});
let editing=null;
const form=document.getElementById('create-form');
const formValue=name=>document.getElementById('f-'+name);
const fields={title:'title',city:'city',category:'category',venue:'venue',address:'address',pmin:'price_min',pmax:'price_max',age:'age_limit',source:'source_url',tickets:'org_link',description:'description'};
function editEvent(event){
  editing=event;
  document.getElementById('form-title').textContent='Редактирование карточки';
  document.getElementById('new-event').hidden=false;
  Object.entries(fields).forEach(([field,key])=>{formValue(field).value=event[key]??''});
  formValue('start').value=new Date(Date.parse(event.date_start)+5*3600000).toISOString().slice(0,16);
  formValue('title').focus();
}
function resetEditor(){
  editing=null;
  form.reset();
  document.getElementById('form-title').textContent='Новое событие';
  document.getElementById('new-event').hidden=true;
}
document.getElementById('new-event').addEventListener('click',resetEditor);
document.getElementById('status-filter').addEventListener('change',loadEvents);
document.getElementById('import-form').addEventListener('submit',async event=>{
  event.preventDefault();
  const output=document.getElementById('import-result');
  const data=new FormData();
  data.append('file',document.getElementById('import-file').files[0]);
  try{
    const report=await api('/api/v1/admin/import',{method:'POST',body:data});
    output.textContent='Добавлено: '+report.added+' · обновлено: '+report.updated+' · без изменений: '+report.unchanged+' · отклонено: '+report.rejected;
    for(const error of report.errors) output.textContent+='\nСтрока '+error.row+': '+error.message;
    loadEvents();loadOverview();
  }catch(error){output.textContent=error.message}
});
form.addEventListener('submit',async event=>{
  event.preventDefault();
  const output=document.getElementById('create-result');
  const body={...(editing||{}),id:editing?.id||crypto.randomUUID(),status:editing?.status||'черновик'};
  for(const [field,key] of Object.entries(fields)) body[key]=formValue(field).value.trim();
  body.price_min=Number(body.price_min);body.price_max=Number(body.price_max);
  body.age_limit=Number(body.age_limit);body.is_free=body.price_max===0;body.org_link=body.org_link||null;
  body.date_start=formValue('start').value+':00+05:00';
  if(editing?.date_end){
    const shift=Date.parse(body.date_start)-Date.parse(editing.date_start);
    body.date_end=new Date(Date.parse(editing.date_end)+shift).toISOString();
  }
  try{
    await api('/api/v1/admin/events'+(editing?'/'+editing.id:''),{method:editing?'PUT':'POST',body:JSON.stringify(body)});
    output.textContent='Карточка сохранена.';resetEditor();loadEvents();loadOverview();
  }catch(error){output.textContent=error.message}
});
if(token){api('/api/v1/admin/overview').then(openPanel).catch(function(){loginBox.hidden=false})}else{loginBox.hidden=false}
})();
