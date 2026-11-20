import json, threading, urllib.request, urllib.error
from http.server import ThreadingHTTPServer
import pytest
from safety_report import server

def test_project_recycle_guards_and_restore(tmp_path, monkeypatch):
    monkeypatch.setattr(server, 'DATA', tmp_path)
    http=ThreadingHTTPServer(('127.0.0.1',0),server.Handler)
    thread=threading.Thread(target=http.serve_forever,daemon=True);thread.start()
    root='http://127.0.0.1:'+str(http.server_port)
    def req(path,data=None):
        body=json.dumps(data).encode() if data is not None else None
        with urllib.request.urlopen(urllib.request.Request(root+path,data=body),timeout=5) as r:return json.load(r)
    try:
        project=req('/api/projects',{'name':'删除测试'});pid=project['id'];route='/api/projects/'+pid
        with pytest.raises(urllib.error.HTTPError):req(route+'/trash',{'name':'名称不符'})
        assert len(req('/api/projects'))==1
        server.state_update(tmp_path/pid,busy=True)
        with pytest.raises(urllib.error.HTTPError):req(route+'/trash',{'name':'删除测试'})
        server.state_update(tmp_path/pid,busy=False)
        (tmp_path/pid/'proof.txt').write_text('保留项目资料')
        req(route+'/trash',{'name':'删除测试'})
        assert req('/api/projects')==[] and req('/api/projects-trash')[0]['id']==pid
        with pytest.raises(urllib.error.HTTPError):req(route)
        req(route+'/restore-project',{})
        assert req('/api/projects')[0]['id']==pid
        assert (tmp_path/pid/'proof.txt').read_text()=='保留项目资料'
    finally:
        http.shutdown();http.server_close();thread.join(timeout=5)
