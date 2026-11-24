import json,threading,urllib.request,urllib.error
from http.server import ThreadingHTTPServer
import pytest
from safety_report import server


def start(root,monkeypatch):
    monkeypatch.setattr(server,'ROOT',root)
    http=ThreadingHTTPServer(('127.0.0.1',0),server.Handler);thread=threading.Thread(target=http.serve_forever,daemon=True);thread.start()
    def get(query=''):
        with urllib.request.urlopen(f'http://127.0.0.1:{http.server_port}/api/test-record'+query,timeout=5) as r:return json.load(r)
    return http,thread,get


def test_shared_record_defaults_latest_and_history_is_verbatim(tmp_path,monkeypatch):
    docs=tmp_path/'docs';docs.mkdir();latest='# 最新测试\n2026-11-24：自动化测试通过。';history='# 全流程历史\n2026-11-17：真实调用未通过，不等同验收。\n2026-11-23：后续复测。'
    (docs/'TESTING.md').write_text(latest);(docs/'全流程测试记录-2026-11-17.md').write_text(history)
    http,thread,get=start(tmp_path,monkeypatch)
    try:
        data=get();assert data['content']==latest and data['record']=='latest' and data['updated_at']=='2026-11-24'
        assert len(data['records'])==2
        old=get('?record=history');assert old['content']==history and old['source']=='全流程测试记录-2026-11-17.md' and old['updated_at']=='2026-11-23'
        with pytest.raises(urllib.error.HTTPError) as e:get('?record=../../.env')
        assert e.value.code==400
    finally:http.shutdown();http.server_close();thread.join(timeout=5)


def test_shared_record_fallback_and_missing_files_are_explicit(tmp_path,monkeypatch):
    docs=tmp_path/'docs';docs.mkdir();(docs/'全流程测试记录-2026-11-17.md').write_text('历史记录 2026-11-17')
    http,thread,get=start(tmp_path,monkeypatch)
    try:
        assert get()['record']=='history'
        (docs/'全流程测试记录-2026-11-17.md').unlink()
        with pytest.raises(urllib.error.HTTPError) as e:get()
        assert e.value.code==404
    finally:http.shutdown();http.server_close();thread.join(timeout=5)
