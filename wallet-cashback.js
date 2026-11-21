/* Cashback drafts live only in memory. The planner never writes bank selections. */
(() => {
  'use strict';
  const review = $('catalogDialog'), planner = $('planDialog');
  let draftEpoch = 0, planEpoch = 0, busy = false, fromPlan = false, target, replay, image = '';
  const sessionOffers = new Map();
  const node = (tag, text, cls) => { const el = document.createElement(tag); if (text != null) el.textContent = text; if (cls) el.className = cls; return el; };
  const bankName = id => banks.find(b => b.id === id)?.name || id;
  const monthAt = delta => { const now = new Date(); return new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth() + delta, 1)).toISOString().slice(0, 7); };
  const newKey = () => Array.from(crypto.getRandomValues(new Uint8Array(16)), b => b.toString(16).padStart(2, '0')).join('');
  const post = (url, body, timeout) => api('/api/me/' + url, {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(body)}, timeout);
  const messages = {401:'Сессия закончилась. Войдите снова.', 403:'Нет доступа к этой карте.', 404:'Карта больше не доступна. Обновите кошелёк.', 409:'Условия изменились или у банка несколько карт. Проверьте выбранную карту.', 422:'Проверьте месяц и значения в строках.', 429:'Слишком много запросов. Повторите позже.', 502:'Распознавание недоступно. Повторите позже или введите условия вручную.'};
  function fail(error, out) {
    out.textContent = (error.status && !['Не удалось выполнить запрос.','Проверьте введённую сумму.'].includes(error.message) ? error.message : messages[error.status]) || (error.name === 'TimeoutError' ? 'Сервер не ответил вовремя. Повторите запрос.' : error.message);
    if (error.status === 401) { toast(messages[401]); dismissAll(); deviceLogin = null; $('appScreen').hidden = true; $('authScreen').hidden = false; showRemembered(); }
  }
  function invalidatePlan() { ++planEpoch; $('planResult').replaceChildren(); $('planError').textContent = ''; $('calculatePlan').disabled = false; }
  function clearShot() { ++draftEpoch; image = ''; $('cashbackShot').value = ''; $('shotPreview').textContent = 'Снимок из банка · JPG, PNG или WebP'; $('confirmCard').disabled = false; $('confirmCard').textContent = 'Прочитать снимок'; $('shotError').textContent = ''; }
  function dismissAll() { clearShot(); invalidatePlan(); review.hidden = planner.hidden = true; $('reviewRows').replaceChildren(); sessionOffers.clear(); }
  function cardOptions(preferred) {
    const matches = manual.filter(c => c.bankId === $('bankId').value || (!c.bankId && c.name === bankName($('bankId').value)));
    $('cashbackCard').replaceChildren(new Option('По банку (если карты нет — создать)', ''));
    matches.forEach((c, i) => $('cashbackCard').append(new Option(c.name + (matches.length > 1 ? ` · карта ${i+1}` : ''), c.cardId)));
    $('cashbackCard').value = matches.some(c => c.cardId === preferred) ? preferred : matches.length === 1 ? matches[0].cardId : '';
  }
  function chooseTarget() {
    if (!$('bankId').value) throw new Error('Выберите банк.');
    if ($('cashbackCard').options.length > 2 && !$('cashbackCard').value) throw new Error('У банка несколько карт. Выберите конкретную карту.');
    return {bankId:$('bankId').value, cardId:$('cashbackCard').value || undefined};
  }
  $('addCashbackBtn').addEventListener('click', () => {
    clearShot(); fromPlan = false; review.hidden = false; $('screenshotForm').hidden = false; $('reviewForm').hidden = true;
    const c = carouselPos.all[mod(Math.round(carouselPos.value), carouselPos.all.length)];
    const bank = banks.find(b => b.id === c?.bankId || b.name === c?.name);
    if (bank) $('bankId').value = bank.id;
    cardOptions(c?.cardId); $('bankId').focus();
  });
  $('bankId').onchange = () => { clearShot(); cardOptions(); };
  $('cashbackCard').onchange = clearShot;
  $('cashbackShot').onchange = async () => {
    const token = ++draftEpoch, file = $('cashbackShot').files[0]; image = ''; $('shotError').textContent = '';
    if (!file) return clearShot();
    $('shotPreview').textContent = 'Читаем снимок…'; $('confirmCard').disabled = true;
    try { if (file.size > 4000000) throw new Error('Скриншот больше 4 МБ'); const data = await readShot(file); if (token !== draftEpoch) return; image = data; const img = node('img'); img.alt = 'Предпросмотр скриншота'; img.src = image; $('shotPreview').replaceChildren(img); }
    catch (e) { if (token === draftEpoch) { $('shotPreview').textContent = 'Выберите другой снимок'; fail(e, $('shotError')); } }
    finally { if (token === draftEpoch) { $('confirmCard').disabled = false; $('confirmCard').textContent = 'Прочитать снимок'; } }
  };
  $('screenshotForm').onsubmit = async event => {
    event.preventDefault(); if ($('confirmCard').disabled) return; const token = ++draftEpoch;
    try { target = chooseTarget(); if (!image) throw new Error('Выберите снимок или введите условия вручную.');
      $('confirmCard').disabled = true; $('confirmCard').textContent = 'Распознаём…'; $('shotError').textContent = '';
      const data = await post('cashback-screenshot', {...target, image}, 45000);
      if (token === draftEpoch) startReview(data.rules, data.month, 'offer', data.slots, data.warnings);
    } catch (e) { if (token === draftEpoch) fail(e, $('shotError')); }
    finally { if (token === draftEpoch) { $('confirmCard').disabled = false; $('confirmCard').textContent = 'Прочитать снимок'; } }
  };
  $('manualDraft').onclick = () => { try { target = chooseTarget(); startReview([{manual:true}], null, 'active'); } catch (e) { fail(e,$('shotError')); } };
  function labelled(parent, title, control, cls) { const label = node('label', title, cls); label.append(control); parent.append(label); return control; }
  function input(parent, key, title, value, cls) { const field = node('input'); field.dataset.key = key; field.value = value ?? ''; labelled(parent, title, field, cls); return field; }
  function row(rule) {
    const box = node('fieldset'), legend = node('legend',rule.label || 'Новая категория'); box.append(legend);
    const state = rule.selected === true ? 'выбрана' : rule.selected === false ? 'не выбрана' : 'неизвестно';
    const source = rule.label ? `На снимке: ${state}.` : 'Введите строку так, как она показана в банке.';
    box.append(node('p', source + (rule.uncertain && rule.label ? ' Распознано неуверенно — сверьте условия.' : ''), rule.uncertain && rule.label ? 'cb-warning' : 'cb-note'));
    const grid = node('div', null, 'cb-fields'); box.append(grid);
    const label = input(grid,'label','Название в банке',rule.label,'wide'); label.maxLength = 80;
    const category = input(grid,'categoryId','Категория для расчёта (пусто — по названию)',rule.categoryId,'wide'); category.setAttribute('list','cbCategoryIds');
    [['rateBps','Ставка, %'],['limitKopecks','Лимит, ₽'],['minAmountKopecks','Покупка от, ₽']].forEach(([key,title]) => { const field = input(grid,key,title,rule[key] == null ? '' : rule[key] / 100); field.inputMode = 'decimal'; });
    const include = node('input'); include.type = 'checkbox'; include.dataset.key = 'include'; include.checked = rule.manual === true;
    labelled(box, 'Подтверждаю эту строку',include,'cb-check');
    const remove = node('button','Убрать строку'); remove.type = 'button'; remove.onclick = () => { box.remove(); $('addRule').focus(); }; box.append(remove);
    box.dataset.selected = JSON.stringify(rule.selected ?? null); $('reviewRows').append(box); return label;
  }
  function updateMode() { const active = $('reviewMode').value === 'active'; $('reviewHint').textContent = active ? 'Отметьте только категории, которые вы уже подключили в приложении банка.' : 'Отметьте проверенные предложения. Они попадут в план, но не будут считаться подключёнными.'; $('saveReview').textContent = active ? 'Подтвердить подключение в банке' : 'Сохранить предложения'; }
  $('reviewMode').onchange = () => { for (const box of $('reviewRows').querySelectorAll('[type=checkbox]')) box.checked = false; updateMode(); };
  function startReview(rules, month, mode, slots, warnings = []) {
    if (!Array.isArray(rules)) throw new Error('Сервер не вернул список условий.');
    clearShot(); replay = null; $('screenshotForm').hidden = true; $('reviewForm').hidden = false; $('reviewRows').replaceChildren();
    $('reviewContext').textContent = `${bankName(target.bankId)} · ${manual.find(c => c.cardId === target.cardId)?.name || 'Карта по банку'}`;
    $('reviewMonth').value = month || monthAt(0); $('reviewMonth').disabled = fromPlan; month = $('reviewMonth').value;
    $('reviewMode').value = mode; $('reviewMode').disabled = fromPlan; $('reviewSlots').value = slots || ''; $('reviewSlots').disabled = fromPlan && Boolean(slots);
    $('reviewWarnings').textContent = [...(Array.isArray(warnings) ? warnings : []), ...(!month ? ['Месяц не указан — проверьте период.'] : [])].join(' ');
    updateMode(); rules.forEach(row); $('saveReview').disabled = false; $('reviewContext').tabIndex = -1; $('reviewContext').focus();
  }
  $('addRule').onclick = () => row({}).focus();
  function hundredths(raw, fallback, name) {
    const text = raw.trim(); if (!text && fallback !== undefined) return fallback;
    if (!/^\d+(?:[.,]\d{1,2})?$/.test(text)) throw new Error(`Проверьте поле «${name}».`);
    const [whole, part = ''] = text.split(/[.,]/), value = Number(whole)*100 + Number(part.padEnd(2,'0'));
    if (!Number.isSafeInteger(value)) throw new Error(`Слишком большое значение: ${name}.`); return value;
  }
  const offerKey = (card, month) => JSON.stringify([deviceLogin, card, month]);
  $('reviewForm').onsubmit = async event => {
    event.preventDefault(); if (busy) return; const mode = $('reviewMode').value, rules = [];
    try { for (const box of $('reviewRows').children) {
      const fields = Object.fromEntries([...box.querySelectorAll('[data-key]')].map(f => [f.dataset.key,f])); if (!fields.include.checked) continue;
      const label = fields.label.value.trim(); if (!label) throw new Error('Укажите название категории, как в банке.');
      const rateBps = hundredths(fields.rateBps.value,undefined,'Ставка'); if (rateBps > 10000) throw new Error('Ставка не может превышать 100 %.');
      rules.push({label, categoryId:fields.categoryId.value.trim() || label, rateBps, limitKopecks:hundredths(fields.limitKopecks.value,null,'Лимит'), minAmountKopecks:hundredths(fields.minAmountKopecks.value,1,'Минимальная покупка'), selected:true, uncertain:false});
    }
    if (!rules.length) throw new Error('Отметьте хотя бы одну проверенную строку.');
    const body = {...target, month:$('reviewMonth').value, mode, slots:$('reviewSlots').value ? Number($('reviewSlots').value) : null, rules};
    const signature = JSON.stringify(body); if (replay?.signature !== signature) replay = {signature, key:newKey()};
    busy = true; $('saveReview').disabled = true; $('shotError').textContent = 'Сохраняем…'; $('reviewForm').inert = true;
    const response = await post('cashback-confirm', {...body,requestId:replay.key});
    if (mode === 'offer') { const key = offerKey(response?.cardId || target.cardId,body.month), combined = new Map((sessionOffers.get(key)?.rules || []).map(r => [r.label,r])); for (const r of rules) combined.set(r.label,r); sessionOffers.set(key,{slots:body.slots,rules:[...combined.values()]}); }
    busy = false; closeReview(); invalidatePlan(); toast(mode === 'offer' ? 'Предложения сохранены для планирования' : 'Подключённые категории сохранены'); await load();
    } catch(e) { fail(e,$('shotError')); } finally { busy = false; $('saveReview').disabled = false; $('reviewForm').inert = false; }
  };
  function closeReview() { if (busy) return; clearShot(); review.hidden = true; $('reviewRows').replaceChildren(); if (fromPlan) { planner.hidden = false; $('calculatePlan').focus(); } else $('addCashbackBtn').focus(); fromPlan = false; }
  function closePlanner() { invalidatePlan(); planner.hidden = true; $('openPlan').focus(); }
  $('closeCatalog').onclick = closeReview; $('closePlan').onclick = closePlanner;
  for (const [dialog, close] of [[review,closeReview],[planner,closePlanner]]) {
    dialog.onclick = e => { if (e.target === dialog) close(); };
    dialog.onkeydown = e => { if (e.key === 'Escape') { e.preventDefault(); close(); } if (e.key !== 'Tab') return;
      const items = [...dialog.querySelectorAll('button,input,select')].filter(x => !x.disabled && x.getClientRects().length && !x.closest('[inert]'));
      if (!items.length) return; if (e.shiftKey && document.activeElement === items[0]) { e.preventDefault(); items.at(-1).focus(); } else if (!e.shiftKey && document.activeElement === items.at(-1)) { e.preventDefault(); items[0].focus(); }
    };
  }
  const list = node('datalist'); list.id = 'cbCategoryIds'; document.body.append(list);
  function syncCategories() { list.replaceChildren(...Object.entries(categories).map(([id,name]) => new Option(name,id))); }
  document.addEventListener('wallet-updated', () => { syncCategories(); invalidatePlan(); }); syncCategories();
  function spendRow() { const wrap = node('div',null,'cb-fields'); const cat = input(wrap,'categoryId','Категория','',''); cat.setAttribute('list',list.id); const amount = input(wrap,'amount','Траты, ₽',''); amount.inputMode = 'decimal'; $('spendRows').append(wrap); return cat; }
  $('openPlan').onclick = () => { invalidatePlan(); planner.hidden = false; $('planMonth').value = monthAt(1); $('spendingMonth').value = monthAt(0); $('spendingSource').value = 'history'; $('spendingInputs').hidden = true; $('spendingPeriod').hidden = false;
    const rows = node('div'); rows.id = 'spendRows'; const add = node('button','Добавить категорию трат'); add.type = 'button'; add.onclick = () => spendRow().focus(); $('spendingInputs').replaceChildren(rows,add); spendRow(); $('planMonth').focus(); };
  $('spendingSource').onchange = () => { const manualInput = $('spendingSource').value === 'manual'; $('spendingInputs').hidden = !manualInput; $('spendingPeriod').hidden = manualInput; invalidatePlan(); };
  $('planForm').oninput = invalidatePlan;
  function activation(choice, month, data) {
    const savedOffer = sessionOffers.get(offerKey(choice.cardId,month));
    const details = data.activation?.find?.(x => x.cardId === choice.cardId) || savedOffer;
    const rows = choice.labels.map(label => details?.rules?.find(r => r.label === label) || {label,uncertain:true});
    fromPlan = true; target = {bankId:choice.bankId,cardId:choice.cardId}; planner.hidden = true; review.hidden = false;
    startReview(rows,month,'active',details?.slots,rows.some(r => r.rateBps == null) ? ['Сверьте ставку, лимит и минимальную покупку с банком.'] : []);
  }
  function showPlan(data, month) {
    const host = $('planResult'); host.replaceChildren(node('h3','Прогноз на '+month));
    host.append(node('p',`Сейчас: ${money(data.baseKopecks)}. По плану: ${money(data.projectedKopecks)}. Разница: ${money(data.gainKopecks)}.`));
    for (const text of data.warnings || []) host.append(node('p',text,'cb-warning'));
    if (!data.choices.length) host.append(node('p','Дополнительных категорий для подключения нет.','cb-note'));
    else host.append(node('p','Сначала выберите категории в банке. После этого подтвердите выбор здесь.','cb-note'));
    for (const choice of data.choices) { const group = node('article'); group.append(node('h3',bankName(choice.bankId))); const labels = node('ul'); choice.labels.forEach(l => labels.append(node('li',l))); group.append(labels); const activate = node('button','Подтвердить выбор в этом банке'); activate.type = 'button'; activate.onclick = () => activation(choice,month,data); group.append(activate); host.append(group); }
  }
  $('planForm').onsubmit = async e => {
    e.preventDefault(); if ($('calculatePlan').disabled) return; invalidatePlan(); const token = planEpoch;
    try { const body = {month:$('planMonth').value,spendingMonth:$('spendingMonth').value};
      if ($('spendingSource').value === 'manual') { body.spending = []; for (const r of $('spendRows').children) { const [cat,amt] = r.querySelectorAll('input'); if (!cat.value.trim() && !amt.value.trim()) continue;
        if (!cat.value.trim()) throw new Error('Введите категорию трат.'); const amountKopecks = hundredths(amt.value,undefined,'Траты'); if (!amountKopecks) throw new Error('Сумма трат должна быть больше нуля.'); body.spending.push({categoryId:cat.value.trim(),amountKopecks}); }
        if (!body.spending.length) throw new Error('Введите хотя бы одну сумму трат.'); }
      $('calculatePlan').disabled = true; $('planResult').textContent = 'Сравниваем предложения банков…'; const result = await post('cashback-plan',body,45000); if (token === planEpoch) showPlan(result,body.month);
    } catch (error) { if (token === planEpoch) { $('planResult').replaceChildren(); fail(error,$('planError')); } } finally { if (token === planEpoch) $('calculatePlan').disabled = false; }
  };
  new ResizeObserver(() => { if ($('cardCarousel').clientWidth) { carouselPos.slotPx = carouselSlot(); applyCarouselTransforms(); } }).observe($('cardCarousel'));
})();
