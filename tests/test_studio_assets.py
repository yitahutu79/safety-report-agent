"""The desktop/offline UI must serve its bundled design assets through the app server."""
import threading
from http.server import ThreadingHTTPServer
from urllib.request import urlopen
from xml.etree import ElementTree
from safety_report import server


def test_studio_assets_are_served_locally(tmp_path, monkeypatch):
    monkeypatch.setattr(server, 'DATA', tmp_path)
    http = ThreadingHTTPServer(('127.0.0.1', 0), server.Handler)
    thread = threading.Thread(target=http.serve_forever, daemon=True)
    thread.start()
    base = f'http://127.0.0.1:{http.server_port}'
    try:
        for route, content_type in [('/studio-ui.js', 'text/javascript'), ('/studio-ui.css', 'text/css'), ('/design-themes.js', 'text/javascript'), ('/design-themes.css', 'text/css')]:
            with urlopen(base + route, timeout=5) as response:
                assert response.status == 200
                assert response.headers.get_content_type() == content_type
                assert len(response.read()) > 100
        for name, mime in [('LXGWWenKai-Regular.ttf', 'font/ttf'), ('NotoSerifSC-Regular.otf', 'font/otf')]:
            with urlopen(base + '/fonts/' + name, timeout=5) as response:
                assert response.headers.get_content_type() == mime
                assert len(response.read()) > 100_000
        icons = list((server.ROOT / 'web' / 'ui-icons').glob('*.svg'))
        assert icons
        for icon in icons:
            with urlopen(base + '/ui-icons/' + icon.name, timeout=5) as response:
                assert response.headers.get_content_type() == 'image/svg+xml'
                assert ElementTree.fromstring(response.read()).tag.endswith('svg')
    finally:
        http.shutdown()
        http.server_close()
        thread.join()
