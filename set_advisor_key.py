"""Save the local AITunnel key without putting it in shell history."""
import getpass
import os
import re
import tempfile
import warnings
from pathlib import Path


KEY = 'ADVISOR_API_KEY'
ENTRY = re.compile(r'^[ \t]*ADVISOR_API_KEY[ \t]*=')


def save_key(path: Path, key: str) -> None:
    if not re.fullmatch(r"[!-~]+", key) or any(char in key for char in "\"'"):
        raise ValueError('Ключ пустой или содержит недопустимые символы.')
    try:
        existing = path.read_bytes().decode('utf-8-sig')
    except FileNotFoundError:
        existing = ''
    newline = '\r\n' if '\r\n' in existing else '\n'
    lines = [line for line in existing.splitlines(keepends=True) if not ENTRY.match(line)]
    text = ''.join(lines)
    if text and not text.endswith(('\r', '\n')):
        text += newline
    text += f'{KEY}={key}{newline}'
    pending = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix='.env.', delete=False) as output:
            pending = Path(output.name)
            output.write(text.encode('utf-8'))
        os.replace(pending, path)
    finally:
        if pending is not None:
            pending.unlink(missing_ok=True)


if __name__ == '__main__':
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error', getpass.GetPassWarning)
            secret = getpass.getpass('Вставьте API-ключ AITunnel и нажмите Enter (ввод скрыт): ').strip()
        save_key(Path(__file__).resolve().with_name('.env'), secret)
    except (KeyboardInterrupt, EOFError, getpass.GetPassWarning):
        raise SystemExit('Ключ не сохранён. Запустите скрипт в обычном терминале.') from None
    except ValueError as error:
        raise SystemExit(str(error) if type(error) is ValueError else 'Не удалось прочитать существующий .env.') from None
    except OSError:
        raise SystemExit('Не удалось записать локальный .env. Проверьте доступ к папке проекта.') from None
    print('Ключ сохранён в локальный .env.')
    if os.environ.get(KEY, '').strip():
        print('В окружении уже задан ADVISOR_API_KEY: уберите его и перезапустите сервер, чтобы он использовал .env.')
