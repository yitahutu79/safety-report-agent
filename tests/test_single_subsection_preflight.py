import threading
from unittest.mock import patch
import pytest
from safety_report import server,provider,pipeline
from safety_report.node_checkpoint import NodeCheckpoint


def test_materials_checks_resume_each_completed_subsection(tmp_path,monkeypatch):
    server.save(tmp_path/'state.json',{'id':'test','report_type':'facility_design','files':[]})
    server.save(tmp_path/'analysis.json',{'chunks':[{'id':'e1','source':'测试','locator':'1','text':'工艺通风要求。'}]})
    monkeypatch.setattr(server,'template_compatible_report',lambda _: {'sections':[{'title':'2 概况','subheadings':['2.1 工艺','2.1.1 通风'],'paragraphs':[],'tables':[]}]})
    calls=[];fail=[True]
    def plan(chapter,section,evidence,model,**kwargs):
        assert len(section['subheadings'])==1
        heading=section['subheadings'][0];calls.append(heading)
        if heading=='2.1.1 通风' and fail[0]:fail[0]=False;raise provider.ModelOutputTruncated('模拟截断')
        return {'requests':[],'can_draft_now':True,'note':'测试'}
    monkeypatch.setattr(server,'plan_missing_materials',plan)
    path=tmp_path/'preflight.json'
    with pytest.raises(ValueError,match='2.1.1 通风'):server.chapter_materials_plan(tmp_path,'2',{},threading.Event(),checkpoint=NodeCheckpoint(path,{}))
    result=server.chapter_materials_plan(tmp_path,'2',{},threading.Event(),checkpoint=NodeCheckpoint(path,{}))
    assert calls==['2.1 工艺','2.1.1 通风','2.1.1 通风']
    assert result['checked_subsections']==2 and result['can_draft_now']


def test_materials_retry_is_bounded_and_marks_task_type():
    result={'requests':[],'can_draft_now':True,'note':''}
    with patch('safety_report.pipeline.complete_json',side_effect=[provider.ModelOutputTruncated('模拟'),result]) as call:
        assert pipeline.plan_missing_materials('2 概况',{'subheadings':['2.1 工艺']},[],{})==result
        assert call.call_count==2
        assert all(c.args[1]['task_type']=='materials_review' for c in call.call_args_list)
        assert [c.kwargs['max_tokens'] for c in call.call_args_list]==[2400,3200]
    with patch('safety_report.pipeline.complete_json',side_effect=provider.ModelOutputTruncated('模拟')) as call,pytest.raises(provider.ModelOutputTruncated):
        pipeline.plan_missing_materials('2 概况',{'subheadings':['2.1 工艺']},[],{})
    assert call.call_count==2


def test_deepseek_materials_check_disables_thinking_and_raises_specific_truncation():
    config={'base_url':'https://api.deepseek.com','model':'deepseek-v4-pro','api_key':'test'}
    with patch('safety_report.provider.request_json',return_value={'choices':[{'finish_reason':'length','message':{'content':'{'}}]}) as call:
        with pytest.raises(provider.ModelOutputTruncated):provider.complete_json('检查',{'task_type':'materials_review'},config,max_tokens=2400)
        assert call.call_count==1
        assert call.call_args.args[2]['thinking']=={'type':'disabled'}
