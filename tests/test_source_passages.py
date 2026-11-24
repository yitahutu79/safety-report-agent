from safety_report.source_passages import paragraph_spans,extraction_passages
from safety_report.project_intake import automatic_candidates
from safety_report.structured_data import update_record


def test_pdf_soft_wrap_keeps_storage_paragraph_and_next_section_separate():
    storage='按照当地法规要求来储存。在许可的区域隔离储存。储存于原装容器中，防止直\n接光照，置于干燥、凉爽和通风良好的区域。存放处须加锁。\n使用容器前，保持容器关紧与密封。请参见第10节所规定的禁忌物料。'
    block={'locator':'page[8]','kind':'paragraph','text':'卫生注意事项。\n'+storage+'\n:\n一般职业卫生建议\n穿戴适当防护用品。'}
    spans=paragraph_spans(block);match=next(s for s in spans if s.startswith('按照当地法规'))
    assert match==storage and '一般职业卫生建议' not in match
    analysis={'documents':[{'sha256':'h','blocks':[block]}],'chunks':[]}
    records,_=automatic_candidates(analysis,[{'id':'f','name':'MSDS.pdf','sha256':'h','role':'source'}])
    r=next(r for r in records if r['source_quote']==storage and r['domain']=='measure')
    assert r['domain']=='measure' and r['values']['措施内容']==storage
    assert len(r['source_quote'])>39 and r['source_context']==storage


def test_long_word_paragraph_uses_full_block_not_2200_character_chunk():
    text='安全措施应保持有效。'*350
    block={'locator':'body[1]','kind':'paragraph','text':text}
    analysis={'documents':[{'sha256':'h','blocks':[block]}],
              'chunks':[{'id':'cut','source':'原文','sha256':'h','locator':'body[1]','text':text[:2200]}]}
    passages=list(extraction_passages(analysis,{'id':'f','name':'原文.docx','sha256':'h'}))
    assert passages[0]['text']==text and len(passages[0]['text'])>2200
    r=automatic_candidates(analysis,[{'id':'f','name':'原文.docx','sha256':'h','role':'source'}])[0][0]
    assert r['source_quote']==text and r['title'].endswith('…')
    update_record([r],{'id':r['id'],'revision':1,'values':r['values'],'status':'checked','reviewer':'核对人','review_note':'完整原段一致','report_section':''},{'3'},[{'id':'f','sha256':'h'}])
    assert r['status']=='checked'


def test_multi_sentence_word_paragraph_is_not_split_into_single_sentences():
    text='应设置安全设施，保持机械连接牢固。发生异常时及时检查。检修过程中应按照规定隔离能量，确认安全后恢复运行。'
    assert paragraph_spans({'locator':'body[1]','kind':'paragraph','text':text})==[text]


def test_subsection_groups_list_and_continuations_with_each_source_location():
    blocks=[{'locator':'b1','level':2,'text':'1.2 法律法规'},
            {'locator':'b2','text':'《中华人民共和国安全生产法》：本次引用依据。'},
            {'locator':'b3','text':'《某安全管理条例》：来源资料所列依据。'},
            {'locator':'b4','text':'以上文件版本及执行条件以原文件记载为准。'},
            {'locator':'b5','level':2,'text':'1.3 技术标准'},
            {'locator':'b6','text':'GB 50016-2014 《建筑设计防火规范》'}]
    a={'documents':[{'sha256':'h','blocks':blocks}]}
    passages=list(extraction_passages(a,{'id':'f','name':'报告.docx','sha256':'h'}))
    assert len(passages)==2
    assert passages[0]['text']=='\n\n'.join(b['text'] for b in blocks[1:4])
    assert [p['locator'] for p in passages[0]['source_spans']]==['b2','b3','b4']
    assert 'GB 50016' not in passages[0]['text']
    records,_=automatic_candidates(a,[{'id':'f','name':'报告.docx','sha256':'h','role':'source'}])
    laws=[r for r in records if r['domain']=='regulation']
    assert len(laws)==2 and laws[0]['title']=='1.2 法律法规'


def test_unheaded_independent_paragraphs_remain_separate():
    a={'documents':[{'sha256':'h','blocks':[{'locator':'b1','text':'设备A安全措施。'}, {'locator':'b2','text':'另一独立材料的说明。'}]}]}
    assert len(list(extraction_passages(a,{'id':'f','name':'资料','sha256':'h'})))==2
