import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import pytest
from safety_report.provider import request_json, ModelDeadlineExceeded
from safety_report.agent_graph import run_chapter_graph


def test_slow_stream_has_total_deadline_without_cancel_event():
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args): pass
        def do_POST(self):
            self.send_response(200)
            self.send_header('Content-Type', 'text/event-stream')
            self.end_headers()
            try:
                for _ in range(50):
                    self.wfile.write(b'data: {"choices":[{"delta":{"content":"x"}}]}\n\n')
                    self.wfile.flush()
                    time.sleep(.03)
            except (BrokenPipeError, ConnectionResetError): pass
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
    start = time.monotonic()
    try:
        with pytest.raises(ModelDeadlineExceeded):
            request_json({'base_url':f'http://127.0.0.1:{server.server_port}', 'model':'transport-test'}, '/chat/completions', {'stream':True}, timeout=.15)
        assert time.monotonic() - start < 1
    finally:
        server.shutdown();server.server_close()


def test_local_single_heading_also_uses_bounded_writer():
    calls=[]
    def complete(system, payload, model, **kw):
        if '资料规划 Agent' in system: return {'queries': []}
        if '安全生产报告的审稿人员' in system: return {'issues': []}
        calls.append((payload, kw))
        return {'paragraphs':[], 'tables':[], 'missing':['缺少资料'], 'review':[]}
    run_chapter_graph('写作', {'chapter':'2 概况','required_subsections':['2.1 单位'],'evidence':[]},
        {'provider':'ollama','base_url':'http://127.0.0.1:11434/v1'},search=lambda q:[],validate=lambda d:[],complete=complete)
    assert calls[0][0]['target_subsections'] == ['2.1 单位']
    assert calls[0][1]['max_tokens'] == 2000
