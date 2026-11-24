import json
from pathlib import Path


def catalog_profile(root,report_type):
    path=Path(root)/'reference/default_outlines.json'
    if not path.exists():return None
    return json.loads(path.read_text(encoding='utf-8'))['profiles'].get(report_type)


def semantic_workflows(workflows,profile):
    """Recommend a target chapter by title; do not silently remap existing records."""
    import re
    patterns={'hazard':['危险.*因素','危险性分析'],'design':['安全设施设计.*措施','防范措施'],
              'verification':['结论.*建议','评价结论'],'regulatory':['依据','总则'],
              'scope':['项目概况','企业概况'],'method':['评价单元','评价方法'],
              'assessment':['安全设施符合性评价','定性.*定量','评价结论'],'recommendation':['对策.*措施'],
              'inspection':['安全设施符合性评价','现场核查','定性.*定量'],
              'testing':['安全设施符合性评价'],'rectification':['对策.*措施'],
              'risk':['危险性分析','风险分析'],'organization':['组织机构'],
              'warning':['预防.*预警'],'response':['应急响应'],'resources':['保障措施'],
              'training':['培训.*演练'],'special':['专项预案']}
    result={}
    for kind,(label,old) in workflows.items():
        match=next((h for pattern in patterns.get(kind,[]) for h in profile['headings'] if h['level']==1 and re.search(pattern,h['text'])),None)
        result[kind]=(label,(match.get('id') or re.match(r'\d+',match['text']).group()) if match else '')
    return result
