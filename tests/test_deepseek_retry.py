from unittest.mock import patch
from safety_report import provider

def test_deepseek_truncation_retries_once_without_thinking():
    config={'provider':'deepseek','base_url':'https://api.deepseek.com','model':'deepseek-flash','api_key':'test-key','json_mode':True}
    calls=[]
    def response(config,path,body,**kwargs):
        calls.append(dict(body))
        if len(calls)==1:return {'choices':[{'finish_reason':'length','message':{'content':''}}]}
        return {'choices':[{'finish_reason':'stop','message':{'content':'{"ok":true}'}}]}
    with patch('safety_report.provider.request_json',side_effect=response):
        assert provider.complete_json('test',{},config)=={'ok':True}
    assert calls[0]['reasoning_effort']=='low'
    assert calls[1]['thinking']=={'type':'disabled'} and 'reasoning_effort' not in calls[1]
