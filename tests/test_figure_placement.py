import hashlib
import zipfile
import pytest
from PIL import Image
from safety_report import assets
from safety_report.word import write_docx


def h(text): return hashlib.sha256(text.encode()).hexdigest()


def report():
    return {'confirmed_fields': [], 'sections': [
        {'title':'1 设计依据','subheadings':['1.1 范围'], 'paragraphs':[{'heading':'1.1 范围','text':'第一段内容'}, {'heading':'1.1 范围','text':'第二段内容'}], 'tables':[]},
        {'title':'2 项目概况','subheadings':[], 'paragraphs':[{'heading':'2 项目概况','text':'第三段内容'}], 'tables':[]}]}


def make(root, title, placement):
    path=root/(title+'.png'); Image.new('RGB',(40,30),'blue').save(path)
    return {'path':str(path), 'caption':title, 'source':'合成测试', 'placement':placement}


def test_placed_after_paragraph_chapter_end_and_appendix(tmp_path):
    doc=report(); figures=[
        make(tmp_path,'图A',{'section_id':'1','paragraph_index':0,'paragraph_hash':h('第一段内容')}),
        make(tmp_path,'图B',{'section_id':'1','paragraph_index':None}),
        make(tmp_path,'图C',{})]
    resolved,warnings=assets.resolve_figure_placements(doc,figures)
    assert not warnings
    output=tmp_path/'test.docx'; write_docx(doc,{},output,resolved)
    with zipfile.ZipFile(output) as z:
        xml=z.read('word/document.xml').decode()
        assert xml.index('第一段内容') < xml.index('图A') < xml.index('第二段内容') < xml.index('图B') < xml.index('2 项目概况')
        assert xml.index('第三段内容') < xml.index('>项目图件<') < xml.index('图C')
        assert len([n for n in z.namelist() if n.startswith('word/media/image')]) == 3


def test_changed_or_missing_anchor_falls_back_and_warns(tmp_path):
    doc=report(); figures=[make(tmp_path,'图A',{'section_id':'1','paragraph_index':0,'paragraph_hash':h('旧内容')}),
                           make(tmp_path,'图B',{'section_id':'9','paragraph_index':None})]
    resolved,warnings=assets.resolve_figure_placements(doc,figures)
    assert len(warnings)==2 and all(not f['placement'] for f in resolved)
    assert '指定段落已变化' in warnings[0] and '指定章节不存在' in warnings[1]


def test_reordered_paragraph_tracks_unique_text(tmp_path):
    doc=report(); doc['sections'][0]['paragraphs'].reverse()
    figures=[make(tmp_path,'图A',{'section_id':'1','paragraph_index':0,'paragraph_hash':h('第一段内容')})]
    result,warnings=assets.resolve_figure_placements(doc,figures)
    assert not warnings and result[0]['placement']['paragraph_index']==1


def test_position_api_persists_hash_and_reports_stale(tmp_path, monkeypatch):
    import json, threading, urllib.request, urllib.error
    from http.server import ThreadingHTTPServer
    from safety_report import server
    monkeypatch.setattr(server, 'DATA', tmp_path)
    http = ThreadingHTTPServer(('127.0.0.1',0), server.Handler)
    worker = threading.Thread(target=http.serve_forever,daemon=True); worker.start()
    base=f'http://127.0.0.1:{http.server_port}'
    def request(path, data=None, raw=None):
        body=raw if raw is not None else json.dumps(data).encode() if data is not None else None
        with urllib.request.urlopen(urllib.request.Request(base+path,data=body),timeout=5) as response: return json.load(response)
    try:
        project=request('/api/projects',{'name':'图件位置测试'}); pid=project['id']; route='/api/projects/'+pid
        image=tmp_path/'sample.png';Image.new('RGB',(40,30),'blue').save(image)
        file=request(route+'/upload?name=sample.png&role=figure',raw=image.read_bytes())['file_id']
        path=tmp_path/pid; state=json.loads((path/'state.json').read_text()); state['report_version']='test-version'; (path/'state.json').write_text(json.dumps(state))
        doc=report();(path/'report.json').write_text(json.dumps(doc,ensure_ascii=False))
        request(route+'/files',{'id':file,'figure_placement':{'section_id':'1','paragraph_index':0},'figure_placement_base_version':'test-version'})
        result=request(route); saved=next(f for f in result['files'] if f['id']==file)
        assert saved['figure_placement']['paragraph_hash']==h('第一段内容')
        assert not saved['figure_placement_warning']
        doc['sections'][0]['paragraphs'][0]['text']='改写后的内容';(path/'report.json').write_text(json.dumps(doc,ensure_ascii=False))
        result=request(route); saved=next(f for f in result['files'] if f['id']==file)
        assert '指定段落已变化' in saved['figure_placement_warning']
        with pytest.raises(urllib.error.HTTPError) as error:
            request(route+'/files',{'id':file,'figure_placement':{'section_id':'1','paragraph_index':0},'figure_placement_base_version':'old-version'})
        assert error.value.code == 400
    finally:
        http.shutdown();http.server_close();worker.join(timeout=5)
