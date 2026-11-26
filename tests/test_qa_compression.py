from safety_report import knowledge_qa

def test_model_receives_ranked_short_evidence_preserving_source_fields():
    paragraphs=['项目名称：示例机械加工项目。','法定代表人：示例姓名 联系电话：13800138000 身份证：123456789012345678',
                '建设规模：车间年加工零件10000件。']+['无关背景信息。'*20 for _ in range(8)]
    original='\n'.join(paragraphs)
    evidence=[{'id':'original-id','source':'备案.pdf','locator':'page[1]','text':original}]
    captured={}
    def complete(system,payload,config,**kwargs):
        captured.update(payload)
        return {'paragraphs':[{'text':'资料描述了项目规模。','evidence_ids':['original-id']}],'missing':[]}
    answer=knowledge_qa.answer_question('项目名称和建设规模是什么？',evidence,{},complete=complete)
    sent=captured['evidence'][0]['text']
    assert len(sent)<len(original)
    assert '13800138000' in sent and '123456789012345678' in sent
    assert evidence[0]['text']==original
    assert '示例机械加工项目' in sent and '10000件' in sent
    assert answer['sources'][0]['id']=='original-id' and answer['sources'][0]['text']==sent
