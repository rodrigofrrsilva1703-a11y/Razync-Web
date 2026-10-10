"""Servidor local: mesma API e interface, sem expor código ou configuração privada."""
import json
import os
from pathlib import Path
import secrets
import sys
import threading
import time
import urllib.request
import webbrowser

ROOT = Path(__file__).resolve().parents[1]
PRIVATE = ROOT / '.local'


def configure():
    PRIVATE.mkdir(exist_ok=True)
    config_file = PRIVATE / 'config.json'
    if not config_file.exists():
        config_file.write_text(json.dumps({
            'RAZYNC_ACCESS_TOKEN': secrets.token_urlsafe(32),
            'CERTIFICATES_MASTER_KEY': secrets.token_urlsafe(48),
            'GEMINI_API_KEY': '', 'GEMINI_FREE_TIER_CONFIRMED': '0',
            'GROQ_API_KEY': '', 'GROQ_FREE_TIER_CONFIRMED': '0',
            'GROQ_ZDR_CONFIRMED': '0', 'RAZYNC_AI_PRIMARY': 'gemini',
            'OPENROUTER_API_KEY': ''
        }, indent=2), encoding='utf-8')
    config = json.loads(config_file.read_text(encoding='utf-8'))
    for key, value in config.items():
        if isinstance(value, str) and value:
            os.environ.setdefault(key, value)
    os.environ['RAZYNC_DB_PATH'] = str(PRIVATE / 'razync.db')
    os.environ['RAZYNC_AI_LEGACY_GEMINI'] = '0'
    if (PRIVATE / 'tessdata' / 'por.traineddata').exists():
        os.environ['TESSDATA_PREFIX'] = str(PRIVATE / 'tessdata')
    # Diretório privado não é servido pelo navegador.
    for candidate in [Path(os.environ.get('LOCALAPPDATA', '')) / 'Programs/Tesseract-OCR',
                      Path('C:/Program Files/Tesseract-OCR')]:
        if (candidate / 'tesseract.exe').exists():
            os.environ['PATH'] = str(candidate) + os.pathsep + os.environ.get('PATH', '')
            break


def create_app():
    from fastapi.responses import FileResponse
    from fastapi.staticfiles import StaticFiles
    from app.main import app
    @app.get('/', include_in_schema=False)
    def index():
        return FileResponse(ROOT / 'index.html', headers={'Cache-Control': 'no-store'})
    app.mount('/assets', StaticFiles(directory=ROOT / 'assets'), name='local-assets')
    return app


def open_when_ready():
    for _ in range(60):
        try:
            with urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=1) as response:
                if response.status == 200:
                    webbrowser.open('http://127.0.0.1:8000/')
                    return
        except OSError:
            time.sleep(1)


if __name__ == '__main__':
    configure()
    try:
        with urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=1) as response:
            existing = json.load(response)
        if (existing.get('service') == 'razync-web-api'
                and Path(existing.get('persistent_data', '')).resolve() == (PRIVATE / 'razync.db').resolve()):
            print('Razync local já está aberto.', flush=True)
            if '--no-browser' not in sys.argv:
                webbrowser.open('http://127.0.0.1:8000/')
            sys.exit(0)
    except (OSError, ValueError):
        pass
    sys.path.insert(0, str(ROOT / 'backend'))
    import uvicorn
    if '--no-browser' not in sys.argv:
        threading.Thread(target=open_when_ready, daemon=True).start()
    print('Razync local: http://127.0.0.1:8000/ — feche com Ctrl+C.', flush=True)
    uvicorn.run(create_app(), host='127.0.0.1', port=8000)
