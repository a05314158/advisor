/* UI-only state: the server ranks cards, applies caps, thresholds and rounding. */
const checkout = (() => {
  'use strict';
  const el = id => document.getElementById(id);
  const field = el('buyAmount'), status = el('buyStatus'), results = el('buyResults');
  let scope = 'mine', selected = '', expanded = true, more = false, epoch = 0, timer, recording = false;
  let owner;
  const publicIds = new Set(['supermarkets','cafe','fuel','pharmacy','transport','clothing','electronics','marketplace','entertainment','utilities','travel','all']);
  const paths = {
    supermarkets:'M2 3h3l3 13h12l2-10H6 M9 19a1.5 1.5 0 1 0 .1 0 M18 19a1.5 1.5 0 1 0 .1 0',
    cafe:'M3 8h14v5a6 6 0 0 1-6 6H9a6 6 0 0 1-6-6z M17 9h2a3 3 0 0 1 0 6h-2 M3 22h16 M7 3v2 M12 2v3',
    fuel:'M3 21V4a1 1 0 0 1 1-1h9a1 1 0 0 1 1 1v17 M2 21h14 M6 6h5v5H6z M14 12h2a2 2 0 0 1 2 2v3a2 2 0 0 0 4 0V9l-4-4 M20 7v3h2',
    pharmacy:'M8 3h8v5h5v8h-5v5H8v-5H3V8h5z',
    transport:'M5 17V6q0-3 7-3t7 3v11q0 2-2 2H7q-2 0-2-2z M5 11h14 M8 15h1 M15 15h1 M7 20l-2 2 M17 20l2 2',
    clothing:'M8 3q4 4 8 0l6 4-3 5-3-2v11H8V10l-3 2-3-5z',
    electronics:'M3 4h18v13H3z M12 17v4 M8 21h8',marketplace:'M3 8l3-5h12l3 5v2q-2 3-4 0-3 3-5 0-3 3-5 0-2 3-4 0z M5 13v8h14v-8',
    entertainment:'M3 7l16-5 2 5-16 5z M4 12h17v9H4z M8 6l3 3 M14 4l3 3',utilities:'M13 2L5 14h6l-1 8 9-13h-7z',
    travel:'M3 8h18v13H3z M9 8V4h6v4 M7 9v11 M17 9v11',all:'M2 5h20v14H2z M3 10h18 M6 15h3',
    other:'M3 5h12l7 7-10 10-9-9z M7 9h1'};
  function icon(id) {
    const ns='http://www.w3.org/2000/svg', svg=document.createElementNS(ns,'svg'), path=document.createElementNS(ns,'path');
    svg.setAttribute('viewBox','0 0 24 24'); svg.setAttribute('aria-hidden','true'); path.setAttribute('d',paths[id]||paths.other); svg.append(path); return svg;
  }
  const node = (tag,text,cl) => { const n=document.createElement(tag); if(text!=null)n.textContent=text; if(cl)n.className=cl; return n; };
  function button(text,fn,cl='buy-secondary'){const b=node('button',text,cl);b.type='button';b.onclick=fn;return b;}
  const amountText = n=>new Intl.NumberFormat('ru-RU',{maximumFractionDigits:2}).format(n/100)+' ₽';
  const day = d=>new Intl.DateTimeFormat('ru-RU',{timeZone:'UTC'}).format(new Date(d+'T00:00:00Z'));
  function parse(raw){
    const t=raw.trim(); if(!t)return {msg:'Введите сумму покупки.'};
    if(t.startsWith('-'))return {msg:'Сумма не может быть отрицательной.'};
    if(/[.,]\d{3,}$/.test(t))return {msg:'Укажите не больше двух знаков после запятой.'};
    const m=/^(\d+|\d{1,3}(?:[ \u00a0\u202f]\d{3})+)(?:[.,](\d{1,2}))?$/.exec(t);
    if(!m)return {msg:'Введите сумму целиком, например 2 500,50.'};
    const value=Number(m[1].replace(/\s/g,''))*100+Number((m[2]||'').padEnd(2,'0'));
    if(value>1e12)return {msg:'Максимальная сумма — 10 000 000 000 ₽.'};
    return value?{value}:{msg:'Сумма должна быть больше нуля.'};
  }
  const label=id=>categories[id]||id;
  function paint(){
    const grid=el('categoryGrid'), change=el('changeCategory');
    const ids=Object.keys(categories).filter(id=>scope==='mine'||publicIds.has(id));
    if(selected&&!ids.includes(selected)){selected='';expanded=true;}
    grid.replaceChildren(); grid.hidden=!expanded;change.hidden=!selected;
    change.replaceChildren(icon(selected),node('strong',label(selected)),node('span',expanded?'Свернуть':'Изменить'));
    change.setAttribute('aria-expanded',String(expanded)); el('categoryHeading').hidden=!!selected;
    ids.forEach((id,i)=>{
      const name=label(id); const b=button('',()=>{selected=id;expanded=false;paint();change.focus({preventScroll:true});queue();},'tile'); b.dataset.id=id;
      if(name.length>12) b.classList.add('tile-wide');
      b.setAttribute('aria-pressed',String(id===selected)); b.append(icon(id),node('span',name)); b.hidden=i>=6&&!more&&id!==selected; grid.append(b);
    });
    el('moreCategories').hidden=!expanded||ids.length<=6;el('moreCategories').textContent=more?'Скрыть остальные категории':'Все категории';el('moreCategories').setAttribute('aria-expanded',String(more));
    document.querySelectorAll('[data-scope]').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.scope===scope)));
    el('scopeNote').textContent=scope==='all'?'Пример расчёта на учебных картах.':'Сравниваем карты и ставки, которые вы добавили.';
  }
  function setScope(mode){scope=mode;paint();queue();}
  function term(host,name,value){host.append(node('dt',name),node('dd',value));}
  function row(r,index,all){
    const article=node('article',null,index?'advice-row':'advice-winner');
    const title=node('h4',r.bankName===r.cardName?r.cardName:`${r.bankName} · ${r.cardName}`);
    const val=node('strong',amountText(r.cashbackKopecks),'advice-value');article.append(title,val);
    const ruleName=r.label||label(r.categoryId);const rate=formatRate(r.rateBps)+'%';
    const calc=r.calculation;
    const ruleCapped=calc?.afterCategoryLimitKopecks<calc?.beforeLimitsKopecks;
    const monthCapped=calc?.monthlyRemainingKopecks!=null&&calc.monthlyRemainingKopecks<calc.afterCategoryLimitKopecks;
    const explanation=monthCapped
      ? `По ставке ${amountText(calc.beforeLimitsKopecks)}. Остаток месяца — ${amountText(calc.monthlyRemainingKopecks)}.`
      : ruleCapped ? `По ставке ${amountText(calc.beforeLimitsKopecks)}. Лимит категории — ${amountText(calc.afterCategoryLimitKopecks)}.` : '';
    if (!index&&r.cashbackKopecks>0) article.prepend(node('p','Лучший кэшбэк','buy-note'));
    article.append(node('p',label(selected),'advice-cat'),node('p',`${r.categoryId==='all'&&selected!=='all'?'Ставка на все покупки':ruleName} · ${rate}`));
    if(explanation) article.append(node('p',explanation));
    if(all.some((x,i)=>i!==index&&x.cashbackKopecks===r.cashbackKopecks))article.append(node('p','Ещё одна карта даёт такой же возврат.','buy-note'));
    const details=node('details'), dl=node('dl');details.append(node('summary','Условия'),dl);
    term(dl,'Ставка',rate);term(dl,'Категория правила',ruleName);term(dl,'Минимальная покупка',r.minAmountKopecks==null?'Не указана':amountText(r.minAmountKopecks));
    term(dl,'Лимит правила',r.limitKopecks===null?'Без ограничения':r.limitKopecks===undefined?'Неизвестен':`${amountText(r.limitKopecks)} · ${ruleCapped?'применён':'не применён'}`);
    if(calc) {
      term(dl,'По ставке',amountText(calc.beforeLimitsKopecks));
      if(ruleCapped) term(dl,'После лимита категории',amountText(calc.afterCategoryLimitKopecks));
      if(calc.monthlyRemainingKopecks!=null) term(dl,'Остаток месяца',amountText(calc.monthlyRemainingKopecks));
      term(dl,'Ожидаемый кэшбэк',amountText(r.cashbackKopecks));
    }
    term(dl,'Период',`${r.validFrom?'С '+day(r.validFrom):'Начало неизвестно'}${r.validUntilExclusive?' до '+day(r.validUntilExclusive)+' (не включая)':' · конец не указан'}`);
    term(dl,'Актуальность',r.updatedOn?day(r.updatedOn):'Дата не указана');const sources={catalog:'Учебный каталог',manual:'Условия из вашего кошелька',confirmed:'Подключённые условия'};term(dl,'Источник',sources[r.source]||r.source||(!String(r.cardId||'').startsWith('manual-')?'Учебный каталог':'Условия из вашего кошелька'));article.append(details);
    if(index===0&&scope==='mine'&&r.bankAccess?.webUrl){const a=node('a','Открыть официальный сайт банка');a.href=r.bankAccess.webUrl;a.rel='noopener noreferrer';a.target='_blank';article.append(a);}
    return article;
  }
  function recordForm(matches,value){
    const form=node('form',null,'record-form');const select=node('select');select.id='paidWith';select.required=true;select.append(new Option('Выберите карту',''));matches.forEach(r=>select.append(new Option(r.cardName,r.cardId)));
    const l=node('label','Какой картой вы оплатили?');l.htmlFor=select.id;
    const submit=node('button','Записать покупку','buy-primary');submit.type='submit';
    const msg=node('p');msg.setAttribute('role','status');form.append(node('h4','Запись в историю'),node('p',`${label(selected)} · ${amountText(value)}. Просмотр совета не сохраняет покупку.`),l,select,submit,msg);
    form.onsubmit=async e=>{e.preventDefault();if(recording||!select.value)return;const body={chosenCardId:select.value,categoryId:selected,amountKopecks:value};const sig=JSON.stringify(body),key='advisor-purchase:'+deviceLogin;
      let receipt;try{receipt=JSON.parse(sessionStorage.getItem(key))}catch{}if(receipt?.sig!==sig){receipt={sig,id:crypto.randomUUID()};sessionStorage.setItem(key,JSON.stringify(receipt));}
      recording=true;submit.disabled=true;msg.textContent='Записываем…';const ticket=epoch;
      try{await api('/api/me/purchases',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({...body,requestId:receipt.id})});sessionStorage.removeItem(key);if(epoch!==ticket){toast('Покупка записана');return;}field.value='';el('clearAmount').hidden=true;results.replaceChildren();status.textContent='Покупка записана. '+label(selected)+' · '+amountText(value);const next=button('Открыть историю',()=>showHistory());results.append(next);next.focus();}
      catch{msg.textContent='Не удалось подтвердить запись. Повторите с теми же данными — дубля не будет.';}finally{recording=false;submit.disabled=false;}
    };return form;
  }
  async function calculate(ticket,value){
    const req=mode=>api('/api/recommendations',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({categoryId:selected,amountKopecks:value,scope:mode})});
    try{const data=await req(scope);if(ticket!==epoch)return;const all=data.allMatches;
      if(!all.length){status.textContent=scope==='all'?'В учебном каталоге подходящих условий нет.':manual.length+saved.length?'По вашим картам подходящих условий нет.':'Кошелёк пуст. Добавьте карту или сравните учебные предложения.';}
      else{status.textContent=all[0].cashbackKopecks===0?`По ${scope==='mine'?'вашим картам':'каталогу'} в категории «${label(selected)}» — 0 ₽.`:`Ожидаемый возврат · карт в сравнении: ${all.length}`;
        data.top3.forEach((r,i)=>results.append(row(r,i,all)));if(all.length>data.top3.length){const more=node('details',null,'more-results');const summary=node('summary',`Все подходящие карты (${all.length})`);more.append(summary);summary.parentElement.addEventListener('toggle',()=>{if(!more.open||more.dataset.filled)return;more.dataset.filled='1';all.slice(data.top3.length).forEach((r,i)=>more.append(row(r,i+data.top3.length,all)));});results.append(more);}
        if(scope==='mine')results.append(recordForm(all,value));}
      if(scope==='mine'&&(!all.length||!all[0].cashbackKopecks)&&publicIds.has(selected)){let alt=data.catalogSuggestion;if(!alt){try{alt=(await req('all')).top3[0]}catch{return;}}if(ticket===epoch&&alt?.cashbackKopecks>0)results.append(button('Посмотреть в каталоге',()=>setScope('all')));}
    }catch{if(ticket!==epoch)return;results.replaceChildren(button('Повторить расчёт',queue));status.textContent='Не удалось рассчитать кэшбэк. Проверьте соединение и повторите.';}
  }
  function queue(){const ticket=++epoch;clearTimeout(timer);results.replaceChildren();const {value,msg}=parse(field.value);field.setAttribute('aria-invalid',String(!!field.value&&!value));el('clearAmount').hidden=!field.value;
    if(!selected||!value){status.textContent=!selected?'Выберите категорию покупки.':msg;return;}status.textContent='Считаем…';timer=setTimeout(()=>calculate(ticket,value),160);}
  el('changeCategory').onclick=()=>{expanded=!expanded;paint();if(expanded)el('categoryGrid').querySelector('[aria-pressed=true]')?.focus();};
  el('moreCategories').onclick=()=>{more=!more;paint();if(more)el('categoryGrid').children[6]?.focus();};
  field.oninput=queue;el('clearAmount').onclick=()=>{field.value='';field.focus();queue();};document.querySelectorAll('[data-scope]').forEach(b=>b.onclick=()=>setScope(b.dataset.scope));
  function refresh(){if(owner!==deviceLogin){owner=deviceLogin;scope='mine';selected='';field.value='';expanded=true;more=false;}paint();if(!el('buyPanel').hidden)queue();}
  return {refresh,open(){refresh();el('buyTitle').focus({preventScroll:true});}};
})();
