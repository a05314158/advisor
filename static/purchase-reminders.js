const purchaseReminders = (() => {
  'use strict';

  const section = document.getElementById('homePurchaseReminders');
  const list = document.getElementById('purchaseDrafts');
  const panel = document.getElementById('purchaseDraftDetail');
  const heading = document.getElementById('purchaseDraftTitle');
  const content = document.getElementById('purchaseDraftContent');
  const toggle = document.getElementById('purchasePushToggle');
  const status = document.getElementById('purchasePushStatus');
  const ios = /iPhone|iPad|iPod/.test(navigator.userAgent)
    || (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1);
  const installed = matchMedia('(display-mode: standalone)').matches || navigator.standalone;
  const supportsPush = isSecureContext && 'serviceWorker' in navigator
    && 'PushManager' in window && 'Notification' in window;
  const registration = isSecureContext && 'serviceWorker' in navigator
    ? navigator.serviceWorker.register('/sw.js').catch(() => null) : Promise.resolve(null);

  let selected = null;
  let listVersion = 0;
  let detailVersion = 0;
  let pushVersion = 0;
  let busy = false;

  function node(tag, text) {
    const element = document.createElement(tag);
    if (text !== undefined) element.textContent = text;
    return element;
  }

  function button(label, action, className = 'buy-secondary') {
    const element = node('button', label);
    element.type = 'button';
    element.className = className;
    element.onclick = action;
    return element;
  }

  function request(path, method, body) {
    return api(path, { method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
  }

  function deepLink() {
    const id = new URLSearchParams(location.search).get('draft');
    return id && /^[a-f0-9]{64}$/.test(id) ? id : null;
  }

  function setDeepLink(id) {
    const url = new URL(location.href);
    if (id) url.searchParams.set('draft', id);
    else url.searchParams.delete('draft');
    history.replaceState(history.state, '', url);
  }

  function showSection() {
    section.hidden = !selected && !list.children.length && toggle.hidden && !status.textContent;
  }

  function close() {
    detailVersion++;
    selected = null;
    setDeepLink(null);
    content.replaceChildren();
    panel.hidden = true;
    showSection();
    (list.querySelector('button') || document.getElementById('homeTitle')).focus();
  }

  function summary(draft) {
    const card = draft.cards.find(item => item.id === draft.chosenCardId)?.name;
    const day = new Intl.DateTimeFormat('ru-RU', { timeZone: 'UTC', dateStyle: 'medium' })
      .format(new Date(draft.paidOn + 'T00:00:00Z'));
    return [categories[draft.categoryId] || draft.categoryId, money(draft.amountKopecks), card, day].join(' · ');
  }

  async function refresh() {
    const version = ++listVersion;
    try {
      const data = await api('/api/me/purchase-drafts');
      if (version !== listVersion || !deviceLogin) return;
      list.replaceChildren(...data.drafts.map(draft => button(summary(draft), () => open(draft.id))));
    } catch (error) {
      if (version !== listVersion || !deviceLogin) return;
      list.replaceChildren(node('p', error.message), button('Обновить черновики', refresh));
    }
    showSection();
  }

  async function decide(draft, body, feedback) {
    const id = draft.id;
    const buttons = Array.from(content.querySelectorAll('button'));
    buttons.forEach(element => { element.disabled = true; });
    feedback.textContent = 'Сохраняем…';
    try {
      const result = await request('/api/me/purchase-drafts/' + id + '/decision', 'PUT', body);
      if (selected !== id || !deviceLogin) return;
      render(result);
      heading.focus();
      refresh();
      if (result.status === 'confirmed') renderHomeCashback();
    } catch (error) {
      if (selected !== id || !deviceLogin) return;
      if (error.status === 409) return open(id);
      feedback.textContent = error.message;
      buttons.forEach(element => { element.disabled = false; });
    }
  }

  function field(label, input) {
    const field = node('label', label);
    field.append(input);
    return field;
  }

  function render(draft) {
    content.replaceChildren();
    if (draft.status !== 'pending') {
      heading.textContent = draft.status === 'confirmed' ? 'Покупка записана' : 'Черновик закрыт';
      if (draft.status === 'confirmed') {
        content.append(node('p', summary(draft)), button('Открыть историю', () => {
          close();
          const month = document.getElementById('historyMonth');
          month.value = draft.paidOn.slice(0, 7);
          month.dispatchEvent(new Event('change'));
          walletRoute('history');
        }));
      } else {
        content.append(node('p', 'Покупка не добавлена в историю.'));
      }
      return;
    }

    heading.textContent = 'Оплатили покупку?';
    const feedback = node('p');
    feedback.setAttribute('role', 'status');
    const form = node('form');
    form.className = 'shot-form';
    const amount = node('input');
    amount.inputMode = 'decimal';
    amount.value = (draft.amountKopecks / 100).toFixed(2).replace('.', ',');
    const card = node('select');
    card.replaceChildren(...draft.cards.map(item => new Option(item.name, item.id)));
    card.value = draft.chosenCardId;
    const day = node('input');
    day.type = 'date';
    day.required = true;
    day.value = draft.paidOn;
    const note = node('p', 'При смене даты покупка попадёт в нужный месяц. Расчёт кэшбэка доступен только для даты, на которую были сохранены условия.');
    const save = node('button', 'Подтвердить с изменениями');
    save.type = 'submit';
    save.className = 'buy-primary';
    form.append(field('Сумма, ₽', amount), field('Карта оплаты', card), field('Дата оплаты', day), note, save);
    form.hidden = true;
    const actions = node('div');
    actions.className = 'purchase-draft-actions';
    const yes = button('Да, оплатил', () => decide(draft, { action: 'confirm' }, feedback), 'buy-primary');
    const no = button('Нет, не оплатил', () => decide(draft, { action: 'decline' }, feedback));
    const edit = button('Изменить', () => {
      form.hidden = !form.hidden;
      yes.hidden = !form.hidden;
      edit.textContent = form.hidden ? 'Изменить' : 'Свернуть изменения';
      edit.setAttribute('aria-expanded', String(!form.hidden));
      if (!form.hidden) amount.focus();
    });
    edit.setAttribute('aria-expanded', 'false');
    actions.append(yes, edit, no);
    form.onsubmit = event => {
      event.preventDefault();
      const match = /^(\d+)(?:[,.](\d{1,2}))?$/.exec(amount.value.trim());
      const kopecks = match ? Number(match[1]) * 100 + Number((match[2] || '').padEnd(2, '0')) : 0;
      if (kopecks <= 0 || kopecks > 1e12) {
        feedback.textContent = 'Введите сумму в рублях, например 250,50.';
        amount.focus();
        return;
      }
      decide(draft, { action: 'confirm', amountKopecks: kopecks, chosenCardId: card.value, paidOn: day.value }, feedback);
    };
    content.append(node('p', summary(draft)), actions, form, feedback);
  }

  async function open(id) {
    const version = ++detailVersion;
    selected = id;
    setDeepLink(id);
    if (location.hash !== '#home') walletRoute('home', true);
    heading.textContent = 'Подтверждение покупки';
    content.replaceChildren(node('p', 'Загружаем…'));
    panel.hidden = false;
    showSection();
    heading.focus();
    panel.scrollIntoView({ block: 'nearest' });
    try {
      const draft = await api('/api/me/purchase-drafts/' + id);
      if (version === detailVersion && deviceLogin) render(draft);
    } catch (error) {
      if (version !== detailVersion || !deviceLogin) return;
      content.replaceChildren(node('p', error.message));
      if (error.status !== 404) content.append(button('Повторить', () => open(id)));
    }
  }

  async function pushControls() {
    const version = ++pushVersion;
    if (!supportsPush && !(ios && !installed)) return;
    try {
      const { publicKey } = await api('/api/me/push');
      if (version !== pushVersion || !deviceLogin || !publicKey) return;
      if (ios && !installed) {
        status.textContent = 'Для уведомлений на iPhone или iPad добавьте КопиКэш на экран «Домой» и откройте оттуда.';
        showSection();
        return;
      }
      const worker = await registration;
      if (!worker || version !== pushVersion || !deviceLogin) return;
      const sub = await worker.pushManager.getSubscription();
      const state = sub && await request('/api/me/push/status', 'POST', { endpoint: sub.endpoint });
      if (version !== pushVersion || !deviceLogin) return;
      const enabled = state?.enabled && Notification.permission === 'granted';
      toggle.textContent = enabled ? 'Выключить уведомления' : 'Включить уведомления';
      toggle.hidden = false;
      toggle.onclick = async () => {
        if (busy) return;
        busy = true;
        toggle.disabled = true;
        status.textContent = '';
        try {
          if (enabled) {
            await request('/api/me/push', 'DELETE', { endpoint: sub.endpoint });
            await sub.unsubscribe();
          } else {
            const permission = await Notification.requestPermission();
            if (permission !== 'granted') {
              status.textContent = 'Черновики доступны здесь. Разрешение можно изменить в настройках уведомлений.';
              return;
            }
            const key = publicKey.replace(/-/g, '+').replace(/_/g, '/');
            const applicationServerKey = Uint8Array.from(atob(key), char => char.charCodeAt(0));
            const subscription = sub || await worker.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey });
            await request('/api/me/push', 'PUT', subscription.toJSON());
          }
          await pushControls();
        } catch (error) {
          status.textContent = error.message || 'Не удалось изменить настройки уведомлений.';
        } finally {
          busy = false;
          toggle.disabled = false;
          showSection();
        }
      };
      showSection();
    } catch {
      // The wallet list is available even if push configuration cannot load.
    }
  }

  function reset() {
    listVersion++;
    detailVersion++;
    pushVersion++;
    selected = null;
    list.replaceChildren();
    content.replaceChildren();
    panel.hidden = true;
    toggle.hidden = true;
    status.textContent = '';
    section.hidden = true;
  }

  function enter() {
    reset();
    refresh();
    pushControls();
    const id = deepLink();
    if (id) open(id);
  }

  function create(body) {
    const timezone = Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC';
    return request('/api/me/purchase-drafts', 'POST', { ...body, timezone });
  }

  document.getElementById('closePurchaseDraft').onclick = close;
  window.addEventListener('popstate', () => {
    if (!deviceLogin) return;
    const id = deepLink();
    if (id && id !== selected) open(id);
    else if (!id && selected) close();
  });
  return { enter, reset, deepLink, create, open, refresh };
})();
