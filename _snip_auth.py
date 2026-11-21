from pathlib import Path
t = Path('wallet.html').read_text(encoding='utf-8')
for key in ['async function checkAuth', "authForm').addEventListener", 'function syncWalletRoute', 'carouselControls', 'id="authScreen"', 'id="welcomeScreen"']:
    i = t.find(key)
    print('====', key, i)
    print(t[i:i+650])
    print()
