import json, threading, urllib.request, urllib.error
from http.server import ThreadingHTTPServer
import pytest
from safety_report import server

def test_acknowledgement_preserves_versions_and_rejects_stale_error(tmp_path, monkeypatch):
    monkeypatch.setattr(server,'DATA',tmp_path)
    http=ThreadingHTTPServer(('127.0.0.1',0),server.Handler)
    thread=threading.Thread(target=http.serve_forever,daemon=True);thread.start()
    base='http://127.0.0.1:'+str(http.server_port)
    def request(path,data=None):
        body=json.dumps(data).encode() if data is not None else None
        with urllib.request.urlopen(urllib.request.Request(base+path,data=body),timeout=5) as r:return json.load(r)
    try:
        project=request('/api/projects',{'name':'错误提示测试'});pid=project['id'];route='/api/projects/'+pid
        server.state_update(tmp_path/pid,error='先前模型错误',report_version='protected-version')
        with pytest.raises(urllib.error.HTTPError):request(route+'/ack-error',{'expected_error':'过期错误'})
        assert request(route)['error']=='先前模型错误'
        assert request(route+'/ack-error',{'expected_error':'先前模型错误'})['ok']
        state=request(route)
        assert state['error']=='' and state['last_acknowledged_error']=='先前模型错误'
        assert state['report_version']=='protected-version'
    finally:http.shutdown();http.server_close();thread.join(timeout=5)
