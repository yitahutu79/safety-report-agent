import copy,json,zipfile
from pathlib import Path
import xml.etree.ElementTree as ET
import pytest
from safety_report.table_reuse import read_table,compatible_layout,synchronize_merged_edits,insert_source_table,source_tables
from safety_report.documents import read_docx
from safety_report.word import table,write_docx
from safety_report.report_source import provided_report_draft

W='http://schemas.openxmlformats.org/wordprocessingml/2006/main'
NS={'w':W}

def element():
    return ET.fromstring('<w:tbl xmlns:w="'+W+'"><w:tblGrid>'+''.join('<w:gridCol w:w="1200"/>' for _ in range(3))+'</w:tblGrid><w:tr><w:trPr><w:tblHeader/></w:trPr><w:tc><w:tcPr><w:gridSpan w:val="2"/></w:tcPr><w:p><w:r><w:t>建筑与方位</w:t></w:r></w:p></w:tc><w:tc><w:p><w:r><w:t>距离</w:t></w:r></w:p></w:tc></w:tr><w:tr><w:tc><w:tcPr><w:vMerge w:val="restart"/></w:tcPr><w:p><w:r><w:t>1号车间</w:t></w:r></w:p></w:tc><w:tc><w:p><w:r><w:t>北</w:t></w:r></w:p></w:tc><w:tc><w:p><w:r><w:t>25.3</w:t></w:r></w:p></w:tc></w:tr><w:tr><w:tc><w:tcPr><w:vMerge/></w:tcPr><w:p/></w:tc><w:tc><w:p><w:r><w:t>西</w:t></w:r></w:p></w:tc><w:tc><w:p><w:r><w:t>17.5</w:t></w:r></w:p></w:tc></w:tr></w:tbl>')

def item():
    rows,layout=read_table(element())
    return {'id':'f:body[1]','caption':'周边间距表','source_file':'原报告.docx','source_file_id':'f','source_sha256':'h','source_locator':'body[1]','source_table_hash':'hash', 'headers':rows[0],'rows':rows[1:],'source_table_layout':layout,'text':'来源表格','reuse_supported':True}

def test_merged_cell_inheritance_keeps_each_distance_with_direction():
    t=item();assert t['rows']==[['1号车间','北','25.3'],['1号车间','西','17.5']]
    assert t['headers']==['建筑与方位','建筑与方位','距离']
    assert any(c['rowspan']==2 for c in t['source_table_layout']['cells'])
    xml=table(t['headers'],t['rows'],layout=t['source_table_layout']);root=ET.fromstring(xml.replace('<w:tbl>','<w:tbl xmlns:w="'+W+'">',1))
    assert root.find('.//w:gridSpan',NS).get('{'+W+'}val')=='2'
    assert len(root.findall('.//w:vMerge',NS))==2
    assert len(root.findall('w:tr',NS)[2].findall('w:tc',NS))==3
    assert xml.count('1号车间')==1 and '25.3' in xml and '17.5' in xml

def test_edit_anchor_propagates_to_merged_continuation_and_preserves_layout():
    old=item();new=copy.deepcopy(old);new['rows'][0][0]='2号车间'
    updated=synchronize_merged_edits(old,new)
    assert updated['rows'][1][0]=='2号车间' and compatible_layout(updated)
    conflict=copy.deepcopy(old);conflict['rows'][1][0]='另一座建筑'
    with pytest.raises(ValueError):synchronize_merged_edits(old,conflict)
    added=copy.deepcopy(old);added['rows'].append(['新建筑','东','12'])
    assert 'source_table_layout' not in synchronize_merged_edits(old,added)

def test_invalid_layout_is_not_rendered_as_merged_cells():
    t=item();t['source_table_layout']['cells'][0]['rowspan']=999
    assert compatible_layout(t) is None

def test_insert_only_target_chapter_and_guard_duplicate_and_heading():
    report={'sections':[{'title':'1 依据','subheadings':['1.1 文件'],'paragraphs':[],'tables':[]},{'title':'2 概况','subheadings':['2.1 布置'],'paragraphs':[],'tables':[]}],'evidence':[]}
    result=insert_source_table(report,item(),'2','2.1 布置')
    assert result['sections'][0]==report['sections'][0] and not report['sections'][1]['tables']
    assert result['sections'][1]['tables'][0]['source_table_layout']==item()['source_table_layout']
    assert result['evidence'][0]['locator']=='body[1]' and result['updated_chapters']==['2']
    with pytest.raises(ValueError):insert_source_table(result,item(),'2','2.1 布置')
    with pytest.raises(ValueError):insert_source_table(report,item(),'2','其他小节')
    with pytest.raises(ValueError):insert_source_table(report,{**item(),'reuse_supported':False},'2','2.1 布置')

def test_word_parser_and_confirmed_report_reuse_keep_native_geometry(tmp_path):
    path=tmp_path/'source.docx';heading='<w:p><w:pPr><w:outlineLvl w:val="1"/></w:pPr><w:r><w:t>2.1 布置</w:t></w:r></w:p>'
    with zipfile.ZipFile(path,'w') as z:z.writestr('word/document.xml','<w:document xmlns:w="'+W+'"><w:body>'+heading+ET.tostring(element(),encoding='unicode')+'</w:body></w:document>')
    blocks,_=read_docx(path)
    assert blocks[1]['table_layout']['cells']==item()['source_table_layout']['cells']
    a={'confirmed_report_sources':[{'id':'f','sha256':'h','name':'原报告'}],'documents':[{'sha256':'h','blocks':blocks}]}
    draft=provided_report_draft(a,['2.1 布置']);assert draft['tables'][0]['source_table_layout']==blocks[1]['table_layout']
    f={'id':'f','name':'source.docx','stored':'source.docx','sha256':'h','role':'source'}
    (tmp_path/'uploads').mkdir();(tmp_path/'uploads'/'source.docx').write_bytes(path.read_bytes())
    assert source_tables(tmp_path,[f])[0]['headers']==item()['headers']
    assert source_tables(tmp_path,[{**f,'active':False}])==[]

def test_table_insertion_into_ungenerated_chapter_exports_table_but_keeps_missing_notice(tmp_path):
    report={'confirmed_fields':[],'sections':[{'title':'2 概况','subheadings':['2.1 布置'],'generation_status':'not_generated','paragraphs':[],'tables':[]}]}
    result=insert_source_table(report,item(),'2','2.1 布置');out=tmp_path/'out.docx';write_docx(result,{},out)
    with zipfile.ZipFile(out) as z:
        text=z.read('word/document.xml').decode();assert '<w:vMerge' in text and '本章尚未生成' in text


def test_source_table_http_reuse_saves_version_and_rejects_locked_or_stale(tmp_path,monkeypatch):
    import threading,urllib.request,urllib.error
    from http.server import ThreadingHTTPServer
    from safety_report import server
    monkeypatch.setattr(server,'DATA',tmp_path)
    http=ThreadingHTTPServer(('127.0.0.1',0),server.Handler);thread=threading.Thread(target=http.serve_forever,daemon=True);thread.start()
    def req(path,data=None):
        body=json.dumps(data).encode() if data is not None else None
        with urllib.request.urlopen(urllib.request.Request(f'http://127.0.0.1:{http.server_port}'+path,data=body),timeout=5) as res:return json.load(res)
    try:
        pid=req('/api/projects',{'name':'原表接口回归'})['id'];target=tmp_path/pid;route='/api/projects/'+pid
        f={'id':'f','name':'source.docx','stored':'source.docx','sha256':'h','role':'source','active':True,'renderable':False,'size':1}
        with zipfile.ZipFile(target/'uploads'/'source.docx','w') as z:z.writestr('word/document.xml','<w:document xmlns:w="'+W+'"><w:body>'+ET.tostring(element(),encoding='unicode')+'</w:body></w:document>')
        report={'confirmed_fields':[],'sections':[{'title':'2 概况','subheadings':['2.1 布置'],'paragraphs':[],'tables':[],'missing':[],'review':[]}],'evidence':[]}
        server.state_update(target,files=[f],report_version='base');server.save(target/'report.json',report);write_docx(report,{},target/'report.docx')
        t=req(route+'/source-tables')['tables'][0]
        data={'base_version':'base','file_id':'f','table_id':t['id'],'source_table_hash':t['source_table_hash'],'section_id':'2','heading':'2.1 布置'}
        server.save(target/'chapter-workflow.json',{'chapters':{'2':{'locked':True}}})
        with pytest.raises(urllib.error.HTTPError):req(route+'/reuse-source-table',data)
        server.save(target/'chapter-workflow.json',{})
        with pytest.raises(urllib.error.HTTPError):req(route+'/reuse-source-table',{**data,'source_table_hash':'stale'})
        saved=req(route+'/reuse-source-table',data)
        assert saved['version']!='base'
        stored=server.load(target/'report.json');assert len(stored['sections'][0]['tables'])==1
        with zipfile.ZipFile(target/'report.docx') as z:assert b'<w:vMerge' in z.read('word/document.xml')
        with pytest.raises(urllib.error.HTTPError):req(route+'/reuse-source-table',data)
        with pytest.raises(urllib.error.HTTPError):req(route+'/reuse-source-table',{**data,'base_version':saved['version']})
    finally:http.shutdown();http.server_close();thread.join(timeout=5)


def test_old_flat_reused_table_is_replaced_without_duplicate_but_human_edits_are_kept():
    old=item();flat={'heading':'2.1 布置','headers':old['headers'],'rows':old['rows'],'caption':'旧表','evidence_ids':['e'],'report_source_reused':True}
    report={'sections':[{'title':'2 概况','subheadings':['2.1 布置'],'paragraphs':[],'tables':[flat]}],'evidence':[{'id':'e','source':old['source_file'],'locator':old['source_locator']}]}
    new=insert_source_table(report,old,'2','2.1 布置')
    assert len(new['sections'][0]['tables'])==1 and new['sections'][0]['tables'][0]['source_table_layout']
    flat['human_edited']=True
    with pytest.raises(ValueError):insert_source_table(report,old,'2','2.1 布置')
