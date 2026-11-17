"""Auditable report-specific professional records, pending human verification."""
from datetime import date, datetime, timezone
import json
from pathlib import Path
import uuid
from .workflow_schema import SCHEMAS

WORKFLOWS = {
    'facility_design': {'hazard': ('危险因素与设计条件', '3'), 'design': ('安全设施设计与依据', '5'), 'verification': ('设计参数与专业复核', '6')},
    'pre_evaluation': {'scope': ('评价对象、范围及建设方案', '2'), 'hazard': ('危险有害因素与事故情景', '3'), 'method': ('评价单元和评价方法', '4'), 'assessment': ('评价过程与结果', '5'), 'recommendation': ('对策措施与建议', '7')},
    'acceptance_evaluation': {'scope': ('验收范围与实际建设情况', '2'), 'hazard': ('危险因素与评价单元', '3'), 'inspection': ('现场核查与设施落实', '4'), 'testing': ('检测检验记录', '4'), 'rectification': ('问题整改及复查', '5'), 'assessment': ('验收评价过程', '5')},
    'emergency_plan': {'risk': ('风险辨识与事故情景', '2'), 'organization': ('应急组织、职责与联络', '3'), 'warning': ('预警、接报与信息报告', '4'), 'response': ('分级响应与现场处置', '5'), 'resources': ('应急资源与保障', '6'), 'training': ('培训演练和预案管理', '7'), 'special': ('专项预案与现场处置方案', '8')},
}
WORKFLOWS.update({'worktrade_conditions': {'scope': ('论证对象、范围与建设方案', '2'), 'hazard': ('危险因素及事故情景', '3'), 'conditions': ('选址、工艺和设施安全条件', '4'), 'recommendation': ('对策措施与后续建议', '5')}, 'worktrade_current_evaluation': {'scope': ('评价对象、范围及现状', '2'), 'hazard': ('危险因素与事故情景', '3'), 'method': ('评价单元和方法', '4'), 'inspection': ('现场核查和运行证据', '5'), 'rectification': ('问题整改与复查', '6')}, 'safety_standardization': {'scope': ('企业范围与组织职责', '2'), 'management': ('制度和落实记录', '3'), 'inspection': ('检查、隐患及整改', '4'), 'assessment': ('自评及持续改进', '5')}, 'dual_prevention': {'scope': ('风险辨识对象和边界', '2'), 'risk': ('风险辨识及分级方法', '2'), 'control': ('风险管控措施与责任', '3'), 'rectification': ('隐患排查整改及复查', '4'), 'training': ('培训和运行改进', '5')}})

for workflow in WORKFLOWS.values():
    workflow['regulatory'] = ('法规标准适用性核查', '1')

FIELDS = ('kind', 'title', 'content', 'source_file', 'source_locator', 'report_section', 'status', 'reviewer', 'review_note')


class ProfessionalLedger:
    def __init__(self, path, report_type):
        self.path = Path(path)
        if report_type not in WORKFLOWS:
            raise ValueError('报告类型无效')
        self.report_type = report_type

    def list(self):
        if not self.path.exists():
            return []
        data = json.loads(self.path.read_text(encoding='utf-8'))
        if not isinstance(data, dict) or not isinstance(data.get('items'), list):
            raise ValueError('专业工作台账格式无效')
        return data['items']

    def save(self, payload, ident=None):
        if not isinstance(payload, dict):
            raise ValueError('专业记录格式无效')
        item = {key: str(payload.get(key, '')).strip() for key in FIELDS}
        limits = {'kind': 80, 'title': 200, 'content': 8000, 'source_file': 300, 'source_locator': 300, 'report_section': 20, 'status': 20, 'reviewer': 120, 'review_note': 2000}
        if any(len(item[key]) > limit for key, limit in limits.items()):
            raise ValueError('专业记录存在超出长度限制的字段')
        if item['kind'] not in WORKFLOWS[self.report_type]:
            raise ValueError('记录类别与报告类型不匹配')
        spec = SCHEMAS[self.report_type][item['kind']]
        details = payload.get('details', {})
        if not isinstance(details, dict):
            raise ValueError('专业分项字段格式无效')
        allowed = {field['key'] for field in spec}
        if set(details) - allowed:
            raise ValueError('专业分项字段与当前类别不匹配')
        clean = {}
        for field in spec:
            value = details.get(field['key'], '')
            if not isinstance(value, str) or len(value) > 2000:
                raise ValueError('专业分项字段必须是 2000 字以内的文字')
            value = value.strip()
            if field.get('options') and value and value not in field['options']:
                raise ValueError(field['label'] + '选项无效')
            if item['status'] == 'reviewed' and field.get('required') and not value:
                raise ValueError('专业复核通过前请填写：' + field['label'])
            clean[field['key']] = value
        if item['kind'] == 'regulatory' and clean.get('checked_date'):
            try:
                checked_date = date.fromisoformat(clean['checked_date'])
            except ValueError:
                raise ValueError('核验日期必须为 YYYY-MM-DD') from None
            if checked_date > date.today():
                raise ValueError('法规核验日期不能晚于今天')
        item['details'] = clean
        if not all(item[key] for key in ('title', 'content', 'source_file', 'source_locator')):
            raise ValueError('请填写标题、内容、来源文件及来源位置')
        if item['status'] not in {'draft', 'reviewed', 'rejected'}:
            raise ValueError('请选择有效的复核状态')
        if item['status'] == 'reviewed' and not item['reviewer']:
            raise ValueError('复核通过须填写专业复核人')
        if not item['report_section']:
            item['report_section'] = WORKFLOWS[self.report_type][item['kind']][1]
        if not item['report_section'].isdigit():
            raise ValueError('报告章节请填写主章节编号')
        now = datetime.now(timezone.utc).isoformat(timespec='seconds')
        items = self.list()
        current = next((row for row in items if row['id'] == ident), None) if ident else None
        if ident and current is None:
            raise ValueError('没有找到该专业记录')
        if current:
            changed = current.get('status') == 'reviewed' and any(
                current.get(key, {} if key == 'details' else '') != item.get(key)
                for key in (*FIELDS, 'details') if key not in {'status', 'reviewer', 'review_note'})
            if changed:
                item['status'] = 'draft'
                item['reviewer'] = ''
                item['review_note'] = ''
            current['history'].append({**{key: current.get(key, '') for key in FIELDS}, 'details': current.get('details', {}), 'revision': current['revision'], 'updated_at': current['updated_at']})
            current.update(item, revision=current['revision'] + 1, updated_at=now)
        else:
            current = {'id': uuid.uuid4().hex, **item, 'revision': 1, 'created_at': now, 'updated_at': now, 'history': []}
            items.append(current)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temp = self.path.with_suffix('.tmp')
        temp.write_text(json.dumps({'schema_version': 1, 'items': items}, ensure_ascii=False, indent=2), encoding='utf-8')
        temp.replace(self.path)
        return current

    def report_evidence(self):
        result = []
        for item in self.list():
            if item['status'] != 'reviewed':
                continue
            spec = SCHEMAS[self.report_type][item['kind']]
            detail_text = '\n'.join(field['label'] + '：' + item.get('details', {}).get(field['key'], '') for field in spec if item.get('details', {}).get(field['key']))
            regulatory = item['kind'] == 'regulatory'
            extra = ({'evidence_type': 'regulatory_applicability',
                      'rule_validity_status': item.get('details', {}).get('validity', ''),
                      'rule_checked_date': item.get('details', {}).get('checked_date', ''),
                      'project_applicability': item.get('details', {}).get('decision', '')} if regulatory else {})
            result.append({'id': 'professional-' + item['id'] + '-r' + str(item['revision']), 'source': item['source_file'], 'locator': item['source_locator'], 'text': f"{WORKFLOWS[self.report_type][item['kind']][0]}：{item['title']}\n{detail_text}\n{item['content']}\n复核说明：{item['review_note']}", 'corpus': 'project_evidence', 'evidence_type': 'professional_record', 'reviewed_by': item['reviewer'], 'report_section': item['report_section'], **extra})
        return result
