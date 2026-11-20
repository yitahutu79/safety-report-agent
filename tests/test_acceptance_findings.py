from safety_report.quality import review_report


def test_legacy_excerpt_is_failure_and_empty_missing_does_not_prove_complete():
    report={'sections':[{'id':'2','title':'2 概况','paragraphs':[{'text':'资料摘录：本项目位于山东东平经济开发区内。','evidence_ids':['e1']}],'tables':[],'missing':[]}],
            'evidence':[{'id':'e1','source':'file','locator':'p1'}]}
    state={'fields':[{'key':'address','value':'烟台经济技术开发区台北路以西','confirmed':True}]}
    checks={x['key']:x for x in review_report(report,state)['checks']}
    assert checks['source_dump']['status']=='fail'
    assert checks['chapter_completion']['status']=='warning'
    assert checks['project_location_scope']['status']=='warning'
    report['sections'][0]['paragraphs'][0]['text']='供应商位于山东东平经济开发区。'
    checks={x['key']:x for x in review_report(report,state)['checks']}
    assert 'project_location_scope' not in checks
