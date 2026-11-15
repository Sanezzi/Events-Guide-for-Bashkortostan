(function(){
  const id=new URLSearchParams(location.search).get('id');
  const root=document.getElementById('root');
  const fmt=new Intl.DateTimeFormat('ru-RU',{day:'2-digit',month:'long',year:'numeric',hour:'2-digit',minute:'2-digit',timeZone:'Asia/Yekaterinburg'});
  const money=n=>new Intl.NumberFormat('ru-RU').format(n)+' ₽';
  function priceText(e){if(e.price_known===false)return 'Уточняйте у организатора';if(e.is_free||e.price_max===0)return 'Бесплатно';if(e.price_min===e.price_max)return money(e.price_min);return money(e.price_min)+' – '+money(e.price_max)}
  function row(dt,dd){const t=document.createElement('dt');t.textContent=dt;const d=document.createElement('dd');d.textContent=dd;return[t,d]}
  function sessionId(){let s=localStorage.getItem('afisha_session');if(!s){s='web-'+Date.now()+'-'+Math.random().toString(36).slice(2);localStorage.setItem('afisha_session',s)}return s}
  async function load(){
    if(!id){root.textContent='Не указан идентификатор события. Вернитесь в каталог и выберите событие.';return}
    try{
      const r=await fetch('/api/v1/events/'+encodeURIComponent(id));
      if(r.status===404){root.textContent='Событие не найдено. Возможно, ссылка устарела.';return}
      if(!r.ok)throw new Error('HTTP '+r.status);
      const e=await r.json();
      root.textContent='';
      if(e.status==='отменено'){const n=document.createElement('p');n.style.color='#9b2c2c';n.style.fontWeight='800';n.textContent='Внимание: это событие отменено. В обычную выдачу каталога оно не попадает.';root.append(n)}
      const badge=document.createElement('span');badge.className='badge'+(e.is_free?' free':'');badge.textContent=e.is_free?'Бесплатно':e.category;root.append(badge);
      const h=document.createElement('h1');h.textContent=e.title;root.append(h);
      const desc=document.createElement('p');desc.textContent=e.description;root.append(desc);
      const dl=document.createElement('dl');
      row('Категория',e.category).forEach(x=>dl.append(x));
      row('Начало',fmt.format(new Date(e.date_start))).forEach(x=>dl.append(x));
      if(e.date_end)row('Окончание',fmt.format(new Date(e.date_end))).forEach(x=>dl.append(x));
      if(e.duration_min)row('Длительность',e.duration_min+' мин').forEach(x=>dl.append(x));
      row('Город',e.city).forEach(x=>dl.append(x));
      row('Площадка',e.venue).forEach(x=>dl.append(x));
      row('Адрес',e.address).forEach(x=>dl.append(x));
      row('Цена',priceText(e)).forEach(x=>dl.append(x));
      row('Возрастное ограничение',e.age_limit+'+').forEach(x=>dl.append(x));
      if(e.language)row('Язык',e.language).forEach(x=>dl.append(x));
      row('Статус',e.status).forEach(x=>dl.append(x));
      root.append(dl);
      const p=document.createElement('p');
      const src=document.createElement('a');src.className='btn';src.href=e.source_url;src.target='_blank';src.rel='noopener';src.textContent='Источник события';p.append(src);
      if(e.org_link){const org=document.createElement('a');org.className='btn ghost';org.href=e.org_link;org.target='_blank';org.rel='noopener';org.textContent='Организатор / билеты';org.style.marginLeft='8px';p.append(org)}
      root.append(p);
      if((e.sources||[]).length>1){
        const sources=document.createElement('ul');
        sources.setAttribute('aria-label','Источники события');
        for(const url of e.sources){
          const item=document.createElement('li');const link=document.createElement('a');
          link.href=url;link.target='_blank';link.rel='noopener';link.textContent=new URL(url).hostname;
          item.append(link);sources.append(item);
        }
        root.append(sources);
      }
      document.title=e.title+' — Афиша культуры Башкортостана';
      document.getElementById('feedback-box').hidden=false;
      loadSimilar();
    }catch(err){root.textContent='Не удалось загрузить событие. Проверьте, что сервер запущен.'}
  }
  async function loadSimilar(){
    try{
      const r=await fetch('/api/v1/events/'+encodeURIComponent(id)+'/similar');if(!r.ok)return;
      const list=await r.json();const box=document.getElementById('similar');
      if(!list.length){document.getElementById('similar-empty').hidden=false;return}
      list.forEach(e=>{const art=document.createElement('article');art.className='card';const b=document.createElement('div');b.className='card-body';const h=document.createElement('h3');const a=document.createElement('a');a.href='/event?id='+encodeURIComponent(e.id);a.textContent=e.title;h.append(a);const w=document.createElement('div');w.className='when';w.textContent=fmt.format(new Date(e.date_start));const wh=document.createElement('div');wh.className='where';wh.textContent=e.city+' · '+e.venue;b.append(h,w,wh);art.append(b);box.append(art)});
    }catch(e){}
  }
  document.getElementById('feedback-form').addEventListener('submit',async ev=>{
    ev.preventDefault();const out=document.getElementById('feedback-result');out.textContent='Отправка…';
    try{const r=await fetch('/api/v1/feedback',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({session_id:sessionId(),event_id:id,text:document.getElementById('feedback-text').value.trim()})});const d=await r.json();out.textContent=r.ok?d.message:(d.message||'Не удалось отправить обращение.');if(r.ok)ev.target.reset()}catch(e){out.textContent='Не удалось отправить обращение.'}
  });
  load();
})();
