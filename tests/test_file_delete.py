import json
import threading
import urllib.request
import urllib.error
from http.server import ThreadingHTTPServer
import pytest
from safety_report import server


def test_delete_file_cleans_current_evidence_and_preserves_history(tmp_path, monkeypatch):
    monkeypatch.setattr(server,'DATA',tmp_path)
    http=ThreadingHTTPServer(('127.0.0.1',0),server.Handler)
    thread=threading.Thread(target=http.serve_forever,daemon=True);thread.start()
    root=f'http://127.0.0.1:{http.server_port}'
    def req(path,data=None,raw=None):
        body=raw if raw is not None else json.dumps(data).encode() if data is not None else None
        with urllib.request.urlopen(urllib.request.Request(root+path,data=body),timeout=5) as res:return json.load(res)
    try:
        pid=req('/api/projects',{'name':'文件删除回归'})['id'];route='/api/projects/'+pid;t=tmp_path/pid
        fid=req(route+'/upload?name=sample.txt',raw='测试资料'.encode())['file_id']
        other=req(route+'/upload?name=other.txt',raw='保留资料'.encode())['file_id']
        state=server.load(t/'state.json');f=state['files'][0]
        # Excluded files must also be deletable.
        req(route+'/files',{'id':fid,'active':False})
        server.save(t/'analysis.json',{'chunks':[{'id':'e1','source':'sample.txt','sha256':f['sha256']}]})
        server.state_update(t,fields=[{'key':'company','value':'旧值','confirmed':True,'candidates':[{'value':'旧值','evidence_id':'e1','source':'sample.txt'}]}])
        for name in ('node-checkpoints.json','preflight-checkpoints.json'):server.save(t/name,{})
        index=t/'knowledge/qdrant';index.mkdir(parents=True);(index/'cached').write_text('old')
        history=t/'versions/saved';history.mkdir(parents=True);(history/'report.json').write_text('historical snapshot')
        server.save(t/'report.json',{'snapshot':'old'})
        server.state_update(t,busy=True)
        with pytest.raises(urllib.error.HTTPError):req(route+'/delete-file',{'id':fid,'confirm_name':'sample.txt'})
        server.state_update(t,busy=False)
        with pytest.raises(urllib.error.HTTPError):req(route+'/delete-file',{'id':fid,'confirm_name':'wrong'})
        assert (t/'uploads'/f['stored']).exists()
        req(route+'/delete-file',{'id':fid,'confirm_name':'sample.txt'})
        now=server.load(t/'state.json')
        assert [x['id'] for x in now['files']]==[other]
        assert now['analysis_dirty'] and now['report_outdated'] and now['chunk_count']==0
        assert now['fields'][0]['value']=='' and not now['fields'][0]['confirmed']
        assert not (t/'uploads'/f['stored']).exists() and not (t/'analysis.json').exists()
        assert not index.exists() and not (t/'node-checkpoints.json').exists()
        assert (history/'report.json').read_text()=='historical snapshot'
        assert server.load(t/'report.json')=={'snapshot':'old'}
        with pytest.raises(urllib.error.HTTPError):req(route+'/files/'+fid+'/download')
        with pytest.raises(urllib.error.HTTPError):req(route+'/delete-file',{'id':fid,'confirm_name':'sample.txt'})
        req(route+'/delete-files',{'files':[{'id':other,'confirm_name':'other.txt'}]})
        assert server.load(t/'state.json')['files']==[]
    finally:
        http.shutdown();http.server_close();thread.join(timeout=5)


def test_bulk_delete_validates_entire_selection_before_changes(tmp_path):
    target=tmp_path/'project';(target/'uploads').mkdir(parents=True)
    files=[{'id':str(i),'name':f'{i}.txt','stored':f'{i}.txt','sha256':str(i),'size':1,'active':i==0,'role':'source'} for i in range(3)]
    server.save(target/'state.json',{'files':files,'fields':[],'busy':False,'data_revision':4})
    for f in files:(target/'uploads'/f['stored']).write_text('data')
    invalid=[{'id':'0','confirm_name':'0.txt'},{'id':'1','confirm_name':'wrong'}]
    with pytest.raises(ValueError,match='名称不匹配'):
        server.delete_project_file(target,{'files':invalid})
    assert len(server.load(target/'state.json')['files'])==3
    assert all((target/'uploads'/f['stored']).exists() for f in files)
    with pytest.raises(ValueError):server.delete_project_file(target,{'files':[]})
    request=[{'id':f['id'],'confirm_name':f['name']} for f in files]
    server.delete_project_file(target,{'files':request})
    state=server.load(target/'state.json')
    assert state['files']==[] and state['data_revision']==5
    assert list((target/'uploads').iterdir())==[]
