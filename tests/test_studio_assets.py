"""The desktop/offline UI must serve its bundled design assets through the app server."""
import threading
from html.parser import HTMLParser
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
        for route, content_type in [('/dialog-controls.js', 'text/javascript'), ('/dialog-controls.css', 'text/css'), ('/report-preview.js', 'text/javascript'), ('/component-experience.js', 'text/javascript'), ('/component-experience.css', 'text/css'), ('/vendor/daisyui-kbd.css', 'text/css'), ('/vendor/daisyui-badge.css', 'text/css'), ('/studio-ui.js', 'text/javascript'), ('/studio-ui.css', 'text/css'), ('/design-themes.js', 'text/javascript'), ('/design-themes.css', 'text/css')]:
            with urlopen(base + route, timeout=5) as response:
                assert response.status == 200
                assert response.headers.get_content_type() == content_type
                assert len(response.read()) > 100
        for name, mime in [('LXGWWenKai-Regular.ttf', 'font/ttf'), ('NotoSerifSC-Regular.otf', 'font/otf')]:
            with urlopen(base + '/fonts/' + name, timeout=5) as response:
                assert response.headers.get_content_type() == mime
                assert len(response.read()) > 100_000
        # Dependencies must execute before the app and editorial consumers can render.
        class Scripts(HTMLParser):
            def __init__(self):
                super().__init__()
                self.sources = []
            def handle_starttag(self, tag, attrs):
                values = dict(attrs)
                if tag == 'script' and values.get('src'):
                    assert 'defer' in values
                    self.sources.append(values['src'])
        scripts = Scripts()
        with urlopen(base + '/', timeout=5) as response:
            scripts.feed(response.read().decode())
        assert scripts.sources.index('/report-preview.js') < scripts.sources.index('/app.js')
        assert scripts.sources.index('/report-preview.js') < scripts.sources.index('/product-design.js')
        assert scripts.sources.index('/dialog-controls.js') > scripts.sources.index('/component-experience.js')
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
