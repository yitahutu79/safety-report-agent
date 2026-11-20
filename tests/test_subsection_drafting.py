import pytest
from safety_report.agent_graph import group_subsections, run_chapter_graph
from safety_report.node_checkpoint import NodeCheckpoint
from safety_report.gptr_bm25 import rank_written_sections


def test_group_respects_parent_order_and_size():
    headings=['2.1 项目','2.1.1 单位','2.1.2 规模','2.1.3 地点','2.2 工艺','2.2.1 设备']
    assert group_subsections(headings)==[headings[:3],headings[3:4],headings[4:]]


def test_resume_incomplete_second_subsection_without_rewriting_first(tmp_path):
    calls=[]; failures=[2]
    evidence=[{'id':'e1','source':'模拟文件','locator':'1','text':'车间采用机械通风。'}, {'id':'e2','source':'模拟文件','locator':'2','text':'车间使用水性清洗剂。'}]
    def complete(system,payload,model,**kw):
        if '资料规划 Agent' in system: return {'queries':[]}
        if '资料筛选 Agent' in system: return {'sources':[{'id':x['id'],'decision':'use','reason':'相关'} for x in payload['sources']]}
        if '安全生产报告的审稿人员' in system:return {'issues':[]}
        group=payload['target_subsections'];calls.append(group[0])
        if group[0]=='2.2 工艺' and failures[0]:
            failures[0]-=1;raise ValueError('模拟截断')
        return {'editorial_plan':[], 'paragraphs':[{'heading':group[0],'text':'仅根据虚构证据编写。','evidence_ids':['e1']}], 'tables':[], 'missing':[], 'review':[]}
    args=dict(system='写作要求',payload={'chapter':'2 项目概况','required_subsections':['2.1 通风','2.2 工艺'],'evidence':evidence},model={},search=lambda q:[],validate=lambda d:[],complete=complete)
    path=tmp_path/'cache.json'
    with pytest.raises(ValueError,match='模拟截断'):
        run_chapter_graph(**args,checkpoint=NodeCheckpoint(path,{'project':'x'}))
    progress=[]
    result=run_chapter_graph(**args,checkpoint=NodeCheckpoint(path,{'project':'x'}),on_progress=progress.append)
    assert calls==['2.1 通风','2.2 工艺','2.2 工艺','2.2 工艺']
    assert [p['heading'] for p in result['paragraphs']]==['2.1 通风','2.2 工艺']
    assert any('已恢复小节 1/2' in msg for msg in progress)


def test_written_context_reuses_gptr_chinese_bm25():
    sections=[{'section_title':'消防水系统','written_content':'消防水泵设置在泵房。'}, {'section_title':'车间通风','written_content':'车间设置机械通风。'}]
    matches=rank_written_sections('机械通风车间',sections)
    assert matches and '通风' in matches[0]


def test_subsection_rejects_unknown_evidence_and_never_persists_invalid_output(tmp_path):
    evidence=[{'id':'e1','source':'模拟','locator':'1','text':'机械通风'}]
    calls=[]
    def complete(system,payload,model,**kw):
        if '资料规划 Agent' in system:return {'queries':[]}
        if '资料筛选 Agent' in system:return {'sources':[{'id':'e1','decision':'use','reason':'相关'}]}
        calls.append('draft')
        return {'paragraphs':[{'heading':payload['target_subsections'][0], 'text':'不应保存', 'evidence_ids':['unknown']}], 'tables':[], 'missing':[], 'review':[]}
    path=tmp_path/'nodes.json'
    with pytest.raises(ValueError, match='未提供的证据'):
        run_chapter_graph('写作',{'chapter':'2 概况','required_subsections':['2.1 通风','2.2 工艺'],'evidence':evidence},{},search=lambda q:[],validate=lambda d:[],complete=complete,checkpoint=NodeCheckpoint(path,{}))
    assert calls==['draft','draft']
    assert '不应保存' not in path.read_text()
