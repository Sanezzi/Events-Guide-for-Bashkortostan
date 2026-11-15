(function(){
  const box=document.getElementById('messages');
  const form=document.getElementById('chat-form');
  const input=document.getElementById('chat-input');
  const sendBtn=document.getElementById('chat-send');
  const confirmBox=document.getElementById('confirm-box');
  const confirmText=document.getElementById('confirm-text');
  const yesBtn=document.getElementById('confirm-yes');
  const noBtn=document.getElementById('confirm-no');
  const fmt=new Intl.DateTimeFormat('ru-RU',{day:'2-digit',month:'long',hour:'2-digit',minute:'2-digit',timeZone:'Asia/Yekaterinburg'});
  let sessionId=localStorage.getItem('afisha_session');
  if(!sessionId){sessionId='web-'+Date.now()+'-'+Math.random().toString(36).slice(2);localStorage.setItem('afisha_session',sessionId)}
  let pendingVersion=null;let pendingExpires=0;let busy=false;
  function scroll(){box.scrollTop=box.scrollHeight}
  function addMsg(role,text){
    const d=document.createElement('div');d.className='msg '+(role==='user'?'user':'bot');d.textContent=text;box.append(d);scroll();return d;
  }
  function addNote(parent,text){const n=document.createElement('div');n.className='note';n.textContent=text;parent.append(n);scroll()}
  function priceText(e){if(e.price_known===false)return 'Стоимость уточняется';if(e.is_free||e.price_max===0)return 'Бесплатно';if(e.price_min===e.price_max)return e.price_min+' ₽';return e.price_min+'–'+e.price_max+' ₽'}
  function renderEvents(parent,events){
    (events||[]).slice(0,5).forEach(e=>{
      const c=document.createElement('div');c.style.background='#fff';c.style.border='1px solid #e6ddd0';c.style.borderRadius='12px';c.style.padding='10px';c.style.marginTop='8px';
      const a=document.createElement('a');a.href='/event?id='+encodeURIComponent(e.id);a.textContent=e.title;a.style.fontWeight='800';
      const meta=document.createElement('div');meta.textContent=fmt.format(new Date(e.date_start))+' · '+e.city+' · '+e.venue+' · '+priceText(e)+' · '+e.age_limit+'+';
      const src=document.createElement('a');src.href=e.source_url;src.target='_blank';src.rel='noopener';src.textContent='Источник';
      c.append(a,meta,src);parent.append(c);
    });scroll();
  }
  function hideConfirm(){confirmBox.hidden=true;pendingVersion=null;pendingExpires=0;yesBtn.disabled=false}
  function showConfirm(rc){
    pendingVersion=rc.version||null;pendingExpires=Date.now()+1000*(rc.expires_in_seconds||300);
    confirmText.textContent='Подтвердить действие: '+(rc.summary||rc.action||'действие из ответа агента');
    confirmBox.hidden=false;yesBtn.disabled=false;scroll();
  }
  async function send(message,confirm){
    if(busy)return;busy=true;sendBtn.disabled=true;
    if(!confirm)hideConfirm();
    if(message)addMsg('user',message);
    try{
      const r=await fetch('/api/chat',{method:'POST',headers:{'Content-Type':'application/json'},credentials:'same-origin',body:JSON.stringify({session_id:sessionId,message:message||'Подтверждаю',confirm_action:!!confirm,confirmation_version:confirm?pendingVersion:null})});
      const d=await r.json().catch(()=>null);
      if(!r.ok){addMsg('bot',(d&&d.message)||'Не удалось выполнить запрос. Попробуйте ещё раз.');return}
      const bot=addMsg('bot',d.reply_text);
      if(d.is_fallback)addNote(bot,'Резервный режим: обычный поиск без модели, факты — только из базы сервиса.');
      if(d.clarifying_question && d.clarifying_question!==d.reply_text)addNote(bot,'Уточнение: '+d.clarifying_question);
      if(d.events&&d.events.length)renderEvents(bot,d.events);
      if(d.requires_confirmation)showConfirm(d.requires_confirmation);else if(confirm)hideConfirm();
    }catch(e){addMsg('bot','Сервис временно недоступен. Каталог на главной странице продолжает работать через обычный поиск.')}
    finally{busy=false;sendBtn.disabled=false;input.focus()}
  }
  form.addEventListener('submit',e=>{e.preventDefault();const v=input.value.trim();if(!v)return;input.value='';send(v,false)});
  yesBtn.addEventListener('click',()=>{if(Date.now()>pendingExpires){hideConfirm();addMsg('bot','Время подтверждения истекло (300 секунд). Отправьте запрос заново.');return}yesBtn.disabled=true;confirmBox.hidden=true;send('Подтверждаю',true)});
  noBtn.addEventListener('click',()=>{hideConfirm();send('Отмена',false)});
  addMsg('bot','Здравствуйте! Напишите, куда хотите сходить: город, дату, возраст и бюджет. Например: «концерты в Уфе в ближайшую неделю».');
  const preset=new URLSearchParams(location.search).get('message');
  if(preset){input.value=preset}
})();
