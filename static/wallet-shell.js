/* Navigation, cards, history and account. Checkout stays in checkout.js.
   Taiga UI patterns, adapted to this page: drawer (add/import/delete), combobox (bank search),
   accordion rows (history), button hierarchy and toast. */
let walletPreferredCard = null, walletReturn = null, deleteTarget = null, addReturn = null, bankSuggest = -1, historyMonth = null;
const shellRoutes = ['home', 'buy', 'cards', 'history', 'account'];
const DEMO_DECK = [
  {cardId:'demo-sber', name:'Сбер', demo:true, paint:{color:'#21A038', ink:'#ffffff', accent:'#d8f5e0'}, rules:[{label:'Транспорт', categoryId:'transport', rateBps:1500},{label:'Кафе', categoryId:'cafe', rateBps:400},{label:'Все покупки', categoryId:'all', rateBps:100}]},
  {cardId:'demo-tbank', name:'Т-Банк', demo:true, paint:{color:'#FFDD2D', ink:'#1D1E1A', accent:'#1D1E1A'}, rules:[{label:'Супермаркеты', categoryId:'supermarkets', rateBps:500},{label:'Кафе', categoryId:'cafe', rateBps:700},{label:'Все покупки', categoryId:'all', rateBps:100}]},
  {cardId:'demo-alfa', name:'Альфа-Банк', demo:true, paint:{color:'#EF3124', ink:'#ffffff', accent:'#ffd0cc'}, rules:[{label:'Кафе', categoryId:'cafe', rateBps:700},{label:'АЗС', categoryId:'fuel', rateBps:500},{label:'Все покупки', categoryId:'all', rateBps:100}]},
  {cardId:'demo-vtb', name:'ВТБ', demo:true, paint:{color:'#002882', ink:'#ffffff', accent:'#c9d4ff'}, rules:[{label:'Транспорт', categoryId:'transport', rateBps:1000},{label:'Аптеки', categoryId:'pharmacy', rateBps:500},{label:'Все покупки', categoryId:'all', rateBps:100}]},
  {cardId:'demo-ozon', name:'Ozon', demo:true, paint:{color:'#005BFF', ink:'#ffffff', accent:'#d6e4ff'}, rules:[{label:'Одежда', categoryId:'clothes', rateBps:500},{label:'Супермаркеты', categoryId:'supermarkets', rateBps:300},{label:'Все покупки', categoryId:'all', rateBps:100}]},
  {cardId:'demo-akbars', name:'Ак Барс', demo:true, paint:{color:'#00915A', ink:'#ffffff', accent:'#d2f5e4'}, rules:[{label:'АЗС', categoryId:'fuel', rateBps:700},{label:'Кафе', categoryId:'cafe', rateBps:400},{label:'Все покупки', categoryId:'all', rateBps:100}]},
  {cardId:'demo-gpb', name:'Газпромбанк', demo:true, paint:{color:'#1F4E9D', ink:'#ffffff', accent:'#d5e2ff'}, rules:[{label:'АЗС', categoryId:'fuel', rateBps:1000},{label:'Транспорт', categoryId:'transport', rateBps:500},{label:'Все покупки', categoryId:'all', rateBps:100}]}
];
const categoryIconPaths={
  supermarkets:'M2 3h3l3 13h12l2-10H6 M9 19a1.5 1.5 0 1 0 .1 0 M18 19a1.5 1.5 0 1 0 .1 0',
  cafe:'M3 8h14v5a6 6 0 0 1-6 6H9a6 6 0 0 1-6-6z M17 9h2a3 3 0 0 1 0 6h-2 M3 22h16 M7 3v2 M12 2v3',
  fuel:'M3 21V4a1 1 0 0 1 1-1h9a1 1 0 0 1 1 1v17 M2 21h14 M6 6h5v5H6z M14 12h2a2 2 0 0 1 2 2v3a2 2 0 0 0 4 0V9l-4-4 M20 7v3h2',
  pharmacy:'M8 3h8v5h5v8h-5v5H8v-5H3V8h5z',
  transport:'M5 17V6q0-3 7-3t7 3v11q0 2-2 2H7q-2 0-2-2z M5 11h14 M8 15h1 M15 15h1 M7 20l-2 2 M17 20l2 2',
  clothes:'M8 3q4 4 8 0l6 4-3 5-3-2v11H8V10l-3 2-3-5z', clothing:'M8 3q4 4 8 0l6 4-3 5-3-2v11H8V10l-3 2-3-5z',
  electronics:'M3 4h18v13H3z M12 17v4 M8 21h8', marketplace:'M3 8l3-5h12l3 5v2q-2 3-4 0-3 3-5 0-3 3-5 0-2 3-4 0z M5 13v8h14v-8',
  entertainment:'M3 7l16-5 2 5-16 5z M4 12h17v9H4z M8 6l3 3 M14 4l3 3', utilities:'M13 2L5 14h6l-1 8 9-13h-7z',
  travel:'M3 8h18v13H3z M9 8V4h6v4 M7 9v11 M17 9v11', all:'M2 5h20v14H2z M3 10h18 M6 15h3',
  other:'M3 5h12l7 7-10 10-9-9z M7 9h1'
};
function categoryIconSvg(id){
  const svg=document.createElementNS('http://www.w3.org/2000/svg','svg');
  svg.setAttribute('viewBox','0 0 24 24');
  svg.setAttribute('aria-hidden','true');
  const path=document.createElementNS('http://www.w3.org/2000/svg','path');
  path.setAttribute('d', categoryIconPaths[id]||categoryIconPaths.other);
  svg.append(path);
  return svg;
}
function walletCount(n){return n===1?'1 карта':n>1&&n<5?`${n} карты`:`${n} карт`;}
function purchaseCount(n){const mod10=n%10, mod100=n%100; const word=mod10===1&&mod100!==11?'покупка':mod10>=2&&mod10<=4&&(mod100<12||mod100>14)?'покупки':'покупок'; return `${n} ${word}`;}
function rubFromField(text){
  const raw=String(text||'').trim();
  if(!raw) throw new Error('Введите сумму');
  if(!/^\d+(?:[.,]\d{1,2})?$/.test(raw)) throw new Error('Проверьте сумму');
  const [whole,part='']=raw.split(/[.,]/);
  return Number(whole)*100+Number(part.padEnd(2,'0'));
}
function rubDisplay(kopecks){return (kopecks/100).toLocaleString('ru-RU',{minimumFractionDigits:kopecks%100?'2':0,maximumFractionDigits:2});}
function profileEmoji(login){
  const icons=['🙂','🌿','⭐️','💳','🦊','🐻','🎯','🌙'];
  let h=0; for(let i=0;i<login.length;i++) h=(h*31+login.charCodeAt(i))>>>0;
  return icons[h%icons.length];
}
function renderAccountIdentity(){
  const login=(deviceLogin||'').trim();
  if($('accountAvatar')) $('accountAvatar').textContent=login?profileEmoji(login):'👤';
  if($('accountDisplayName')) $('accountDisplayName').textContent='Мой кошелёк';
  if($('settingsUser')) $('settingsUser').textContent=login?`@${login}`:'Гость';
}
function syncThemeControls(){
  const theme=document.documentElement.dataset.theme||'light';
  if($('settingsTheme')) $('settingsTheme').value=theme;
  if($('themeLight')) $('themeLight').setAttribute('aria-pressed', String(theme==='light'));
  if($('themeDark')) $('themeDark').setAttribute('aria-pressed', String(theme==='dark'));
}
function walletBank(card){
  const key=(card?.bankId||card?.name||card?.cardName||'').toString().toLowerCase().replace(/[^a-zа-я0-9]/gi,'');
  return banks.find(bank=>bank.id===card?.bankId || bank.name===(card?.name||card?.cardName) || bank.name.toLowerCase().replace(/[^a-zа-я0-9]/gi,'')===key) || null;
}
function walletBankLogo(card){
  if(card?.demo && typeof card.cardId==='string' && card.cardId.startsWith('demo-')){
    const hit=banks.find(bank=>bank.id===card.cardId.slice(5));
    if(hit?.logo) return hit.logo;
  }
  const bank=walletBank(card);
  return bank?.logo || null;
}
window.walletBankLogo=walletBankLogo;
function carouselCardLogoMarkup(card){
  const logo=walletBankLogo(card);
  const letter=escapeHtml((card?.cardName||card?.name||'?').charAt(0));
  if(logo) return `<span class="carousel-card-logo has-img" aria-hidden="true"><img src="${escapeHtml(logo)}" alt="" width="31" height="31" decoding="async" loading="lazy"></span>`;
  return `<span class="carousel-card-logo" aria-hidden="true">${letter}</span>`;
}
window.carouselCardLogoMarkup=carouselCardLogoMarkup;
function walletCardCaption(card){
  const rules=card.rules||[];
  if(!rules.length) return 'Добавить условия';
  const best=rules.reduce((a,b)=>b.rateBps>a.rateBps?b:a);
  return `${best.label||categories[best.categoryId]||best.categoryId} ${formatRate(best.rateBps)}%`;
}
function ruleLine(rule){return `${rule.label||categories[rule.categoryId]||rule.categoryId} · ${formatRate(rule.rateBps)}%`;}
function renderWalletCardDetails(card){
  const host=$('carouselSummary'); if(!host) return; host.replaceChildren();
  const title=document.createElement('p');
  title.className='carousel-bank-title';
  title.textContent=card.cardName||card.name;
  host.append(title);
  if(card.demo){
    host.append(Object.assign(document.createElement('p'),{className:'carousel-demo-note',textContent:'Ставки демонстрационные'}));
  }
  const rules=card.rules||[];
  const list=$('carouselCategories');
  if(list){
    list.replaceChildren();
    list.hidden=!rules.length;
    rules.forEach(rule=>{
      const li=document.createElement('li');
      const catId=rule.categoryId||'other';
      const name=rule.label||categories[catId]||catId;
      const main=document.createElement('span'); main.className='carousel-cat-main';
      const mark=document.createElement('span'); mark.className='carousel-cat-mark'; mark.append(categoryIconSvg(catId));
      const nameEl=document.createElement('span'); nameEl.className='carousel-cat-name'; nameEl.textContent=name;
      main.append(mark, nameEl);
      li.append(main, Object.assign(document.createElement('span'),{className:'carousel-cat-rate',textContent:`${formatRate(rule.rateBps)}%`}));
      list.append(li);
    });
  }
  const hint=$('carouselEmptyHint');
  if(hint) hint.hidden=!!rules.length || document.documentElement.dataset.demo==='cards';
  const cashback=$('addCashbackBtn');
  if(cashback){
    cashback.hidden=false;
    cashback.textContent=rules.length?'Изменить условия кэшбэка':'Добавить условия кэшбэка';
    cashback.disabled=!card;
  }
  if($('cardActions')) $('cardActions').hidden=!card;
  if($('cardMenu')){$('cardMenu').hidden=true;}
  if($('cardMenuBtn')) $('cardMenuBtn').setAttribute('aria-expanded','false');
  if($('makeUsualBtn')) $('makeUsualBtn').disabled=!card;
  if($('deleteActiveBtn')) $('deleteActiveBtn').disabled=!card;
}
function renderWalletCashback(){/* overview stays in the inline toggle */}
function activeCard(){
  const cards=carouselPos.all; if(!cards.length) return null;
  return cards[((Math.round(carouselPos.value)%cards.length)+cards.length)%cards.length];
}
function applyWalletRoute(route){
  if(route==='buy'){showBuy(); markRoute('buy'); $('buyTitle').focus({preventScroll:true}); return;}
  $('hero').hidden=route!=='home'; $('content').hidden=route==='home';
  $('buyPanel').hidden=true; $('cardsPanel').hidden=route!=='cards'; $('historyPanel').hidden=route!=='history';
  if($('accountPanel')) $('accountPanel').hidden=route!=='account';
  if(route==='home' || route==='account' || route==='history' || route==='buy'){
    const catalog=$('catalogDialog'); if(catalog && !catalog.hidden) catalog.hidden=true;
    const plan=$('planDialog'); if(plan && !plan.hidden) plan.hidden=true;
  }
  markRoute(route);
  if(route==='cards' && $('cardCarousel').clientWidth){carouselPos.slotPx=carouselSlot(); applyCarouselTransforms();}
  if(route==='history') renderHistory();
  if(route==='account') openSettings();
  if(route==='home') renderHomeMonthCashback();
  const focus={home:'homeTitle',cards:'cards-title',history:'historyTitle',account:'accountTitle'}[route];
  if(focus && $(focus)) $(focus).focus({preventScroll:true});
}
function walletRoute(route, replace){
  const safe=shellRoutes.includes(route)?route:'home';
  const hash=safe==='home'?'#home':'#'+safe;
  const state={advisor:true, route:safe};
  if(location.hash!==hash) history[replace?'replaceState':'pushState'](state,'',hash);
  else history.replaceState(state,'',hash);
  applyWalletRoute(safe);
}
function walletBack(){
  if(typeof window.walletCashbackBack==='function' && window.walletCashbackBack()) return;
  const hash=(location.hash||'#home').replace(/^#/,'');
  const route=shellRoutes.includes(hash)?hash:'home';
  if(route==='home') return;
  if(window.history.length>1) history.back();
  else walletRoute('home', true);
}
function markRoute(route){document.querySelectorAll('[data-route]').forEach(button=>{if(button.dataset.route===route)button.setAttribute('aria-current','page');else button.removeAttribute('aria-current');});}
function entryRoute(forceHome){
  if(forceHome) return 'home';
  const hash=(location.hash||'').replace(/^#/,'');
  if(!hash || hash==='home') return 'home';
  return shellRoutes.includes(hash)?hash:'home';
}
function syncWalletRoute(forceHome){ walletRoute(entryRoute(forceHome), true); }
async function loadWalletData(){
  const statusRow=$('walletStatus')?.closest('.wallet-status');
  if(statusRow) statusRow.classList.remove('is-error');
  $('walletStatus').textContent=''; $('retryWallet').hidden=true;
  try{
    [catalog, saved, manual]=await Promise.all([
      apiPart('Справочник карт','/api/cards'),
      apiPart('Список в кошельке','/api/me/cards'),
      apiPart('Ваши карты','/api/me/manual-cards'),
    ]);
    await fillMeta(); renderCards(); writeDevice();
    if(!$('hero').hidden) renderHomeMonthCashback();
    if($('accountPanel') && !$('accountPanel').hidden) openSettings();
  }catch(error){
    if(statusRow) statusRow.classList.add('is-error');
    $('walletStatus').textContent=error.message||'Не удалось загрузить кошелёк.';
    $('retryWallet').hidden=false;
    if(!carouselPos.all.length) $('carouselTrack').innerHTML='<div class="empty"><strong>Не удалось загрузить кошелёк</strong><span>'+(error.message||'Повторите загрузку.')+'</span></div>';
  }
}
function expireSession(){
  deviceLogin=null;
  sessionStorage.removeItem('advisor-auth-home');
  if(typeof manual!=='undefined') manual=[];
  else if(window.manual) window.manual=[];
  if(typeof saved!=='undefined') saved=[];
  else if(window.saved) window.saved=[];
  const pos=typeof carouselPos!=='undefined'?carouselPos:window.carouselPos;
  if(pos){pos.all=[]; cancelAnimationFrame(pos.raf);}
  for(const id of ['addDialog','deleteDialog','planDialog','catalogDialog']) {const node=$(id); if(node) node.hidden=true;}
  if($('accountPanel')) $('accountPanel').hidden=true;
  $('hero').hidden=false; $('content').hidden=true;
  $('buyPanel').hidden=true; $('cardsPanel').hidden=true; $('historyPanel').hidden=true;
  if(location.hash) history.replaceState(null,'',location.pathname+location.search);
  $('authScreen').hidden=true;
  $('appScreen').hidden=true;
  $('welcomeScreen').hidden=false;
  if($('authPassword')) $('authPassword').value='';
  if($('sessionGate')) $('sessionGate').hidden=true;
}
window.expireSession=expireSession;
function openDialog(dialog, focus, source){walletReturn=source||document.activeElement; dialog.hidden=false; focus?.focus();}
function closeDialog(dialog){dialog.hidden=true; if(walletReturn?.isConnected) walletReturn.focus();}
function trap(dialog){if(!dialog) return; dialog.addEventListener('keydown',event=>{
  if(event.key==='Escape'){event.preventDefault(); dialog.querySelector('.close, .cancel')?.click(); return;}
  if(event.key!=='Tab') return;
  const items=[...dialog.querySelectorAll('button,input,select,a')].filter(item=>!item.disabled && !item.closest('[hidden]') && item.getClientRects().length);
  if(!items.length) return;
  if(event.shiftKey && document.activeElement===items[0]){event.preventDefault(); items.at(-1).focus();}
  else if(!event.shiftKey && document.activeElement===items.at(-1)){event.preventDefault(); items[0].focus();}
});}
function openAddCard(source){
  if(document.documentElement.dataset.demo==='cards') return;
  addReturn=walletReturn=source||document.activeElement;
  $('addRoutes').hidden=false; $('addCardForm').hidden=true; $('addTitle').textContent='Добавить карту';
  $('addStatus').textContent=''; $('retryAdd').hidden=true; $('addDialog').hidden=false; $('addRouteBank').focus();
}
function showBankForm(){
  $('addRoutes').hidden=true; $('addCardForm').hidden=false; $('addCardForm').dataset.mode='bank'; $('addSource').value='bank';
  $('bankSearch').value=''; $('bankSearch').hidden=false; $('searchLabel').hidden=false;
  if($('addSelectedBank')) {$('addSelectedBank').hidden=true; $('addSelectedBank').textContent='';}
  if($('openCatalogSource')) $('openCatalogSource').hidden=false;
  fillAddChoices(); $('bankSearch').focus();
}
function showCatalogForm(){
  $('addRoutes').hidden=true; $('addCardForm').hidden=false; $('addCardForm').dataset.mode='catalog'; $('addSource').value='catalog';
  $('bankSearch').value=''; $('bankSearch').hidden=true; $('searchLabel').hidden=true;
  if($('addSelectedBank')) {$('addSelectedBank').hidden=true; $('addSelectedBank').textContent='';}
  if($('openCatalogSource')) $('openCatalogSource').hidden=true;
  fillAddChoices(); $('newBank').focus();
}
function fillAddChoices(){
  const select=$('newBank'), catalogMode=$('addSource').value==='catalog', query=$('bankSearch').value.trim().toLowerCase();
  const previous=select.value;
  select.replaceChildren();
  const bankItem=bank=>({value:bank.id,label:bank.name,logo:bank.logo||null});
  const items=catalogMode?catalog.map(card=>({value:card.cardId,label:`${card.cardName} · ${card.bankName}`,logo:null}))
    :banks.filter(bank=>!query || bank.name.toLowerCase().includes(query) || bank.id.includes(query)).map(bankItem);
  items.forEach(item=>select.append(new Option(item.label,item.value)));
  if(previous && [...select.options].some(option=>option.value===previous)) select.value=previous;
  else if(items.length===1) select.value=items[0].value;
  const box=$('bankSuggestions'); box.replaceChildren(); box.className='suggest bank-list'; bankSuggest=-1;
  if(catalogMode){box.hidden=true; $('bankSearch').setAttribute('aria-expanded','false');}
  else {
    box.hidden=false; $('bankSearch').setAttribute('aria-expanded','true');
    const list=query?items:banks.map(bankItem);
    list.forEach((item,index)=>{
      const option=document.createElement('button'); option.type='button'; option.className='bank-row'; option.setAttribute('role','option');
      if(item.logo){const logo=document.createElement('img'); logo.className='bank-row-logo'; logo.src=item.logo; logo.alt=''; logo.width=32; logo.height=32; logo.decoding='async'; logo.loading='lazy'; logo.onerror=()=>logo.remove(); option.append(logo);}
      const label=document.createElement('span'); label.className='bank-row-name'; label.textContent=item.label; option.append(label);
      option.onmousedown=event=>event.preventDefault();
      option.onclick=()=>{
        $('newBank').value=item.value; $('bankSearch').value=item.label;
        if($('addSelectedBank')){$('addSelectedBank').hidden=false; $('addSelectedBank').textContent='Выбран: '+item.label;}
        box.hidden=true; $('bankSearch').setAttribute('aria-expanded','false'); $('addStatus').textContent=''; $('saveNewCard').disabled=false;
      };
      box.append(option); if(index===0) option.setAttribute('aria-selected','true');
    });
    if(!list.length){const empty=document.createElement('p'); empty.className='cb-note'; empty.textContent='Ничего не найдено'; box.append(empty);}
  }
  $('addStatus').textContent=items.length?'':catalogMode?'В каталоге нет карт.':'Ничего не найдено';
  $('saveNewCard').disabled=!items.length || !select.value;
}
function monthTitle(month){
  if(!month) return '';
  const name=new Intl.DateTimeFormat('ru-RU',{month:'long', year:'numeric', timeZone:'UTC'}).format(new Date(month+'-01T12:00:00Z')).replace(/\s*г\.?$/,'');
  return name.charAt(0).toUpperCase()+name.slice(1);
}
function syncHistoryMonthText(){
  const input=$('historyMonth'), text=$('historyMonthText');
  if(!input||!text) return;
  text.textContent=input.value?monthTitle(input.value):'Текущий месяц';
}
async function renderHomeMonthCashback(){
  const section=$('homeMonthCashback'), host=$('homeMonthCashbackBody');
  if(!section||!host) return;
  if(document.documentElement.dataset.demo==='cards'||$('appScreen').hidden){
    section.hidden=true;
    return;
  }
  section.hidden=false;
  host.className='month-cashback is-loading';
  host.textContent='Считаем кэшбэк…';
  try{
    const data=await api('/api/me/stats');
    host.className='month-cashback';
    host.replaceChildren();
    if(!data.count){
      const empty=document.createElement('p');
      empty.className='month-cashback-meta';
      empty.textContent='Покупок в этом месяце пока нет. Запишите покупку после совета.';
      host.append(empty);
      const journal=document.createElement('button');
      journal.type='button'; journal.className='month-cashback-journal'; journal.textContent='Покупки за месяц';
      journal.onclick=()=>walletRoute('history');
      host.append(journal);
      return;
    }
    const grid=document.createElement('div'); grid.className='month-cashback-grid';
    const actual=document.createElement('div'); actual.className='month-cashback-actual';
    const kicker=document.createElement('span'); kicker.className='month-cashback-kicker'; kicker.textContent='Получено';
    actual.append(kicker);
    if(data.actualCashbackKopecks==null){
      const pending=document.createElement('span'); pending.className='month-cashback-pending'; pending.textContent='—';
      actual.append(pending);
    }else{
      const value=document.createElement('strong'); value.className='money'; value.textContent=money(data.actualCashbackKopecks);
      actual.append(value);
    }
  const side=document.createElement('div'); side.className='month-cashback-side';
    const calc=document.createElement('p');
    calc.append(Object.assign(document.createElement('span'),{textContent:'По расчёту'}),
      Object.assign(document.createElement('strong'),{className:'money',textContent:money(data.calculatedKopecks)}));
    const missed=document.createElement('p');
    missed.append(Object.assign(document.createElement('span'),{textContent:'Можно было ещё'}),
      Object.assign(document.createElement('strong'),{className:'money',textContent:money(Math.max(0,data.missedKopecks||0))}));
    side.append(calc, missed);
    grid.append(actual, side);
    host.append(grid);
    const meta=document.createElement('p'); meta.className='month-cashback-meta';
    if(!data.actualCashbackCount) meta.textContent='Нет подтверждённых начислений';
    else meta.textContent=`Подтверждено по ${data.actualCashbackCount} из ${purchaseCount(data.count)}`;
    host.append(meta);
    if(Array.isArray(data.cards)&&data.cards.length){
      const cards=document.createElement('details'); cards.className='month-cashback-cards';
      const summary=document.createElement('summary'); summary.textContent='По картам'; cards.append(summary);
      const list=document.createElement('ul');
      data.cards.forEach(card=>{
        const li=document.createElement('li');
        const name=document.createElement('span'); name.className='name'; name.textContent=card.name||card.cardId;
        const vals=document.createElement('span'); vals.className='vals';
        const actualText=card.actualCashbackCount
          ?`${money(card.actualCashbackKopecks)} · ${card.actualCashbackCount}`
          :`${money(card.cashbackKopecks)} расчёт`;
        vals.textContent=actualText;
        li.append(name, vals); list.append(li);
      });
      cards.append(list); host.append(cards);
    }
    const journal=document.createElement('button');
    journal.type='button'; journal.className='month-cashback-journal'; journal.textContent='Покупки за месяц';
    journal.onclick=()=>walletRoute('history');
    host.append(journal);
  }catch(error){
    host.className='month-cashback is-error'; host.replaceChildren();
    const message=document.createElement('p'); message.textContent=error.message||'Не удалось загрузить сводку.';
    const retry=document.createElement('button'); retry.type='button'; retry.textContent='Повторить';
    retry.onclick=()=>renderHomeMonthCashback();
    host.append(message, retry);
  }
}
window.renderHomeMonthCashback=renderHomeMonthCashback;
function buildActualCashbackEditor(item){
  const wrap=document.createElement('div'); wrap.className='journal-actual';
  const title=document.createElement('h4'); title.textContent='Фактический кэшбэк';
  const label=document.createElement('label');
  label.textContent='Сколько начислил банк, ₽';
  const input=document.createElement('input');
  input.inputMode='decimal'; input.autocomplete='off';
  input.placeholder='Например, 48';
  if(item.actualCashbackKopecks!=null) input.value=rubDisplay(item.actualCashbackKopecks);
  label.append(input);
  const note=document.createElement('p'); note.className='journal-actual-note';
  const syncNote=()=>{
    if(item.actualCashbackKopecks==null) note.textContent='Отметка не подтверждена';
    else if(item.actualCashbackKopecks===0) note.textContent='Подтверждённый ноль';
    else note.textContent=`Сохранено: ${money(item.actualCashbackKopecks)}`;
  };
  syncNote();
  const error=document.createElement('p'); error.className='journal-actual-error'; error.hidden=true;
  const actions=document.createElement('div'); actions.className='journal-actual-actions';
  const save=document.createElement('button'); save.type='button'; save.className='primary'; save.textContent='Сохранить';
  const clear=document.createElement('button'); clear.type='button'; clear.textContent='Удалить отметку';
  const busy=flag=>{save.disabled=flag; clear.disabled=flag; input.readOnly=flag;};
  save.onclick=async()=>{
    error.hidden=true;
    let amount;
    try{amount=rubFromField(input.value);}catch(e){error.textContent=e.message; error.hidden=false; return;}
    busy(true);
    try{
      await api(`/api/me/purchases/${item.id}/cashback`,{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({amountKopecks:amount})});
      item.actualCashbackKopecks=amount; syncNote(); toast('Начисление сохранено');
      renderHomeMonthCashback();
    }catch(e){error.textContent=e.message||'Не удалось сохранить'; error.hidden=false;}
    finally{busy(false);}
  };
  clear.onclick=async()=>{
    error.hidden=true; busy(true);
    try{
      await api(`/api/me/purchases/${item.id}/cashback`,{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({amountKopecks:null})});
      item.actualCashbackKopecks=null; input.value=''; syncNote(); toast('Отметка удалена');
      renderHomeMonthCashback();
    }catch(e){error.textContent=e.message||'Не удалось удалить'; error.hidden=false;}
    finally{busy(false);}
  };
  actions.append(save, clear);
  wrap.append(title, label, note, actions, error);
  wrap.addEventListener('click', event=>event.stopPropagation());
  return wrap;
}
function dayTitle(iso){
  if(!iso) return 'Без даты';
  return new Intl.DateTimeFormat('ru-RU',{day:'numeric', month:'long', timeZone:'UTC'}).format(new Date(iso.slice(0,10)+'T12:00:00Z'));
}
async function renderHistory(){
  const host=$('historyBody'); host.className='journal is-loading'; host.textContent='Загружаем историю…';
  try{
    const query=historyMonth?`?month=${encodeURIComponent(historyMonth)}`:'';
    const data=await api('/api/me/stats'+query); host.className='journal'; host.replaceChildren();
    if($('historyMonth') && data.month) $('historyMonth').value=data.month;
    historyMonth=data.month;
    const summary=document.createElement('section'); summary.className='journal-summary';
    syncHistoryMonthText();
    const total=document.createElement('p'); total.className='journal-total';
    const strong=document.createElement('strong'); strong.className='money'; strong.textContent=money(data.calculatedKopecks);
    const caption=document.createElement('span'); caption.className='sr-only'; caption.textContent='Расчётный кэшбэк за месяц';
    total.append(strong, caption);
    summary.append(total);
    const ask=document.createElement('button'); ask.type='button'; ask.className='secondary-action'; ask.textContent='Разобрать месяц';
    ask.onclick=async()=>{ask.disabled=true; ask.textContent='Разбираем…'; try{const reply=await api('/api/me/stats/comment',{method:'POST'},45000); const comment=document.createElement('p'); comment.textContent=reply.comment; summary.append(comment);}catch(error){toast(error.message);}finally{ask.disabled=false; ask.textContent='Разобрать месяц';}};
    summary.append(ask); host.append(summary);
    if(!data.purchases.length){host.classList.add('is-empty'); const empty=document.createElement('p'); empty.textContent='Покупок в этом месяце нет. Запишите покупку после совета.'; host.append(empty); return;}
    const groups=new Map();
    data.purchases.forEach(item=>{const key=(item.date||'').slice(0,10); if(!groups.has(key)) groups.set(key,[]); groups.get(key).push(item);});
    groups.forEach((items,key)=>{
      const day=document.createElement('h3'); day.className='journal-day'; day.textContent=dayTitle(key); host.append(day);
      const list=document.createElement('div'); list.className='journal-list';
      items.forEach(item=>{
        const gap=(item.recommendedKopecks??0)-(item.chosenKopecks??0);
        const row=document.createElement('button'); row.type='button'; row.className='journal-row'; row.setAttribute('aria-expanded','false');
        const main=document.createElement('span'); main.className='journal-main';
        const title=document.createElement('span'); title.className='journal-title'; title.textContent=categories[item.categoryId]||item.categoryId||'Покупка';
        const bank=document.createElement('span'); bank.className='journal-bank'; bank.textContent=item.chosenName||'Карта';
        main.append(title, bank);
        if(gap>0){const extra=document.createElement('span'); extra.className='journal-gap'; extra.textContent=`Можно было получить ещё ${money(gap)}`; main.append(extra);}
        const moneyCol=document.createElement('span'); moneyCol.className='journal-money';
        const amount=document.createElement('strong'); amount.className='money'; amount.textContent=money(item.amountKopecks);
        const cash=document.createElement('span'); cash.className='journal-cash'; cash.textContent=item.chosenKopecks==null?'':`+${money(item.chosenKopecks)}`;
        moneyCol.append(amount, cash); row.append(main, moneyCol);
        const detail=document.createElement('div'); detail.className='journal-detail'; detail.hidden=true;
        const chosen=document.createElement('p'); chosen.textContent=`Выбранная карта: ${item.chosenName||'—'}${item.chosenKopecks==null?'':`, ${money(item.chosenKopecks)}`}`;
        const best=document.createElement('p'); best.textContent=`Лучшая по расчёту: ${item.recommendedName||'—'}${item.recommendedKopecks==null?'':`, ${money(item.recommendedKopecks)}`}`;
        const diff=document.createElement('p'); diff.textContent=`Разница: ${item.recommendedKopecks==null||item.chosenKopecks==null?'—':money(gap)}`;
        detail.append(chosen, best, diff);
        if(item.id!=null) detail.append(buildActualCashbackEditor(item));
        row.onclick=()=>{detail.hidden=!detail.hidden; row.setAttribute('aria-expanded', String(!detail.hidden));};
        list.append(row, detail);
      });
      host.append(list);
    });
  }catch(error){
    host.className='journal is-error'; host.replaceChildren();
    const message=document.createElement('p'); message.textContent=error.message||'Не удалось загрузить историю.';
    const retry=document.createElement('button'); retry.type='button'; retry.textContent='Повторить загрузку'; retry.onclick=()=>renderHistory();
    host.append(message, retry);
  }
}
async function renderAccount(){
  const host=$('accountStats'); if(!host) return;
  renderAccountIdentity();
  host.className=''; host.setAttribute('aria-busy','true'); host.textContent='Загружаем статистику…';
  try{
    const data=await api('/api/me/stats'); host.setAttribute('aria-busy','false'); host.replaceChildren();
    const primary=document.createElement('p'); primary.className='stat-primary';
    const label=document.createElement('span'); label.textContent='Расчётный кэшбэк';
    const value=document.createElement('strong'); value.className='money'; value.textContent=money(data.calculatedKopecks);
    primary.append(label, value);     host.append(primary);
    if(Array.isArray(data.cards)&&data.cards.length){
      const palette=['#ffdd2d','#285a3a','#5d8fc9','#a22624','#8d7ecb','#79ac66','#cbb8ed'];
      const total=data.cards.reduce((sum,c)=>sum+c.cashbackKopecks,0)||1;
      let cursor=0; const stops=[];
      data.cards.forEach((card,i)=>{
        const share=(card.cashbackKopecks/total)*100; const color=palette[i%palette.length];
        stops.push(`${color} ${cursor}% ${cursor+share}%`); cursor+=share;
      });
      const donut=document.createElement('div'); donut.className='profile-donut';
      const ring=document.createElement('div'); ring.className='profile-donut-ring';
      ring.style.background=`conic-gradient(${stops.join(',')})`;
      ring.setAttribute('role','img'); ring.setAttribute('aria-label','Доля кэшбэка по картам за месяц');
      const legend=document.createElement('ul'); legend.className='profile-legend';
      data.cards.forEach((card,i)=>{
        const li=document.createElement('li');
        const sw=document.createElement('span'); sw.className='swatch'; sw.style.background=palette[i%palette.length];
        const name=document.createElement('span'); name.className='name'; name.textContent=card.name||card.cardId;
        const val=document.createElement('span'); val.className='val money'; val.textContent=money(card.cashbackKopecks);
        li.append(sw,name,val); legend.append(li);
      });
      donut.append(ring,legend); host.append(donut);
    }
    const secondary=document.createElement('div'); secondary.className='stat-secondary';
    const count=document.createElement('p'); const countLabel=document.createElement('span'); countLabel.textContent='Покупок записано';
    const countValue=document.createElement('strong'); countValue.textContent=String(data.count); count.append(countLabel, countValue); secondary.append(count);
    if(data.missedKopecks>0){const missed=document.createElement('p'); const missedLabel=document.createElement('span'); missedLabel.textContent='Можно было получить ещё'; const missedValue=document.createElement('strong'); missedValue.className='money'; missedValue.textContent=money(data.missedKopecks); missed.append(missedLabel, missedValue); secondary.append(missed);}
    host.append(secondary);
    if(!data.count){const empty=document.createElement('p'); empty.className='journal-meta'; empty.textContent='За этот месяц покупок нет.'; host.append(empty);}
  }catch(error){
    host.setAttribute('aria-busy','false'); host.className='account-error'; host.replaceChildren();
    const message=document.createElement('p'); message.textContent=error.message||'Не удалось загрузить статистику.';
    const retry=document.createElement('button'); retry.type='button'; retry.textContent='Повторить загрузку'; retry.onclick=()=>renderAccount();
    host.append(message, retry);
  }
}
document.querySelectorAll('[data-route]').forEach(button=>button.addEventListener('click',()=>walletRoute(button.dataset.route)));
$('openBuy').addEventListener('click',()=>{
  if(!carouselPos.all.length){ walletRoute('cards', true); openAddCard($('openCatalog')); return; }
  walletRoute('buy');
});
if($('authGuest')) $('authGuest').addEventListener('click',async()=>{
  const button=$('authGuest');
  button.disabled=true; $('authError').textContent='';
  try{
    const user=await api('/api/auth/guest',{
      method:'POST',
      headers:{'Content-Type':'application/json'},
      body:'{}',
    });
    deviceLogin=user.login; localStorage.setItem('advisor-login',user.login);
    sessionStorage.setItem('advisor-auth-home','1'); await checkAuth();
  }catch(error){
    const text=error.status===404
      ?'Вход как гость недоступен — перезапустите сервер с последней версией.'
      :error.message||'Не удалось войти как гость';
    $('authError').textContent=text;
    button.disabled=false;
  }
});
$('openCards').addEventListener('click',()=>walletRoute('cards'));
$('emptyAdd').addEventListener('click',()=>{walletRoute('cards',true); openAddCard($('openCatalog'));});
$('openCatalog').addEventListener('click',event=>openAddCard(event.currentTarget));
$('buyBack').addEventListener('click',()=>walletBack());
$('cardsBack').addEventListener('click',()=>walletBack());
$('historyBack').addEventListener('click',()=>walletBack());
$('accountBack').addEventListener('click',()=>walletBack());
$('showStatsBtn').addEventListener('click',()=>walletRoute('history'));
$('retryWallet').addEventListener('click',()=>load());
if($('historyMonth')){$('historyMonth').addEventListener('change',()=>{historyMonth=$('historyMonth').value||null; syncHistoryMonthText(); if(!$('historyPanel').hidden) renderHistory();}); syncHistoryMonthText();}
window.addEventListener('popstate',()=>{
  if($('appScreen').hidden) return;
  if(typeof window.walletCashbackBack==='function' && !$('catalogDialog')?.hidden){ if(window.walletCashbackBack()) return; }
  for(const id of ['addDialog','deleteDialog','planDialog']) {const node=$(id); if(node) node.hidden=true;}
  const route=(location.hash||'#home').slice(1); applyWalletRoute(shellRoutes.includes(route)?route:'home');
});
$('passwordToggle').addEventListener('click',()=>{
  const input=$('authPassword'), btn=$('passwordToggle');
  const next=input.type==='password'?'text':'password';
  input.type=next;
  const shown=next==='text';
  btn.setAttribute('aria-pressed', String(shown));
  btn.setAttribute('aria-label', shown?'Скрыть пароль':'Показать пароль');
  const eye=btn.querySelector('.icon-eye'), off=btn.querySelector('.icon-eye-off');
  if(eye) eye.hidden=shown;
  if(off) off.hidden=!shown;
});
$('addSource').addEventListener('change',fillAddChoices);
if($('openCatalogSource')) $('openCatalogSource').addEventListener('click',showCatalogForm);
$('bankSearch').addEventListener('input',()=>{bankSuggest=-1; fillAddChoices();});
$('bankSearch').addEventListener('keydown',event=>{
  const options=[...$('bankSuggestions').querySelectorAll('[role=option]')]; if(!options.length || $('bankSuggestions').hidden) return;
  if(event.key==='ArrowDown' || event.key==='ArrowUp'){event.preventDefault(); bankSuggest=event.key==='ArrowDown'?Math.min(options.length-1, bankSuggest+1):Math.max(0, bankSuggest-1); options.forEach((option,index)=>option.setAttribute('aria-selected', String(index===bankSuggest))); options[bankSuggest].scrollIntoView({block:'nearest'});}
  else if(event.key==='Enter'){event.preventDefault(); options[Math.max(0,bankSuggest)].click();}
  else if(event.key==='Escape'){$('bankSuggestions').hidden=true; $('bankSearch').setAttribute('aria-expanded','false');}
});
$('retryAdd').addEventListener('click',async()=>{try{await fillMeta(); fillAddChoices();}catch(error){$('addStatus').textContent=error.message;}});
async function submitNewCard(event){
  event.preventDefault(); if($('saveNewCard').disabled) return;
  const catalogMode=$('addSource').value==='catalog', id=$('newBank').value, button=$('saveNewCard');
  if(!id){$('addStatus').textContent='Выберите банк из списка.'; return;}
  button.disabled=true; button.textContent='Сохраняем…';
  try{
    if(catalogMode){await api('/api/me/cards/'+encodeURIComponent(id),{method:'PUT'}); walletPreferredCard=id;}
    else{const bank=banks.find(item=>item.id===id); const created=await api('/api/me/manual-cards',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name:bank.name,bankId:bank.id,rules:[]})}); walletPreferredCard=created.cardId;}
    $('addDialog').hidden=true; toast('Карта добавлена'); await load(); walletRoute('cards',true);
    $('addCashbackBtn').focus();
  }catch(error){$('addStatus').textContent=error.message; $('retryAdd').hidden=false;}
  finally{button.textContent='Добавить карту'; button.disabled=$('newBank').options.length===0;}
}
$('closeAdd').addEventListener('click',()=>closeDialog($('addDialog')));
$('addRouteBank').addEventListener('click',showBankForm);
$('addRouteShot').addEventListener('click',()=>{
  const back=addReturn||$('openCatalog');
  $('addDialog').hidden=true;
  if(typeof window.openCashbackDecision==='function') window.openCashbackDecision(back);
  else $('addCashbackBtn').click();
});
if($('cardMenuBtn') && !$('cardMenuBtn').hidden) $('cardMenuBtn').addEventListener('click',()=>{const open=$('cardMenu').hidden; $('cardMenu').hidden=!open; $('cardMenuBtn').setAttribute('aria-expanded', String(open)); if(open) $('addCashbackBtn').focus();});
$('makeUsualBtn').addEventListener('click',async()=>{
  const card=activeCard(); if(!card) return; $('makeUsualBtn').disabled=true;
  try{await api('/api/me/usual-card',{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({cardId:card.cardId})}); toast('Обычная карта сохранена');}
  catch(error){toast(error.message);} finally{$('makeUsualBtn').disabled=false;}
});
$('deleteActiveBtn').addEventListener('click',()=>{
  const card=activeCard(); if(!card) return; deleteTarget=card; walletReturn=$('addCashbackBtn');
  $('deleteTitle').textContent='Удалить карту?'; $('deleteDescription').textContent=`Карта «${card.cardName||card.name}» исчезнет из кошелька вместе с сохранёнными условиями. Покупки в истории останутся.`;
  $('deleteStatus').textContent=''; $('deleteDialog').hidden=false; $('cancelDelete').focus();
});
$('showCashbackBtn').addEventListener('click',()=>$('showCashbackBtn').setAttribute('aria-expanded',String(!$('cashbackView').hidden)));
if($('themeLight')) $('themeLight').addEventListener('click',()=>{applyTheme('light'); syncThemeControls();});
if($('themeDark')) $('themeDark').addEventListener('click',()=>{applyTheme('dark'); syncThemeControls();});
$('logout').addEventListener('click',async()=>{
  if(!window.confirm('Выйти из кошелька на этом устройстве?')) return;
  $('logout').disabled=true; $('settingsStatus').textContent='';
  try{await api('/api/auth/logout',{method:'POST'});}
  catch(error){$('settingsStatus').textContent=error.message;}
  expireSession();
  $('logout').disabled=false;
});
$('cancelDelete').addEventListener('click',()=>closeDialog($('deleteDialog')));
$('confirmDelete').addEventListener('click',async()=>{
  if(!deleteTarget) return; $('confirmDelete').disabled=true; $('confirmDelete').textContent='Удаляем…';
  try{
    const path=deleteTarget.kind==='manual'?`/api/me/manual-cards/${encodeURIComponent(deleteTarget.cardId)}`:`/api/me/cards/${encodeURIComponent(deleteTarget.cardId)}`;
    await api(path,{method:'DELETE'}); $('deleteDialog').hidden=true; toast('Карта удалена'); await load(); $('cards-title').focus();
  }catch(error){$('deleteStatus').textContent=error.message;}
  finally{$('confirmDelete').disabled=false; $('confirmDelete').textContent='Удалить карту';}
});
['addDialog','deleteDialog'].forEach(id=>trap($(id)));
const originalOpenSettings=openSettings;
openSettings=async function(){
  await originalOpenSettings();
  syncThemeControls();
  $('settingsStatus').textContent='';
  renderAccountIdentity();
  await renderAccount();
};
function showSessionGate(message, retry){
  const gate=$('sessionGate'); if(!gate) return;
  gate.hidden=false; $('sessionGateStatus').textContent=message;
  $('sessionGateRetry').hidden=!retry;
  $('welcomeScreen').hidden=true; $('authScreen').hidden=true; $('appScreen').hidden=true;
}
function hideSessionGate(){ if($('sessionGate')) $('sessionGate').hidden=true; }
window.shellCheckAuth=async function(){
  const forceHome=sessionStorage.getItem('advisor-auth-home')==='1';
  sessionStorage.removeItem('advisor-auth-home');
  showSessionGate('Проверяем вход…', false);
  try{
    const user=await api('/api/auth/me');
    hideSessionGate();
    if(user.authenticated){
      $('welcomeScreen').hidden=true; $('authScreen').hidden=true; $('appScreen').hidden=false;
      deviceLogin=user.login; $('authPassword').value='';
      syncWalletRoute(forceHome); await load();
    }else{
      $('welcomeScreen').hidden=false; $('authScreen').hidden=true; $('appScreen').hidden=true;
    }
  }catch(error){
    showSessionGate('Не удалось проверить вход', true);
    $('sessionGateRetry').onclick=()=>window.shellCheckAuth();
  }
};
checkAuth=window.shellCheckAuth;
function applyDemoCount(count){
  const deck=DEMO_DECK.slice(0, count).map(card=>({...card, rules:card.rules.map(rule=>({...rule}))}));
  manual=deck; saved=[]; walletPreferredCard=deck[0]?.cardId||null; carouselPos.value=0; carouselPos.target=0;
  renderCards(); applyWalletRoute('cards');
  document.querySelectorAll('[data-demo-count]').forEach(button=>button.setAttribute('aria-pressed', String(Number(button.dataset.demoCount)===count)));
}
function startDemo(){
  document.documentElement.dataset.demo='cards';
  hideSessionGate();
  $('welcomeScreen').hidden=true; $('authScreen').hidden=true; $('appScreen').hidden=false;
  if($('demoBar')) $('demoBar').hidden=false;
  applyDemoCount(7);
}
document.querySelectorAll('[data-demo-count]').forEach(button=>button.addEventListener('click',()=>applyDemoCount(Number(button.dataset.demoCount))));
if($('demoReset')) $('demoReset').addEventListener('click',()=>applyDemoCount(7));
if(new URLSearchParams(location.search).get('demo')==='cards') startDemo();
else checkAuth();

if ('serviceWorker' in navigator) {
  window.addEventListener('load', () => {
    navigator.serviceWorker.register('/sw.js', { scope: '/' }).catch(() => {});
  });
}
