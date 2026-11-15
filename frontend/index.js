document.addEventListener('DOMContentLoaded',function(){var f=document.getElementById('search-form');var bar=document.querySelector('.topbar-in');if(f&&bar){f.classList.add('topbar-search');bar.appendChild(f);}});;
(function(){
  const catalog=document.getElementById('catalog');
  const meta=document.getElementById('result-meta');
  const empty=document.getElementById('empty');
  const form=document.getElementById('filters');
  const searchForm=document.getElementById('search-form');
  const city=document.getElementById('city');
  const venue=document.getElementById('venue');
  const venueStatus=document.getElementById('venue-status');
  let venueRequest=0;
  const fmt=new Intl.DateTimeFormat('ru-RU',{day:'2-digit',month:'long',year:'numeric',hour:'2-digit',minute:'2-digit',timeZone:'Asia/Yekaterinburg'});
  const money=n=>new Intl.NumberFormat('ru-RU').format(n)+' ₽';
  function params(){
    const p=new URLSearchParams(location.search);
    return p;
  }
  function fillFromUrl(){
    const p=params();
    ['city','category','date_from','date_to','price_max','age_limit','sort'].forEach(k=>{const el=document.getElementById(k);if(el&&p.get(k))el.value=p.get(k)});
    if(p.get('is_free')==='true')document.getElementById('is_free').checked=true;
    const q=document.getElementById('q');if(p.get('text'))q.value=p.get('text');
  }
  function readForm(){
    const p=new URLSearchParams();
    const fd=new FormData(form);
    const q=document.getElementById('q').value.trim();
    if(q)p.set('text',q);
    ['city','venue','category','date_from','date_to','price_max','age_limit','sort'].forEach(k=>{const v=fd.get(k);if(v)p.set(k,v)});
    if(fd.get('is_free'))p.set('is_free','true');
    return p;
  }
  function priceText(e){
    if(e.price_known===false)return 'Уточняйте у организатора';
    if(e.is_free||e.price_max===0)return 'Бесплатно';
    if(e.price_min===e.price_max)return money(e.price_min);
    return money(e.price_min)+' – '+money(e.price_max);
  }
  function card(e){
    const art=document.createElement('article');art.className='card';
    const body=document.createElement('div');body.className='card-body';
    const badge=document.createElement('span');badge.className='badge'+(e.is_free?' free':'');badge.textContent=e.is_free?'Бесплатно':e.category;
    const h=document.createElement('h3');const a=document.createElement('a');a.href='/event?id='+encodeURIComponent(e.id);a.textContent=e.title;h.append(a);
    const when=document.createElement('div');when.className='when';when.textContent=fmt.format(new Date(e.date_start));
    const where=document.createElement('div');where.className='where';where.textContent=e.city+' · '+e.venue;
    const price=document.createElement('div');price.className='price';price.textContent=priceText(e)+' · '+e.age_limit+'+';
    const desc=document.createElement('p');desc.className='desc';desc.textContent=e.description;
    const foot=document.createElement('div');foot.className='foot';
    const open=document.createElement('a');open.className='btn';open.href='/event?id='+encodeURIComponent(e.id);open.textContent='Открыть';
    const src=document.createElement('a');src.className='src';src.href=e.source_url;src.target='_blank';src.rel='noopener';src.textContent='Источник';
    foot.append(open,src);body.append(badge,h,when,where,price,desc,foot);art.append(body);return art;
  }
  async function loadCities(){
    try{
      const response=await fetch('/api/v1/cities');
      if(!response.ok)throw new Error();
      const data=await response.json();
      for(const name of data.cities)city.add(new Option(name,name));
    }catch(e){}
  }
  async function loadVenues(selected){
    const version=++venueRequest;
    const query=city.value ? '?'+new URLSearchParams({city:city.value}) : '';
    venue.replaceChildren(new Option('Все площадки',''));
    venue.disabled=true;
    venueStatus.hidden=true;
    try{
      const response=await fetch('/api/v1/venues'+query);
      if(!response.ok)throw new Error();
      const data=await response.json();
      if(version!==venueRequest)return;
      for(const name of data.venues)venue.add(new Option(name,name));
      venue.value=data.venues.includes(selected) ? selected : '';
      venueStatus.textContent='В выбранном городе пока нет площадок с актуальными событиями.';
      venueStatus.hidden=data.venues.length>0;
    }catch(e){
      if(version!==venueRequest)return;
      venueStatus.textContent='Не удалось загрузить площадки. Выберите город ещё раз.';
      venueStatus.hidden=false;
    }finally{
      if(version===venueRequest)venue.disabled=false;
    }
  }
  const more=document.getElementById('more-events');
  let offset=0;
  let requestVersion=0;
  more.addEventListener('click',()=>load(true));
  city.addEventListener('change',()=>loadVenues(venue.value));
  async function load(append=false){
    const version=++requestVersion;const p=params();meta.textContent='Загрузка афиши…';empty.hidden=true;more.hidden=true;if(!append){offset=0;catalog.textContent='';}
    const qs=new URLSearchParams();
    ['city','venue','category','text','sort'].forEach(k=>{if(p.get(k))qs.set(k,p.get(k))});
    ['price_max','age_limit'].forEach(k=>{if(p.get(k))qs.set(k,p.get(k))});
    if(p.get('date_from'))qs.set('date_from',p.get('date_from')+'T00:00:00+05:00');
    if(p.get('date_to'))qs.set('date_to',p.get('date_to')+'T23:59:59+05:00');
    if(p.get('is_free')==='true')qs.set('is_free','true');
    qs.set('limit','20');qs.set('offset',String(offset));
    try{
      const r=await fetch('/api/v1/events?'+qs.toString());
      if(!r.ok){
        const problem=await r.json();
        if(version===requestVersion)meta.textContent=problem.message||'Не удалось загрузить афишу.';
        return;
      }
      const d=await r.json();
      if(version!==requestVersion)return;
      meta.textContent='Найдено событий: '+d.total;
      if(!d.events.length&&!append){
        const relaxation={city:'выбрать другой город',venue:'выбрать другую площадку',category:'убрать категорию',max_price:'увеличить бюджет',age:'проверить возраст',date_from:'расширить период',date_to:'расширить период',q:'изменить текст запроса',is_free:'включить платные события'};
        empty.textContent='Подходящих событий нет. Попробуйте '+(relaxation[d.explanation]||'ослабить один из фильтров')+'.';empty.hidden=false;return;
      }
      offset+=d.events.length;more.hidden=offset>=d.total;
      d.events.forEach(e=>catalog.append(card(e)));
    }catch(err){if(version===requestVersion)meta.textContent='Не удалось загрузить афишу. Попробуйте ещё раз.';}
  }
  form.addEventListener('submit',e=>{e.preventDefault();const p=readForm();history.pushState(null,'','/'+(p.toString()?'?'+p.toString():''));load();});
  searchForm.addEventListener('submit',e=>{e.preventDefault();const p=readForm();history.pushState(null,'','/'+(p.toString()?'?'+p.toString():''));load();});
  function restoreFilters(){
    form.reset();
    document.getElementById('q').value='';
    fillFromUrl();
    loadVenues(params().get('venue'));
    load();
  }
  document.getElementById('reset-filters').addEventListener('click',()=>{history.pushState(null,'','/');restoreFilters();});
  addEventListener('popstate',restoreFilters);
    let agentSession=localStorage.getItem('afisha_session');
  if(!agentSession){agentSession='web-'+Date.now()+'-'+Math.random().toString(36).slice(2);localStorage.setItem('afisha_session',agentSession)}
  let agentBusy=false;
  function agentMsg(role,text){const box=document.getElementById('agent-messages');const d=document.createElement('div');d.className='msg '+(role==='user'?'user':'bot');d.textContent=text;box.append(d);box.scrollTop=box.scrollHeight;return d}
  async function agentSend(message,confirmation=null){
    if(agentBusy||!message)return;agentBusy=true;const btn=document.getElementById('agent-send');btn.disabled=true;document.getElementById('agent-status').textContent='Агент думает…';agentMsg('user',message);
    try{
      const r=await fetch('/api/chat',{method:'POST',headers:{'Content-Type':'application/json'},credentials:'same-origin',body:JSON.stringify({session_id:agentSession,message:message,confirm_action:!!confirmation,confirmation_version:confirmation})});
      const d=await r.json().catch(()=>null);
      if(!r.ok){agentMsg('bot',(d&&d.message)||'Не удалось выполнить запрос. Попробуйте ещё раз.');return}
      const bot=agentMsg('bot',d.reply_text||'');
      if(d.is_fallback){const n=document.createElement('div');n.className='note';n.textContent='Резервный режим: обычный поиск без модели, факты — только из базы сервиса.';bot.append(n)}
      if(d.clarifying_question && d.clarifying_question!==d.reply_text){const n=document.createElement('div');n.className='note';n.textContent='Уточнение: '+d.clarifying_question;bot.append(n)}
      if(d.requires_confirmation){
        const button=document.createElement('button');
        button.type='button';button.className='btn';button.textContent='Подтвердить';
        button.addEventListener('click',()=>{
          button.disabled=true;agentSend('Подтверждаю',d.requires_confirmation.version);
        },{once:true});
        bot.append(button);
      }
      (d.events||[]).slice(0,5).forEach(e=>{const c=document.createElement('div');c.style.background='#fff';c.style.border='1px solid #e6ddd0';c.style.borderRadius='12px';c.style.padding='10px';c.style.marginTop='8px';const a=document.createElement('a');a.href='/event?id='+encodeURIComponent(e.id);a.textContent=e.title;a.style.fontWeight='800';const m=document.createElement('div');m.textContent=fmt.format(new Date(e.date_start))+' · '+e.city+' · '+e.venue;const s=document.createElement('a');s.href=e.source_url;s.target='_blank';s.rel='noopener';s.textContent='Источник';c.append(a,m,s);bot.append(c)});
    }catch(e){agentMsg('bot','Сервис временно недоступен. Каталог продолжает работать через обычный поиск.')}
    finally{agentBusy=false;btn.disabled=false;document.getElementById('agent-status').textContent=''}
  }
  document.querySelectorAll('#inline-agent .chip').forEach(b=>b.addEventListener('click',()=>{const inp=document.getElementById('agent-input');inp.value=b.dataset.q;inp.focus();document.getElementById('agent-form').requestSubmit();}));
  document.getElementById('agent-form').addEventListener('submit',e=>{e.preventDefault();const v=document.getElementById('agent-input').value.trim();if(!v)return;document.getElementById('agent-input').value='';agentSend(v);});
  loadCities().then(restoreFilters);
})();;
