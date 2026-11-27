import hashlib
import json
import threading
from concurrent.futures import ThreadPoolExecutor
from http.server import ThreadingHTTPServer
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from xml.sax.saxutils import escape
from zipfile import ZipFile

import pytest

from safety_report import server
from safety_report.documents import parse_file
from safety_report.import_identity import document_keys, joined_blocks
from safety_report.knowledge import KnowledgeBase


LAW = '中华人民共和国测试安全法\n（2021年6月10日会议通过）\n第一章 总则\n第一条 '+ '依法进行安全生产管理，明确人员职责。'*25+'\n第二条 '+ '设备运行时应当核查设计参数和安全条件。'*25


def payloads(parsed, filename='测试法.txt'):
    return [dict(category='regulation', title=f"{filename} · {c['locator']} · {c['offset']}",
                 content=c['text'], source=filename) for c in parsed['chunks']]


def imported(kb, path):
    parsed = parse_file(path)
    return kb.import_chunks(payloads(parsed, path.name), parsed['sha256'], joined_blocks(parsed))


def test_renamed_and_cross_format_law_matches_existing_approved_record(tmp_path):
    kb = KnowledgeBase(tmp_path/'kb.json')
    r = kb.create(dict(category='regulation', title='已有测试法', content=LAW, source='已有法规文件', validity_status='current'))
    kb.set_status(r['id'], 'approved', '测试审核人')
    before = kb.path.read_bytes()
    file = tmp_path/'改名.docx'
    with ZipFile(file, 'w') as z:
        z.writestr('word/document.xml', '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>'+''.join('<w:p><w:r><w:t>'+escape(line)+'</w:t></w:r></w:p>' for line in LAW.splitlines())+'</w:body></w:document>')
    result = imported(kb, file)
    assert result['duplicate'] and result['count'] == 0 and result['existing_id'] == r['id']
    assert kb.path.read_bytes() == before
    changed = tmp_path/'同名法规新版本.txt'; changed.write_text(LAW.replace('设备运行时', '设备运行前后'), encoding='utf-8')
    assert not imported(kb, changed)['duplicate']


def test_reconstructs_existing_legacy_chunks_and_ignores_download_wrapper(tmp_path):
    text = LAW+'\n第三条 '+'落实安全措施。'*700
    file = tmp_path/'老法规.txt'; file.write_text(text, encoding='utf-8')
    kb = KnowledgeBase(tmp_path/'kb.json'); parsed = parse_file(file)
    kb.create_many(payloads(parsed, file.name))
    before = len(kb.list())
    wrapped = tmp_path/'新文件名.txt'
    wrapped.write_text('样稿引用：测试法\n来源：https://example.gov.cn/law\n采集日期：2026-11-27\n\n'+text.replace('安全措施', '安全 措施'), encoding='utf-8')
    assert imported(kb, wrapped)['duplicate'] and len(kb.list()) == before


def test_partial_delete_only_restores_missing_chunks_and_full_delete_allows_reimport(tmp_path):
    file = tmp_path/'法规.txt'; file.write_text(LAW+'\n第三条 '+'核查输入参数。'*700, encoding='utf-8')
    kb = KnowledgeBase(tmp_path/'kb.json'); first = imported(kb, file)
    ids = first['record_ids']; assert len(ids) >= 3
    kb.delete(ids[1], 1)
    result = imported(kb, file)
    assert not result['duplicate'] and result['count'] == 1 and result['skipped'] == len(ids)-1
    assert len(kb.list()) == len(ids)
    for record in kb.list(): kb.delete(record['id'], record['revision'])
    assert imported(kb, file)['count'] == len(ids)


def test_simultaneous_imports_create_only_one_copy(tmp_path):
    file = tmp_path/'法规.txt'; file.write_text(LAW, encoding='utf-8')
    parsed = parse_file(file); kb = KnowledgeBase(tmp_path/'kb.json')
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: kb.import_chunks(payloads(parsed), parsed['sha256'], joined_blocks(parsed)), range(2)))
    assert sum(r['duplicate'] for r in results) == 1
    assert len(kb.list()) == len(parsed['chunks'])


def test_identity_does_not_merge_numeric_columns_or_project_report_with_law_appendix():
    assert not document_keys('参数：1 2').intersection(document_keys('参数：12'))
    assert not document_keys('项目名称：生产线\n建设单位：测试公司\n'+LAW).intersection(document_keys(LAW))


def test_http_upload_checks_project_and_existing_law_library(tmp_path, monkeypatch):
    monkeypatch.setattr(server, 'DATA', tmp_path); monkeypatch.setenv('APP_PASSWORD', '')
    http = ThreadingHTTPServer(('127.0.0.1', 0), server.Handler)
    thread = threading.Thread(target=http.serve_forever, daemon=True); thread.start()
    base = f'http://127.0.0.1:{http.server_port}'

    def request(path, data=None, raw=None):
        body = raw if raw is not None else json.dumps(data).encode() if data is not None else None
        with urlopen(Request(base+path, data=body), timeout=15) as response: return json.load(response)

    try:
        law = request('/api/knowledge/import?'+urlencode({'filename':'法规.txt','category':'regulation'}), raw=LAW.encode())
        assert law['count'] > 0 and not law['duplicate']
        duplicate = request('/api/knowledge/import?'+urlencode({'filename':'改名.txt','category':'hazard'}), raw=LAW.encode())
        assert duplicate['duplicate'] and duplicate['count'] == 0
        p = request('/api/projects', {'name':'上传判重测试'}); route='/api/projects/'+p['id']
        duplicate = request(route+'/upload?'+urlencode({'name':'已有法规.txt'}), raw=LAW.encode())
        assert duplicate['knowledge_duplicate'] and not request(route)['files']
        first = request(route+'/upload?name=one.txt&role=source', raw='项目名称：项目甲'.encode())
        duplicate = request(route+'/upload?name=renamed.txt&role=reference', raw='项目名称：项目甲'.encode())
        assert duplicate['duplicate'] and duplicate['file_id'] == first['file_id']
        duplicate = request(route+'/upload?name=spacing.txt', raw='项目名称： 项目甲\n'.encode())
        assert duplicate['duplicate'] and len(request(route)['files']) == 1
        changed = request(route+'/upload?name=one.txt', raw='项目名称：项目乙'.encode())
        assert not changed.get('duplicate') and len(request(route)['files']) == 2
    finally:
        http.shutdown(); http.server_close(); thread.join(timeout=5); server.close_knowledge_stores(tmp_path)
