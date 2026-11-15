(function(){
  const sel=document.getElementById('city');const out=document.getElementById('result');
  const list=document.getElementById('subscriptions');
  async function loadSubscriptions(){
    list.replaceChildren();
    const response=await fetch('/api/v1/subscriptions');
    if(!response.ok){out.textContent='Не удалось загрузить подписки.';return}
    for(const sub of await response.json()){
      const row=document.createElement('li');
      const button=document.createElement('button');
      button.type='button';button.className='btn ghost';button.textContent='Отписаться';
      button.addEventListener('click',async()=>{
        const result=await fetch('/api/v1/subscriptions/'+encodeURIComponent(sub.id),{method:'DELETE'});
        out.textContent=result.ok?'Подписка удалена.':'Не удалось удалить подписку.';
        if(result.ok)loadSubscriptions();
      });
      row.append(document.createTextNode(sub.city+' · '+(sub.category||'все категории')+' '),button);
      list.append(row);
    }
  }
  loadSubscriptions().catch(()=>{out.textContent='Не удалось загрузить подписки.'});
  fetch('/api/v1/cities').then(r=>r.json()).then(d=>{(d.cities||[]).forEach(c=>{const o=document.createElement('option');o.value=c;o.textContent=c;sel.append(o)})}).catch(()=>{out.textContent='Не удалось загрузить список городов.'});
  document.getElementById('sub-form').addEventListener('submit',async e=>{
    e.preventDefault();out.textContent='Оформление…';
    const body={city:sel.value,period:document.getElementById('period').value};
    const cat=document.getElementById('category').value;if(cat)body.category=cat;
    try{const r=await fetch('/api/v1/subscriptions',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});const d=await r.json();out.textContent=r.ok?d.message:((d&&d.message)||'Не удалось оформить подписку.');if(r.ok)await loadSubscriptions()}catch(err){out.textContent='Не удалось оформить подписку. Проверьте, что сервер запущен.'}
  });
})();;
