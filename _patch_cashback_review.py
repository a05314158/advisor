from pathlib import Path

path = Path('wallet-cashback.js')
text = path.read_text(encoding='utf-8')

old = """  $('chooseOffer').onclick=()=>choose('offer'); $('chooseActive').onclick=()=>choose('active');
  const mayDiscard=()=>!dirty || window.confirm('Выйти без сохранения? Черновик условий будет удалён.');
  $('changeDecision').onclick=()=>{if(mayDiscard()){dirty=false; clearShot(); showStep('decisionStep','Условия кэшбэка','bankId');}};
  $('cashbackShot').onchange=async()=>{
    clearFileState(); const token=draftEpoch,file=$('cashbackShot').files[0]; if(!file) return clearShot();
    dirty=true; $('shotPreview').textContent='Читаем снимок…';
    try{if(file.size>4000000) throw new Error('Снимок больше 4 МБ'); const data=await readShot(file); if(token!==draftEpoch)return;
      image=data; const img=node('img'); img.alt='Предпросмотр снимка'; img.src=image; $('shotPreview').replaceChildren(img); $('confirmCard').disabled=false;
    }catch(e){if(token===draftEpoch){$('shotPreview').textContent='Выберите другой снимок'; fail(e,$('shotError'));}}
  };
  function clearFileState(){++draftEpoch; image=''; $('confirmCard').disabled=true; $('confirmCard').textContent='Прочитать снимок'; $('shotError').textContent='';}
  $('screenshotForm').onsubmit=async e=>{e.preventDefault(); if(!image || $('confirmCard').disabled)return; const token=++draftEpoch;
    $('confirmCard').disabled=true; $('confirmCard').textContent='Распознаём…'; $('shotError').textContent='';
    try{const data=await post('cashback-screenshot',{...target,image},45000); if(token===draftEpoch)startReview(data.rules,data.month,null,'shot');}
    catch(err){if(token===draftEpoch)fail(err,$('shotError'));} finally{if(token===draftEpoch){$('confirmCard').disabled=false; $('confirmCard').textContent='Прочитать снимок';}}
  };
  $('manualDraft').onclick=()=>{if(!mayDiscard())return; startReview([{}],suggestedMonth || monthAt(mode==='offer'?1:0),null,'manual');};
  function labelled(parent,title,control,cls){const label=node('label',title,cls); label.append(control); parent.append(label); return control;}
  function input(parent,key,title,value,cls){const field=node('input'); field.dataset.key=key; field.value=value??''; return labelled(parent,title,field,cls);}
  function row(rule={}){
    const box=node('fieldset'); box.append(node('legend',rule.label || 'Новая категория'));
    if(source==='shot' && rule.label){const state=rule.selected===true?'выбрана':rule.selected===false?'не выбрана':'выбор не распознан'; box.append(node('p','На снимке: '+state+(rule.uncertain?'. Проверьте неуверенно распознанные поля.':'.'),rule.uncertain?'cb-warning':'cb-note'));}
    const grid=node('div',null,'cb-fields'); box.append(grid);
    const label=input(grid,'label','Название в банке',rule.label,'wide'); label.maxLength=80;
    const category=input(grid,'categoryId','Категория для расчёта (пусто — по названию)',rule.categoryId,'wide'); category.setAttribute('list','cbCategoryIds'); category.maxLength=80;
    for(const [key,title] of [['rateBps','Ставка, %'],['limitKopecks','Лимит кэшбэка, ₽'],['minAmountKopecks','Покупка от, ₽']]){const f=input(grid,key,title,rule[key]==null?'':rule[key]/100); f.inputMode='decimal'; if(key==='limitKopecks')f.placeholder='Не указан';}
    const include=node('input'); include.type='checkbox'; include.dataset.key='include'; labelled(box,mode==='active'?'Я подключил эту категорию в банке':'Включить в предложения',include,'cb-check');
    box.append(action('Убрать строку',()=>{dirty=true; box.remove(); $('addRule').focus();})); $('reviewRows').append(box); return label;
  }
  function startReview(rules,month,slots,kind){
    if(!Array.isArray(rules))throw new Error('Сервер не вернул список условий.');
    clearShot(); dirty=kind==='shot'; source=kind; replay=null; $('reviewRows').replaceChildren();
    const active=mode==='active'; $('reviewContext').textContent=bankName(target.bankId)+' · '+(active?'Подключённые категории':'Предложения для плана');
    $('reviewMonth').value=month || ''; $('reviewMonth').disabled=kind==='plan'; $('reviewSlots').value=slots??''; $('reviewSlots').max=128; $('reviewSlots').disabled=kind==='plan' && slots!=null;
    $('reviewWarnings').textContent=!month?'Месяц на снимке не распознан. Укажите период действия вручную.':kind==='plan' && rules.some(r=>r.rateBps==null)?'В плане есть названия, но нет ставок. Сверьте условия с банком и заполните строки.':'';
    $('reviewHint').textContent=active?'Отметьте только категории, которые вы уже выбрали в банке. Советник не подключает их за вас.':'Отметьте проверенные строки. Предложения не влияют на выбор карты перед оплатой. Без числа мест план не сможет сравнить варианты этой карты.';
    $('saveReview').textContent=active?'Сохранить подключённые категории':'Сохранить предложения'; rules.forEach(row); showStep('reviewForm','Проверка условий','reviewContext');
  }
  $('reviewForm').oninput=()=>{dirty=true;}; $('addRule').onclick=()=>{dirty=true;row().focus();};
  function hundredths(raw,fallback,name){const text=raw.trim(); if(!text && fallback!==undefined)return fallback; if(!/^\\d+(?:[.,]\\d{1,2})?$/.test(text))throw new Error(`Проверьте поле «${name}».`); const [whole,part='']=text.split(/[.,]/),value=Number(whole)*100+Number(part.padEnd(2,'0')); if(!Number.isSafeInteger(value))throw new Error(`Слишком большое значение: ${name}.`); return value;}
  $('reviewForm').onsubmit=async e=>{
    e.preventDefault(); if(busy)return;
    try{const rules=[]; for(const box of $('reviewRows').children){const fields=Object.fromEntries([...box.querySelectorAll('[data-key]')].map(f=>[f.dataset.key,f])); if(!fields.include.checked)continue;
      const label=fields.label.value.trim(); if(!label)throw new Error('Укажите название категории, как в банке.'); const rateBps=hundredths(fields.rateBps.value,undefined,'Ставка'); if(rateBps>10000)throw new Error('Ставка не может превышать 100 %.');
      rules.push({label,categoryId:fields.categoryId.value.trim() || label,rateBps,limitKopecks:hundredths(fields.limitKopecks.value,null,'Лимит'),minAmountKopecks:hundredths(fields.minAmountKopecks.value,1,'Минимальная покупка'),selected:true,uncertain:false});
    }
    if(!rules.length)throw new Error('Отметьте хотя бы одну проверенную строку.');
    const body={...target,month:$('reviewMonth').value,mode,slots:$('reviewSlots').value===''?null:Number($('reviewSlots').value),rules};
    const signature=JSON.stringify(body); if(replay?.signature!==signature)replay={signature,key:newKey()};
    busy=true; $('saveReview').disabled=true; $('reviewForm').inert=true; $('shotError').textContent='Сохраняем…'; const response=await post('cashback-confirm',{...body,requestId:replay.key});
    if(mode==='offer')sessionOffers.set(offerKey(response.cardId,response.month),{rules:response.rules,slots:response.slots});
    await load(); invalidatePlan(); busy=false; dirty=false; closeReview(); toast(mode==='offer'?'Предложения сохранены для плана':'Подключённые категории сохранены');
    }catch(err){fail(err,$('shotError'));}finally{busy=false; $('saveReview').disabled=false; $('reviewForm').inert=false;}
  };
  function closeReview(){if(busy || !mayDiscard())return false; dirty=false; clearShot(); review.hidden=true; $('reviewRows').replaceChildren(); if(suggestedMonth){planner.hidden=false; (origin?.isConnected?origin:$('calculatePlan')).focus();}else (origin||$('addCashbackBtn')).focus(); suggestedMonth=null; return true;}
"""

# The regex escaping in old string is wrong for matching file - use exact file content
# Let me read exact bytes from file instead
start = text.find("  $('chooseOffer').onclick")
end = text.find("  function closePlanner()")
if start < 0 or end < 0:
    raise SystemExit(f'markers not found {start} {end}')

new = r'''  $('chooseOffer').onclick=()=>choose('offer'); $('chooseActive').onclick=()=>choose('active');
  let discardResolver = null;
  function askDiscard(){
    return new Promise(resolve=>{
      if(!dirty){resolve(true); return;}
      const dialog=$('discardDialog');
      discardResolver=resolve;
      dialog.hidden=false;
      $('discardStay').focus();
    });
  }
  async function mayDiscard(){ return askDiscard(); }
  if($('discardStay')) $('discardStay').onclick=()=>{ $('discardDialog').hidden=true; const r=discardResolver; discardResolver=null; r?.(false); };
  if($('discardLeave')) $('discardLeave').onclick=()=>{ $('discardDialog').hidden=true; const r=discardResolver; discardResolver=null; r?.(true); };
  if($('discardDialog')) $('discardDialog').addEventListener('keydown',e=>{ if(e.key==='Escape'){ e.preventDefault(); $('discardStay').click(); }});
  $('changeDecision').onclick=async()=>{if(!(await mayDiscard()))return; dirty=false; clearShot(); showStep('decisionStep','Условия кэшбэка','bankId');};
  $('cashbackShot').onchange=async()=>{
    clearFileState(); const token=draftEpoch,file=$('cashbackShot').files[0]; if(!file) return clearShot();
    dirty=true; $('shotPreview').textContent='Читаем снимок…';
    try{if(file.size>4000000) throw new Error('Снимок больше 4 МБ'); const data=await readShot(file); if(token!==draftEpoch)return;
      image=data; const img=node('img'); img.alt='Предпросмотр снимка'; img.src=image; $('shotPreview').replaceChildren(img); $('confirmCard').disabled=false;
    }catch(e){if(token===draftEpoch){$('shotPreview').textContent='Выберите другой снимок'; fail(e,$('shotError'));}}
  };
  function clearFileState(){++draftEpoch; image=''; $('confirmCard').disabled=true; $('confirmCard').textContent='Прочитать снимок'; $('shotError').textContent='';}
  $('screenshotForm').onsubmit=async e=>{e.preventDefault(); if(!image || $('confirmCard').disabled)return; const token=++draftEpoch;
    $('confirmCard').disabled=true; $('confirmCard').textContent='Распознаём…'; $('shotError').textContent='';
    try{const data=await post('cashback-screenshot',{...target,image},45000); if(token===draftEpoch)startReview(data.rules,data.month,null,'shot');}
    catch(err){if(token===draftEpoch)fail(err,$('shotError'));} finally{if(token===draftEpoch){$('confirmCard').disabled=false; $('confirmCard').textContent='Прочитать снимок';}}
  };
  $('manualDraft').onclick=async()=>{if(!(await mayDiscard()))return; startReview([{}],suggestedMonth || monthAt(mode==='offer'?1:0),null,'manual');};
  function labelled(parent,title,control,cls){const label=node('label',title,cls); label.append(control); parent.append(label); return control;}
  function input(parent,key,title,value,cls){const field=node('input'); field.dataset.key=key; field.value=value??''; return labelled(parent,title,field,cls);}
  function formatRateText(bps){ if(bps==null||bps==='') return null; return (Number(bps)/100).toLocaleString('ru-RU',{maximumFractionDigits:2})+'%'; }
  function syncMonthText(){
    const value=$('reviewMonth').value;
    const text=$('reviewMonthText');
    if(!text) return;
    text.textContent=value?periodName(value).replace(/\s*г\.?$/,'').replace(/^./,c=>c.toUpperCase()):'Выберите месяц';
    text.classList.toggle('is-empty', !value);
  }
  function updateReviewFooter(){
    const boxes=[...$('reviewRows').children];
    let selected=0, needRate=false;
    boxes.forEach(box=>{
      const fields=Object.fromEntries([...box.querySelectorAll('[data-key]')].map(f=>[f.dataset.key,f]));
      if(fields.include?.checked){ selected+=1; if(!(fields.rateBps?.value||'').trim()) needRate=true; }
    });
    if($('reviewCount')) $('reviewCount').textContent=`Выбрано: ${selected}`;
    const needs=[];
    if(!$('reviewMonth').value) needs.push('укажите месяц');
    if(!selected) needs.push('отметьте категорию');
    if(needRate) needs.push('укажите ставку');
    if($('reviewNeed')) $('reviewNeed').textContent=needs.length?'Нужно: '+needs.join(', '):'';
    $('saveReview').disabled=!!needs.length || busy;
  }
  function row(rule={}){
    const box=node('fieldset','','review-row');
    const head=node('div',null,'review-row-head');
    const title=node('div',null,'review-row-title');
    const name=node('strong', rule.label || categories[rule.categoryId] || 'Новая категория');
    const meta=[]; const rate=formatRateText(rule.rateBps); if(rate) meta.push(rate);
    if(rule.limitKopecks!=null) meta.push('лимит '+(rule.limitKopecks/100).toLocaleString('ru-RU')+' ₽');
    if(!rate) meta.push('ставка не указана');
    const summary=node('span', meta.join(' · '), 'review-row-meta');
    title.append(name, summary);
    const include=node('input'); include.type='checkbox'; include.dataset.key='include'; include.checked=rule.selected===true;
    const includeLabel=node('label', mode==='active'?'Подключена':'Добавить в предложения', 'review-check');
    includeLabel.prepend(include);
    head.append(title, includeLabel); box.append(head);
    if(rule.uncertain) box.append(node('p','Проверьте неуверенно распознанные поля.','cb-warning'));
    const details=node('details',null,'review-details');
    details.append(node('summary','Подробнее'));
    const grid=node('div',null,'cb-fields'); details.append(grid);
    const label=input(grid,'label','Название в банке',rule.label,'wide'); label.maxLength=80;
    label.addEventListener('input',()=>{ name.textContent=label.value.trim()||'Новая категория'; updateReviewFooter(); });
    const category=input(grid,'categoryId','Категория для расчёта',rule.categoryId||'','wide'); category.setAttribute('list','cbCategoryIds'); category.maxLength=80;
    const rateField=input(grid,'rateBps','Ставка, %',rule.rateBps==null?'':rule.rateBps/100); rateField.inputMode='decimal';
    if(rule.rateBps==null){ rateField.required=true; rateField.placeholder='Укажите ставку'; rateField.classList.add('needs-input'); }
    rateField.addEventListener('input',()=>{
      const formatted=formatRateText(rateField.value===''?null:Number(String(rateField.value).replace(',','.'))*100);
      summary.textContent=[formatted||'ставка не указана', rule.limitKopecks!=null?('лимит '+(rule.limitKopecks/100).toLocaleString('ru-RU')+' ₽'):null].filter(Boolean).join(' · ');
      updateReviewFooter();
    });
    const limit=input(grid,'limitKopecks','Лимит кэшбэка, ₽',rule.limitKopecks==null?'':rule.limitKopecks/100); limit.inputMode='decimal'; limit.placeholder='Не указан';
    const minimum=input(grid,'minAmountKopecks','Минимальная сумма покупки, ₽',rule.minAmountKopecks==null?'':rule.minAmountKopecks/100); minimum.inputMode='decimal'; minimum.placeholder='1';
    if(rule.uncertain){
      const warn=node('p','Значение распознано неуверенно — сверьте со снимком.','cb-warning');
      rateField.parentElement.append(warn.cloneNode(true));
    }
    box.append(details);
    include.addEventListener('change',updateReviewFooter);
    box.append(action('Убрать строку',()=>{dirty=true; box.remove(); updateReviewFooter(); $('addRule').focus();}));
    $('reviewRows').append(box); return label;
  }
  function startReview(rules,month,slots,kind){
    if(!Array.isArray(rules))throw new Error('Сервер не вернул список условий.');
    clearShot(); dirty=kind==='shot' || !month; source=kind; replay=null; $('reviewRows').replaceChildren();
    const active=mode==='active';
    const cardLabel=$('cashbackCard').selectedOptions[0]?.textContent || 'Карта';
    $('reviewContext').textContent=bankName(target.bankId)+' · '+cardLabel;
    $('reviewMonth').value=month || ''; $('reviewMonth').disabled=kind==='plan'; syncMonthText();
    $('reviewSlots').value=slots??''; $('reviewSlots').max=128; $('reviewSlots').disabled=kind==='plan' && slots!=null;
    const slotsWrap=$('reviewSlotsLabel'); if(slotsWrap) slotsWrap.hidden=active;
    if($('reviewWarnings')){ $('reviewWarnings').hidden=true; $('reviewWarnings').textContent=''; }
    $('reviewHint').textContent=active?'Отметьте категории, которые уже подключены в банке.':'Отметьте предложения для плана. Без числа мест сравнение этой карты недоступно.';
    $('saveReview').textContent='Сохранить категории';
    rules.forEach(row);
    updateReviewFooter();
    showStep('reviewForm','Проверьте категории', month?'reviewContext':'reviewMonth');
  }
  $('reviewForm').oninput=()=>{dirty=true; updateReviewFooter();};
  $('reviewMonth').addEventListener('change',()=>{dirty=true; syncMonthText(); updateReviewFooter();});
  $('addRule').onclick=()=>{dirty=true;row().focus(); updateReviewFooter();};
  function hundredths(raw,fallback,name){const text=raw.trim(); if(!text && fallback!==undefined)return fallback; if(!/^\d+(?:[.,]\d{1,2})?$/.test(text))throw new Error(`Проверьте поле «${name}».`); const [whole,part='']=text.split(/[.,]/),value=Number(whole)*100+Number(part.padEnd(2,'0')); if(!Number.isSafeInteger(value))throw new Error(`Слишком большое значение: ${name}.`); return value;}
  $('reviewForm').onsubmit=async e=>{
    e.preventDefault(); if(busy)return; updateReviewFooter(); if($('saveReview').disabled) return;
    try{const rules=[]; for(const box of $('reviewRows').children){const fields=Object.fromEntries([...box.querySelectorAll('[data-key]')].map(f=>[f.dataset.key,f])); if(!fields.include.checked)continue;
      const label=fields.label.value.trim(); if(!label)throw new Error('Укажите название категории, как в банке.'); const rateBps=hundredths(fields.rateBps.value,undefined,'Ставка'); if(rateBps>10000)throw new Error('Ставка не может превышать 100 %.');
      rules.push({label,categoryId:fields.categoryId.value.trim() || label,rateBps,limitKopecks:hundredths(fields.limitKopecks.value,null,'Лимит'),minAmountKopecks:hundredths(fields.minAmountKopecks.value,1,'Минимальная покупка'),selected:true,uncertain:false});
    }
    if(!rules.length)throw new Error('Отметьте хотя бы одну проверенную строку.');
    const body={...target,month:$('reviewMonth').value,mode,slots:$('reviewSlots').value===''?null:Number($('reviewSlots').value),rules};
    const signature=JSON.stringify(body); if(replay?.signature!==signature)replay={signature,key:newKey()};
    busy=true; $('saveReview').disabled=true; $('saveReview').textContent='Сохраняем…'; $('reviewForm').inert=true; $('shotError').textContent='';
    const response=await post('cashback-confirm',{...body,requestId:replay.key});
    if(mode==='offer')sessionOffers.set(offerKey(response.cardId,response.month),{rules:response.rules,slots:response.slots});
    walletPreferredCard=response.cardId || target.cardId || walletPreferredCard;
    await load(); invalidatePlan(); busy=false; dirty=false; closeReview(true);
    if(typeof walletRoute==='function') walletRoute('cards', true);
    toast(mode==='offer'?'Предложения сохранены для плана':'Категории сохранены');
    }catch(err){fail(err,$('shotError')||$('reviewNeed'));}finally{busy=false; $('saveReview').disabled=false; $('saveReview').textContent='Сохранить категории'; $('reviewForm').inert=false; updateReviewFooter();}
  };
  async function closeReview(force){
    if(busy) return false;
    if(!force && !(await mayDiscard())) return false;
    dirty=false; clearShot(); review.hidden=true; $('reviewRows').replaceChildren();
    if(suggestedMonth){planner.hidden=false; (origin?.isConnected?origin:$('calculatePlan')).focus();}
    else (origin||$('addCashbackBtn')).focus();
    suggestedMonth=null; return true;
  }
'''

text = text[:start] + new + text[end:]
# closeReview was sync and used by onclick - update closeCatalog to async wrapper
text = text.replace("$('closeCatalog').onclick=closeReview;", "$('closeCatalog').onclick=()=>closeReview();")
text = text.replace(
    "window.walletCashbackBack=()=>{if(!review.hidden){closeReview();return true;}if(!planner.hidden){closePlanner();return true;}return false;};",
    "window.walletCashbackBack=()=>{if(!review.hidden){closeReview();return true;}const discard=$('discardDialog');if(discard&&!discard.hidden){$('discardStay').click();return true;}if(!planner.hidden){closePlanner();return true;}return false;};"
)

path.write_text(text, encoding='utf-8')
print('wallet-cashback.js patched', path.stat().st_size)
