"""Patch wallet.html for single checkAuth stub, session gate, hide carousel arrows."""
from pathlib import Path

path = Path('wallet.html')
text = path.read_text(encoding='utf-8')

old_check = (
    "async function checkAuth(){try{const user=await api('/api/auth/me');"
    "$('welcomeScreen').hidden=user.authenticated;$('authScreen').hidden=true;"
    "$('appScreen').hidden=!user.authenticated;if(user.authenticated){deviceLogin=user.login;"
    "$('authPassword').value='';syncWalletRoute(false);await load()}}"
    "catch{$('welcomeScreen').hidden=false;$('authScreen').hidden=true;$('appScreen').hidden=true}}"
)
new_check = (
    "async function checkAuth(){if(window.shellCheckAuth)return window.shellCheckAuth();"
    "$('welcomeScreen').hidden=false;$('authScreen').hidden=true;$('appScreen').hidden=true}"
)
if old_check not in text:
    raise SystemExit('checkAuth block not found')
text = text.replace(old_check, new_check, 1)

old_submit = (
    "deviceLogin=user.login;localStorage.setItem('advisor-login',user.login);"
    "setAuthMode('register');await checkAuth()"
)
new_submit = (
    "deviceLogin=user.login;localStorage.setItem('advisor-login',user.login);"
    "setAuthMode('register');sessionStorage.setItem('advisor-auth-home','1');await checkAuth()"
)
if old_submit not in text:
    raise SystemExit('auth submit success path not found')
text = text.replace(old_submit, new_submit, 1)

# Session gate before welcome iframe
gate = (
    '<div id="sessionGate" class="session-gate" hidden>'
    '<p id="sessionGateStatus">Проверяем вход…</p>'
    '<button type="button" id="sessionGateRetry" hidden>Повторить</button>'
    '</div>\n  '
)
if 'id="sessionGate"' not in text:
    marker = '<iframe id="welcomeScreen"'
    if marker not in text:
        raise SystemExit('welcome iframe not found')
    text = text.replace(marker, gate + marker, 1)

# Discard dialog for cashback review
discard = (
    '<div class="dialog" id="discardDialog" role="dialog" aria-modal="true" '
    'aria-labelledby="discardTitle" hidden><div class="dialog-card">'
    '<div class="dialog-head"><h2 id="discardTitle">Выйти без сохранения?</h2></div>'
    '<p id="discardDescription">Черновик условий будет удалён.</p>'
    '<div class="dialog-actions">'
    '<button type="button" class="cancel" id="discardStay">Продолжить проверку</button>'
    '<button type="button" class="confirm" id="discardLeave">Выйти без сохранения</button>'
    '</div></div></div>\n'
)
if 'id="discardDialog"' not in text:
    text = text.replace('<div id="toast"', discard + '<div id="toast"', 1)

# Hide carousel arrows in markup (keep nodes for potential a11y tests that look for ids — remove buttons)
old_controls = (
    '<div class="carousel-controls" id="carouselControls" hidden>'
    '<button class="carousel-arrow" id="carouselPrev" type="button" aria-label="Предыдущая карта">‹</button>'
    '<span class="carousel-position" id="carouselPosition" aria-live="polite"></span>'
    '<button class="carousel-arrow" id="carouselNext" type="button" aria-label="Следующая карта">›</button>'
    '</div>'
)
new_controls = (
    '<div class="carousel-controls" id="carouselControls" hidden>'
    '<button class="carousel-arrow" id="carouselPrev" type="button" aria-label="Предыдущая карта" hidden>‹</button>'
    '<span class="carousel-position" id="carouselPosition" aria-live="polite"></span>'
    '<button class="carousel-arrow" id="carouselNext" type="button" aria-label="Следующая карта" hidden>›</button>'
    '</div>'
)
if old_controls not in text:
    raise SystemExit('carousel controls not found')
text = text.replace(old_controls, new_controls, 1)

# Always hide arrows in updateCarouselDetails
text = text.replace(
    "$('carouselPrev').hidden=cards.length<2;$('carouselNext').hidden=cards.length<2;",
    "$('carouselPrev').hidden=true;$('carouselNext').hidden=true;",
)

# Demo bar restore
if 'id="demoBar"' not in text:
    demo = (
        '<div class="demo-bar" id="demoBar" hidden>'
        '<div class="demo-switch" role="group" aria-label="Сколько карт показать">'
        '<button type="button" data-demo-count="1">1</button>'
        '<button type="button" data-demo-count="2">2</button>'
        '<button type="button" data-demo-count="4">4</button>'
        '<button type="button" data-demo-count="7">7</button>'
        '</div>'
        '<button type="button" id="demoReset">Сначала</button>'
        '<a href="/">В приложение</a></div>\n    '
    )
    text = text.replace(
        '<div class="wallet-status"',
        demo + '<div class="wallet-status"',
        1,
    )

# Early demo dataset to skip welcome flash
if 'dataset.demo' not in text[:800]:
    text = text.replace(
        '<meta name="theme-color" content="#F5F3EE">\n',
        '<meta name="theme-color" content="#F5F3EE">\n'
        '  <script>if(new URLSearchParams(location.search).get("demo")==="cards")'
        'document.documentElement.dataset.demo="cards"</script>\n',
        1,
    )

# Review form rewrite skeleton in HTML
old_review = (
    '<form class="shot-form" id="reviewForm" hidden>'
    '<p class="cb-note" id="reviewContext" tabindex="-1"></p>'
    '<p class="cb-warning" id="reviewWarnings" role="status"></p>'
    '<label>Месяц действия<input type="month" id="reviewMonth" required></label>'
    '<label>Всего мест для категорий у этой карты'
    '<input type="number" min="0" step="1" id="reviewSlots" placeholder="Неизвестно"></label>'
    '<p id="reviewHint" class="cb-note"></p>'
    '<div id="reviewRows"></div>'
    '<button type="button" id="addRule">Добавить строку</button>'
    '<button type="submit" class="confirm" id="saveReview">Сохранить предложения</button>'
    '</form>'
)
new_review = (
    '<form class="shot-form review-form" id="reviewForm" hidden>'
    '<p class="review-bank" id="reviewContext" tabindex="-1"></p>'
    '<p class="cb-note" id="reviewHint"></p>'
    '<p class="cb-warning" id="reviewWarnings" role="status" hidden></p>'
    '<div class="review-month">'
    '<span class="review-month-label" id="reviewMonthLabel">Месяц действия</span>'
    '<p class="review-month-text" id="reviewMonthText">Выберите месяц</p>'
    '<input type="month" id="reviewMonth" required aria-labelledby="reviewMonthLabel">'
    '</div>'
    '<label class="review-slots" id="reviewSlotsLabel">Число мест для категорий'
    '<input type="number" min="0" step="1" id="reviewSlots" placeholder="Неизвестно"></label>'
    '<div id="reviewRows" class="review-rows"></div>'
    '<button type="button" id="addRule" class="text-action">Добавить строку</button>'
    '<div class="review-footer">'
    '<p class="review-count" id="reviewCount" aria-live="polite">Выбрано: 0</p>'
    '<p class="review-need" id="reviewNeed" role="status"></p>'
    '<button type="submit" class="confirm" id="saveReview">Сохранить категории</button>'
    '</div>'
    '</form>'
)
if old_review not in text:
    raise SystemExit('reviewForm not found')
text = text.replace(old_review, new_review, 1)

# History month select
if 'id="historyMonth"' not in text:
    text = text.replace(
        '<h2 id="historyTitle" tabindex="-1">История покупок</h2>',
        '<h2 id="historyTitle" tabindex="-1">История покупок</h2>'
        '<label class="history-month-label" for="historyMonth">Месяц'
        '<input type="month" id="historyMonth"></label>',
        1,
    )

# Simplify add card form: keep addSource/newBank for tests but hide source visually via class;
# add catalog link and selected bank label
old_add = (
    '<form id="addCardForm" class="shot-form" hidden>'
    '<label>Источник<select id="addSource">'
    '<option value="bank">Мой банк</option>'
    '<option value="catalog">Учебный каталог</option>'
    '</select></label>'
)
# Find exact - may already differ
if old_add not in text:
    # try looser
    i = text.find('id="addCardForm"')
    print('addCardForm snippet:', text[i:i+500])
    raise SystemExit('addCardForm start not found')

new_add = (
    '<form id="addCardForm" class="shot-form" hidden>'
    '<p class="cb-note" id="addSelectedBank" hidden></p>'
    '<label class="add-source-legacy" hidden>Источник<select id="addSource">'
    '<option value="bank">Мой банк</option>'
    '<option value="catalog">Учебный каталог</option>'
    '</select></label>'
)
text = text.replace(old_add, new_add, 1)

# After newBank label, add catalog toggle button if missing
if 'id="openCatalogSource"' not in text:
    text = text.replace(
        '<button class="confirm" id="saveNewCard" type="submit">Добавить карту</button>',
        '<button type="button" class="text-action" id="openCatalogSource">Учебный каталог</button>'
        '<button class="confirm" id="saveNewCard" type="submit">Добавить карту</button>',
        1,
    )

path.write_text(text, encoding='utf-8')
print('wallet.html patched')
