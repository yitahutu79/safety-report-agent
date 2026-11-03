"""Auditable project calculation records; this module intentionally performs no engineering math.

Only calculations reviewed by a named professional and tied to source inputs and an
identified rule/formula are eligible to appear as report evidence. A later rule plugin
must be versioned and validated separately before it can compute a result.
"""
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation, localcontext
import json
from pathlib import Path
import threading
import uuid

KINDS = {
    'hazard_identification': '危险有害因素辨识',
    'chemical_identification': '危险化学品识别',
    'major_hazard': '重大危险源辨识',
    'fire_separation': '防火间距核查',
    'explosion_hazard': '爆炸危险分析',
    'pressure_relief_area': '泄压面积计算',
    'fire_water': '消防用水量计算',
    'other': '其他专业分析/计算',
}
STATUSES = {'draft', 'reviewed', 'rejected'}
FIELDS = ('kind', 'title', 'status', 'inputs', 'source_rule', 'rule_version',
          'rule_clause', 'rule_validity_status', 'rule_checked_date', 'formula', 'steps', 'result', 'result_unit', 'assumptions',
          'reviewer', 'review_note', 'report_section')


def calculate_major_hazard_indicator(unit_name, unit_source_file, unit_locator, materials):
    """Calculate only GB 18218-2018 S=sum(q_i/Q_i) for a user-defined unit.

    Chemical applicability, the production/storage-unit boundary, maximum design
    quantities and each Q value remain expert-confirmed inputs. This function does
    not identify chemicals or determine their critical quantities.
    """
    unit_name = str(unit_name).strip() if isinstance(unit_name, str) else ''
    unit_source_file = str(unit_source_file).strip() if isinstance(unit_source_file, str) else ''
    unit_locator = str(unit_locator).strip() if isinstance(unit_locator, str) else ''
    if not unit_name or not unit_source_file or not unit_locator:
        raise ValueError('请填写辨识单元名称/边界及其来源文件和位置')
    if not isinstance(materials, list) or not 1 <= len(materials) <= 100:
        raise ValueError('每个辨识单元需要 1 到 100 种危险化学品输入')
    seen = set()
    parsed = []
    def positive_decimal(value, label):
        try:
            number = Decimal(str(value))
        except (InvalidOperation, ValueError, TypeError):
            raise ValueError(label + '必须是有效的数字')
        if not number.is_finite() or number <= 0 or number > Decimal('1e15'):
            raise ValueError(label + '必须大于 0 且在允许范围内')
        return number
    for row in materials:
        if not isinstance(row, dict):
            raise ValueError('危险化学品输入格式无效')
        name = row.get('name', '').strip() if isinstance(row.get('name'), str) else ''
        if not name or len(name) > 200:
            raise ValueError('请填写不超过 200 字的物质名称')
        if name.casefold() in seen:
            raise ValueError('同一辨识单元内存在重复物质名称，请先合并实际存在量')
        seen.add(name.casefold())
        quantity = positive_decimal(row.get('quantity_t'), f'{name}实际存在量 q（t）')
        critical = positive_decimal(row.get('critical_t'), f'{name}临界量 Q（t）')
        quantity_source = row.get('quantity_source_file', '').strip() if isinstance(row.get('quantity_source_file'), str) else ''
        quantity_locator = row.get('quantity_source_locator', '').strip() if isinstance(row.get('quantity_source_locator'), str) else ''
        critical_source = row.get('critical_source_file', '').strip() if isinstance(row.get('critical_source_file'), str) else ''
        critical_locator = row.get('critical_source_locator', '').strip() if isinstance(row.get('critical_source_locator'), str) else ''
        if not all((quantity_source, quantity_locator, critical_source, critical_locator)):
            raise ValueError(f'{name}的实际存在量和临界量都必须记录来源文件及位置')
        parsed.append((name, quantity, critical, quantity_source, quantity_locator,
                       critical_source, critical_locator))
    with localcontext() as context:
        context.prec = 28
        ratios = [(name, quantity / critical) for name, quantity, critical, *_ in parsed]
        indicator = sum((ratio for _, ratio in ratios), Decimal(0))
        reaches = parsed[0][1] >= parsed[0][2] if len(parsed) == 1 else indicator >= 1
        if len(parsed) == 1:
            outcome = '单一品种数量达到或超过对应临界量，需由专业人员按标准流程复核' if reaches else '单一品种数量低于对应临界量，仍需专业人员核验适用范围和单元划分'
            formula = '单一品种按 q ≥ Q 判定；下列 q/Q 比值仅作为辅助展示'
            steps = f"辨识单元：{unit_name}。单一品种 {parsed[0][0]}：q={parsed[0][1]} t，Q={parsed[0][2]} t，q/Q={format(indicator, '.12g')}。{outcome}。qᵢ 口径须由复核人依据 4.2.2 确认；适用的储罐、容器、设备或仓储区应按设计最大量确定。"
        else:
            outcome = '达到重大危险源辨识指标（S ≥ 1），需由专业人员按标准流程复核' if reaches else '未达到重大危险源辨识指标（S < 1），仍需专业人员核验适用范围和单元划分'
            formula = 'S = Σ(qᵢ/Qᵢ)；qᵢ、Qᵢ 均按 t 输入，S ≥ 1 为达到辨识指标'
            rendered = ' + '.join(f'{quantity}/{critical}' for _, quantity, critical, *_ in parsed)
            steps = f"辨识单元：{unit_name}。S = {rendered} = {format(indicator, '.12g')}。{outcome}。qᵢ 口径须由复核人依据 4.2.2 确认；适用的储罐、容器、设备或仓储区应按设计最大量确定。"
        result = {'indicator': format(indicator, '.12g'), 'is_at_or_above_threshold': reaches,
                  'statement': outcome, 'formula': formula, 'steps': steps,
                  'rule': 'GB 18218-2018《危险化学品重大危险源辨识》',
                  'rule_version': '2018-11-19 发布；2019-03-01 实施',
                  'rule_clause': '4.2.1 a)（单一品种）' if len(parsed) == 1 else '4.2.1 b) 式（1）（多品种），并参照 4.2.2 核实 q 口径',
                  'result_unit': 'q/Q 比值（单一品种，辅助展示）' if len(parsed) == 1 else 'S',
                  'assumptions': '人工确认该生产/储存单元边界、每种物质属于标准表 1/表 2 的范围及对应临界量 Q；qᵢ 的统计口径按 4.2.2 核实。此工具只计算 S，不判断物质分类、临界量适用性、单元划分或标准流程的其他条件。',
                  'unit_name': unit_name}
    inputs = [{'name': '生产/储存辨识单元边界：' + unit_name, 'value': unit_name, 'unit': '辨识单元',
               'source_file': unit_source_file, 'source_locator': unit_locator, 'evidence_id': ''}]
    for name, quantity, critical, q_file, q_loc, Q_file, Q_loc in parsed:
        inputs.extend([
            {'name': name + '实际存在量 q', 'value': format(quantity, 'f'), 'unit': 't',
             'source_file': q_file, 'source_locator': q_loc, 'evidence_id': ''},
            {'name': name + '临界量 Q（需对照表 1/表 2 及分类核实）', 'value': format(critical, 'f'), 'unit': 't',
             'source_file': Q_file, 'source_locator': Q_loc, 'evidence_id': ''},
        ])
    return {**result, 'inputs': inputs}


def _now():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


class CalculationLedger:
    def __init__(self, path):
        self.path = Path(path)
        self.lock = threading.RLock()

    def _read(self):
        if not self.path.exists():
            return {'schema_version': 1, 'items': []}
        data = json.loads(self.path.read_text(encoding='utf-8'))
        if not isinstance(data, dict) or not isinstance(data.get('items'), list):
            raise ValueError('专业分析计算台账格式无效')
        return data

    def _write(self, data):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temp = self.path.with_suffix('.tmp')
        temp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
        temp.replace(self.path)

    @staticmethod
    def _clean(payload):
        if not isinstance(payload, dict):
            raise ValueError('计算记录格式无效')
        item = {key: payload.get(key, '') for key in FIELDS}
        for key in ('title', 'source_rule', 'rule_version', 'rule_clause', 'formula',
                    'rule_validity_status', 'rule_checked_date', 'steps', 'result', 'result_unit', 'assumptions', 'reviewer',
                    'review_note', 'report_section'):
            if not isinstance(item[key], str):
                raise ValueError(f'{key}必须为文本')
            item[key] = item[key].strip()
        if not item['rule_validity_status']:
            item['rule_validity_status'] = 'unknown'
        if item['kind'] not in KINDS:
            raise ValueError('请选择有效的分析/计算类型')
        if item['status'] not in STATUSES:
            raise ValueError('请选择有效的复核状态')
        if item['rule_validity_status'] not in {'current', 'unknown', 'superseded', 'repealed', 'not_applicable'}:
            raise ValueError('请选择依据/规则有效状态')
        if item['rule_checked_date']:
            try:
                item['rule_checked_date'] = date.fromisoformat(item['rule_checked_date']).isoformat()
            except ValueError:
                raise ValueError('依据状态核验日期必须使用 YYYY-MM-DD 格式')
            if date.fromisoformat(item['rule_checked_date']) > date.today():
                raise ValueError('依据状态核验日期不能晚于今天')
        if not item['title'] or len(item['title']) > 200:
            raise ValueError('请填写不超过 200 字的记录标题')
        if not isinstance(item['inputs'], list) or len(item['inputs']) > 100:
            raise ValueError('输入数据须为最多 100 项的列表')
        clean_inputs = []
        for entry in item['inputs']:
            if not isinstance(entry, dict):
                raise ValueError('每项输入必须为对象')
            row = {key: entry.get(key, '') for key in
                   ('name', 'value', 'unit', 'source_file', 'source_locator', 'evidence_id')}
            for key, maximum in (('name', 120), ('value', 500), ('unit', 60),
                                 ('source_file', 300), ('source_locator', 200), ('evidence_id', 80)):
                if not isinstance(row[key], str):
                    raise ValueError('输入字段必须为文本')
                row[key] = row[key].strip()
                if len(row[key]) > maximum:
                    raise ValueError('输入字段超过长度限制')
            if not row['name'] or not row['value'] or not row['unit']:
                raise ValueError('每项计算输入都要填写名称、数值/内容和单位')
            if item['status'] == 'reviewed' and not all(row[k] for k in ('source_file', 'source_locator')):
                raise ValueError('复核通过的计算记录中，每项输入都必须记录来源文件和位置')
            clean_inputs.append(row)
        item['inputs'] = clean_inputs
        for key, maximum in (('source_rule', 500), ('rule_version', 120), ('rule_clause', 300),
                             ('formula', 2000), ('steps', 10000), ('result', 2000),
                             ('result_unit', 100), ('assumptions', 4000), ('reviewer', 120),
                             ('review_note', 2000), ('report_section', 160)):
            if len(item[key]) > maximum:
                raise ValueError(f'{key}超过长度限制')
        if item['status'] == 'reviewed':
            if item['rule_validity_status'] not in {'current', 'not_applicable'}:
                raise ValueError('复核通过前需核验依据状态；如确实不适用法规版本，请选“不适用”并说明')
            if item['rule_validity_status'] == 'current' and not item['rule_checked_date']:
                raise ValueError('标记依据现行时必须记录有效性核验日期')
            required = ('source_rule', 'rule_version', 'rule_clause', 'formula', 'steps',
                        'result', 'result_unit', 'assumptions', 'reviewer', 'review_note')
            if any(not item[key] for key in required):
                raise ValueError('复核通过前必须填写依据来源、版本、条款、公式、计算过程、结果、单位和复核人')
            if not item['inputs']:
                raise ValueError('复核通过的记录至少需要一项可追溯输入')
        return item

    def list(self):
        with self.lock:
            return self._read()['items']

    def save(self, payload, ident=None):
        item = self._clean(payload)
        timestamp = _now()
        with self.lock:
            data = self._read()
            current = next((x for x in data['items'] if x['id'] == ident), None) if ident else None
            if current:
                reviewed_payload_changed = current.get('status') == 'reviewed' and any(
                    current.get(key) != item.get(key) for key in FIELDS
                    if key not in {'status', 'reviewer', 'review_note'})
                if reviewed_payload_changed:
                    item['status'] = 'draft'
                    item['reviewer'] = ''
                    item['review_note'] = ''
                current['history'].append({**{k: current.get(k) for k in FIELDS},
                    'revision': current['revision'], 'updated_at': current['updated_at']})
                current.update(item, revision=current['revision'] + 1, updated_at=timestamp)
                current['audit'].append({'action': 'revised', 'at': timestamp,
                                         'revision': current['revision'], 'status': item['status'],
                                         'review_reset': reviewed_payload_changed})
                record = current
            elif ident:
                raise ValueError('没有找到专业分析计算记录')
            else:
                record = {'id': uuid.uuid4().hex, **item, 'revision': 1,
                          'created_at': timestamp, 'updated_at': timestamp, 'history': [],
                          'audit': [{'action': 'created', 'at': timestamp, 'revision': 1,
                                     'status': item['status']}]}
                data['items'].append(record)
            self._write(data)
            return record

    def report_evidence(self):
        result = []
        with self.lock:
            for item in self._read()['items']:
                if item['status'] != 'reviewed':
                    continue
                inputs = '\n'.join(f"输入：{x['name']}={x['value']} {x['unit']}；来源：{x['source_file']} {x['source_locator']}" for x in item['inputs'])
                text = (f"分析/计算类型：{KINDS[item['kind']]}\n标题：{item['title']}\n{inputs}\n"
                        f"依据：{item['source_rule']} {item['rule_version']} {item['rule_clause']}\n"
                        f"依据有效状态：{item['rule_validity_status']}；核验日期：{item['rule_checked_date'] or '未记录'}\n"
                        f"公式/方法：{item['formula']}\n计算过程：{item['steps']}\n"
                        f"结果：{item['result']} {item['result_unit']}\n适用条件/假设：{item['assumptions'] or '未注明'}\n"
                        f"复核人：{item['reviewer']}；复核说明：{item['review_note'] or '未注明'}")
                result.append({'id': f"calculation-{item['id']}-r{item['revision']}",
                    'source': '专业分析计算台账：' + item['title'],
                    'locator': f"审核版本 v{item['revision']} · {KINDS[item['kind']]}",
                    'text': text, 'corpus': 'project_evidence', 'evidence_type': 'professional_calculation',
                    'calculation_kind': item['kind'], 'calculation_status': item['status'],
                    'reviewed_by': item['reviewer'], 'report_section': item['report_section'],
                    'rule_validity_status': item['rule_validity_status'], 'rule_checked_date': item['rule_checked_date'],
                    'inputs': item['inputs'], 'formula': item['formula'], 'result': item['result'],
                    'result_unit': item['result_unit']})
        return result
