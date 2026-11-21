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
function walletCount(n){return n===1?'1 карта':n>1&&n<5?`${n} карты`:`${n} карт`;}
function purchaseCount(n){const mod10=n%10, mod100=n%100; const word=mod10===1&&mod100!==11?'покупка':mod10>=2&&mod10<=4&&(mod100<12||mod100>14)?'покупки':'покупок'; return `${n} ${word}`;}
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
      const name=rule.label||categories[rule.categoryId]||rule.categoryId;
      li.append(Object.assign(document.createElement('span'),{className:'carousel-cat-name',textContent:name}));
      li.append(Object.assign(document.createElement('span'),{className:'carousel-cat-rate',textContent:`${formatRate(rule.rateBps)}%`}));
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
  if(route==='home') renderHomeCashback();
  if(route==='history') renderHistory();
  if(route==='account') openSettings();
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
  $('walletStatus').textContent=''; $('retryWallet').hidden=true;
  try{
    [catalog, saved, manual]=await Promise.all([api('/api/cards'), api('/api/me/cards'), api('/api/me/manual-cards')]);
    await fillMeta(); renderCards(); writeDevice();
    if($('accountPanel') && !$('accountPanel').hidden) openSettings();
  }catch(error){
    $('walletStatus').textContent=error.message; $('retryWallet').hidden=false;
    if(!carouselPos.all.length) $('carouselTrack').innerHTML='<div class="empty"><strong>Не удалось загрузить кошелёк</strong><span>Повторите загрузку.</span></div>';
  }
}
function expireSession(){deviceLogin=null; purchaseReminders.reset(); $('appScreen').hidden=true; $('authScreen').hidden=false; $('welcomeScreen').hidden=true; showRemembered();}
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
  const items=catalogMode?catalog.map(card=>({value:card.cardId,label:`${card.cardName} · ${card.bankName}`}))
    :banks.filter(bank=>!query || bank.name.toLowerCase().includes(query) || bank.id.includes(query)).map(bank=>({value:bank.id,label:bank.name}));
  items.forEach(item=>select.append(new Option(item.label,item.value)));
  if(previous && [...select.options].some(option=>option.value===previous)) select.value=previous;
  else if(items.length===1) select.value=items[0].value;
  const box=$('bankSuggestions'); box.replaceChildren(); box.className='suggest bank-list'; bankSuggest=-1;
  if(catalogMode){box.hidden=true; $('bankSearch').setAttribute('aria-expanded','false');}
  else {
    box.hidden=false; $('bankSearch').setAttribute('aria-expanded','true');
    const list=query?items:banks.map(bank=>({value:bank.id,label:bank.name}));
    list.forEach((item,index)=>{
      const option=document.createElement('button'); option.type='button'; option.className='bank-row'; option.setAttribute('role','option');
      option.textContent=item.label; option.onmousedown=event=>event.preventDefault();
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
function dayTitle(iso){
  if(!iso) return 'Без даты';
  return new Intl.DateTimeFormat('ru-RU',{day:'numeric', month:'long', timeZone:'UTC'}).format(new Date(iso.slice(0,10)+'T12:00:00Z'));
}
let homeCashbackRequest = 0, journalRequest = 0;

function cashbackText(tag, text, className = ''){
  return Object.assign(document.createElement(tag), {textContent: text, className});
}

function cashbackButton(label, action, className = 'secondary-action'){
  return Object.assign(cashbackText('button', label, className), {type: 'button', onclick: action});
}

function cashbackMetric(label, value){
  const metric = document.createElement('p');
  metric.append(cashbackText('span', label), cashbackText('strong', value, 'money'));
  return metric;
}

async function renderHomeCashback(){
  const host = $('homeCashback');
  const ticket = ++homeCashbackRequest;
  host.setAttribute('aria-busy', 'true');
  host.replaceChildren(cashbackText('p', 'Загружаем сводку…', 'journal-meta'));
  try {
    const data = await api('/api/me/stats');
    if (ticket !== homeCashbackRequest) return;
    host.replaceChildren(cashbackText('p', monthTitle(data.month), 'journal-month'));
    if (!data.count){
      host.append(cashbackText('p', 'За этот месяц покупок пока нет.', 'journal-meta'));
      return;
    }
    const grid = document.createElement('div');
    grid.className = 'month-cashback-grid';
    const actual = document.createElement('div');
    actual.className = 'month-cashback-actual';
    actual.append(cashbackText('span', 'Получено', 'month-cashback-kicker'));
    actual.append(data.actualCashbackKopecks == null
      ? cashbackText('span', '—', 'month-cashback-pending')
      : cashbackText('strong', money(data.actualCashbackKopecks), 'money'));
    const estimates = document.createElement('div');
    estimates.className = 'month-cashback-side';
    estimates.append(cashbackMetric('По расчёту', money(data.calculatedKopecks)),
      cashbackMetric('Могли получить ещё', money(data.missedKopecks)));
    grid.append(actual, estimates);
    host.append(grid, cashbackText('p', data.actualCashbackCount
      ? `Подтверждено по ${data.actualCashbackCount} из ${data.count} записанных покупок`
      : 'Нет подтверждённых начислений', 'month-cashback-meta'));
    const missing = data.purchases?.filter(purchase => purchase.estimateAvailable === false).length || 0;
    if (missing) host.append(cashbackText('p', `Покупок без оценки кэшбэка: ${missing}`, 'month-cashback-meta'));
    if (data.cards?.length){
      const breakdown = document.createElement('details');
      breakdown.className = 'month-cashback-cards';
      breakdown.append(cashbackText('summary', 'По картам'));
      const list = document.createElement('ul');
      for (const card of data.cards){
        const row = document.createElement('li');
        const actual = card.actualCashbackKopecks == null
          ? 'Начисления не подтверждены' : 'Получили ' + money(card.actualCashbackKopecks);
        const values = document.createElement('span');
        values.className = 'vals';
        values.append(cashbackText('span', actual), cashbackText('span', 'По расчёту ' + money(card.cashbackKopecks)));
        row.append(cashbackText('strong', card.name || card.cardId, 'name'), values);
        list.append(row);
      }
      breakdown.append(list);
      host.append(breakdown);
    }
    host.append(cashbackButton('Покупки за месяц', () => {
      historyMonth = data.month;
      walletRoute('history');
    }, 'month-cashback-journal'));
  } catch (error) {
    if (ticket !== homeCashbackRequest) return;
    host.replaceChildren(cashbackText('p', error.message || 'Не удалось загрузить сводку.', 'journal-meta'),
      cashbackButton('Повторить', renderHomeCashback));
  } finally {
    if (ticket === homeCashbackRequest) host.removeAttribute('aria-busy');
  }
}

function actualCashbackForm(item){
  const form = document.createElement('form');
  form.className = 'journal-actual';
  const label = cashbackText('label', 'Сколько начислил банк, ₽');
  const input = document.createElement('input');
  input.inputMode = 'decimal';
  input.autocomplete = 'off';
  input.placeholder = 'Например, 48,50';
  const current = cashbackText('p', '', 'journal-actual-note');
  const status = cashbackText('p', '');
  status.setAttribute('role', 'status');
  status.id = 'cashback-status-' + item.id;
  input.setAttribute('aria-describedby', status.id);
  label.append(input);
  const save = cashbackButton('Сохранить', null, 'primary');
  save.type = 'submit';
  const clear = cashbackButton('Удалить отметку', () => update(null), '');
  const actions = document.createElement('div');
  actions.className = 'journal-actual-actions';
  actions.append(save, clear);
  form.append(cashbackText('h4', 'Фактический кэшбэк'), label, current, actions, status);

  function renderValue(){
    const amount = item.actualCashbackKopecks;
    current.textContent = amount == null ? 'Не подтверждено' : 'Подтверждено: ' + money(amount);
    input.value = amount == null ? '' : String(amount / 100).replace('.', ',');
    clear.hidden = amount == null;
  }

  async function update(amount){
    if (save.disabled) return;
    input.removeAttribute('aria-invalid');
    save.disabled = clear.disabled = input.disabled = true;
    status.textContent = 'Сохраняем…';
    try {
      await api(`/api/me/purchases/${item.id}/cashback`, {
        method: 'PUT',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({amountKopecks: amount})
      });
      item.actualCashbackKopecks = amount;
      renderValue();
      status.textContent = amount == null ? 'Отметка удалена.' : 'Начисление сохранено.';
      // A user can return home while the save is in flight.
      if (!$('hero').hidden && !$('appScreen').hidden) renderHomeCashback();
    } catch (error) {
      status.textContent = error.message || 'Не удалось сохранить. Повторите попытку.';
    } finally {
      save.disabled = clear.disabled = input.disabled = false;
    }
  }

  input.oninput = () => {
    input.removeAttribute('aria-invalid');
    status.textContent = '';
  };
  form.onsubmit = event => {
    event.preventDefault();
    const {value, msg} = checkout.parseAmount(input.value, true);
    if (msg){
      input.setAttribute('aria-invalid', 'true');
      status.textContent = msg === 'Введите сумму покупки.' ? 'Введите сумму начисления.' : msg;
      input.focus();
      return;
    }
    update(value);
  };
  renderValue();
  return form;
}

async function renderHistory(){
  const ticket = ++journalRequest;
  const host=$('historyBody'); host.className='journal is-loading'; host.textContent='Загружаем историю…';
  try{
    const query=historyMonth?`?month=${encodeURIComponent(historyMonth)}`:'';
    const data=await api('/api/me/stats'+query);
    if (ticket !== journalRequest) return;
    host.className='journal'; host.replaceChildren();
    if($('historyMonth') && data.month) $('historyMonth').value=data.month;
    historyMonth=data.month;
    const summary=document.createElement('section'); summary.className='journal-summary';
    syncHistoryMonthText();
    const total=document.createElement('p'); total.className='journal-total';
    const strong=document.createElement('strong'); strong.className='money'; strong.textContent=money(data.calculatedKopecks);
    const caption=document.createElement('span'); caption.textContent='Расчётный кэшбэк';
    total.append(strong, caption);
    const noteShort=(data.note||'Расчёт по записанным покупкам.').split('.').filter(Boolean)[0]+'.';
    const meta=document.createElement('p'); meta.className='journal-meta'; meta.textContent=`${purchaseCount(data.count)} · ${noteShort}`;
    summary.append(total, meta);
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
        const cash=document.createElement('span'); cash.className='journal-cash'; cash.textContent=item.estimateAvailable===false?'Расчёт недоступен':item.chosenKopecks==null?'':`+${money(item.chosenKopecks)} кэшбэка`;
        moneyCol.append(amount, cash); row.append(main, moneyCol);
        const detail=document.createElement('div'); detail.className='journal-detail'; detail.hidden=true;
        const chosen=document.createElement('p'); chosen.textContent=`Выбранная карта: ${item.chosenName||'—'}${item.estimateAvailable===false||item.chosenKopecks==null?'':`, ${money(item.chosenKopecks)}`}`;
        const best=document.createElement('p'); best.textContent=`Лучшая по расчёту: ${item.estimateAvailable===false?'—':item.recommendedName||'—'}${item.estimateAvailable===false||item.recommendedKopecks==null?'':`, ${money(item.recommendedKopecks)}`}`;
        const diff=document.createElement('p'); diff.textContent=`Разница: ${item.estimateAvailable===false||item.recommendedKopecks==null||item.chosenKopecks==null?'—':money(gap)}`;
        detail.append(chosen, best, diff);
        if (item.id != null) detail.append(actualCashbackForm(item));
        row.onclick=()=>{detail.hidden=!detail.hidden; row.setAttribute('aria-expanded', String(!detail.hidden));};
        list.append(row, detail);
      });
      host.append(list);
    });
  }catch(error){
    if (ticket !== journalRequest) return;
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
    const user=await api('/api/auth/guest',{method:'POST'});
    deviceLogin=user.login; localStorage.setItem('advisor-login',user.login);
    sessionStorage.setItem('advisor-auth-home','1'); await checkAuth();
  }catch(error){$('authError').textContent=error.message||'Не удалось войти как гость'; button.disabled=false;}
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
$('addRouteShot').addEventListener('click',()=>{closeDialog($('addDialog')); $('addCashbackBtn').click();});
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
  $('logout').disabled=true;
  try{await api('/api/auth/logout',{method:'POST'}); expireSession();}
  catch(error){$('settingsStatus').textContent=error.message;}
  finally{$('logout').disabled=false;}
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
      syncWalletRoute(forceHome || !!purchaseReminders.deepLink()); await load();
      if(deviceLogin) purchaseReminders.enter();
    }else{
      const draft = purchaseReminders.deepLink();
      $('welcomeScreen').hidden=!!draft; $('authScreen').hidden=!draft; $('appScreen').hidden=true;
      if(draft){showRemembered(); setAuthMode('login');}
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
