"""Per-project adoption ledger for safety recommendations."""
from datetime import datetime, timezone
import json
from pathlib import Path
import threading
import uuid

STATUSES = {'pending', 'adopted', 'partial', 'not_adopted', 'not_applicable'}
FIELDS = ('recommendation', 'source_file', 'source_locator', 'source_evidence_id',
          'disposition', 'design_response', 'report_section', 'reviewed_by')


def _now():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


class MeasuresLedger:
    def __init__(self, path):
        self.path = Path(path)
        self.lock = threading.RLock()

    def _read(self):
        if not self.path.exists():
            return {'schema_version': 1, 'items': []}
        data = json.loads(self.path.read_text(encoding='utf-8'))
        if not isinstance(data, dict) or not isinstance(data.get('items'), list):
            raise ValueError('安全措施台账格式无效')
        return data

    def _write(self, data):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temp = self.path.with_suffix('.tmp')
        temp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
        temp.replace(self.path)

    def list(self):
        with self.lock:
            return self._read()['items']

    def save(self, payload, ident=None):
        if not isinstance(payload, dict):
            raise ValueError('建议条目格式无效')
        item = {key: str(payload.get(key, '')).strip() for key in FIELDS}
        limits = {'recommendation': 4000, 'source_file': 300, 'source_locator': 200,
                  'source_evidence_id': 80, 'design_response': 4000, 'report_section': 160, 'reviewed_by': 120}
        for key, size in limits.items():
            if len(item[key]) > size:
                raise ValueError(f'{key}超过长度限制')
        if not item['recommendation'] or not item['source_file'] or not item['source_locator']:
            raise ValueError('请填写建议内容、来源文件和来源位置')
        if item['disposition'] not in STATUSES:
            raise ValueError('请选择有效的采纳状态')
        if item['disposition'] in STATUSES - {'pending'} and not item['reviewed_by']:
            raise ValueError('确定采纳状态时必须记录审核人')
        if item['disposition'] in {'adopted', 'partial'} and not item['design_response']:
            raise ValueError('已采纳或部分采纳时，请填写具体设计落实内容')
        if item['disposition'] in {'not_adopted', 'not_applicable'} and not item['design_response']:
            raise ValueError('未采纳或不适用时，请记录理由')
        timestamp = _now()
        with self.lock:
            data = self._read()
            current = next((x for x in data['items'] if x['id'] == ident), None) if ident else None
            if current:
                current['history'].append({**{k: current.get(k, '') for k in FIELDS},
                    'revision': current['revision'], 'updated_at': current['updated_at']})
                current.update(item, revision=current['revision'] + 1, updated_at=timestamp)
                current['audit'].append({'action': 'revised', 'at': timestamp, 'revision': current['revision']})
                record = current
            elif ident:
                raise ValueError('没有找到安全措施建议条目')
            else:
                record = {'id': uuid.uuid4().hex, **item, 'revision': 1, 'created_at': timestamp,
                          'updated_at': timestamp, 'history': [],
                          'audit': [{'action': 'created', 'at': timestamp, 'revision': 1}]}
                data['items'].append(record)
            self._write(data)
            return record

    def report_evidence(self):
        """Only decided rows are included; pending recommendations cannot be presented as adopted."""
        chunks = []
        with self.lock:
            for item in self._read()['items']:
                status = item['disposition']
                if status == 'pending':
                    continue
                text = (f"建议原文：{item['recommendation']}\n采纳状态：{status}\n"
                        f"设计落实：{item['design_response'] or '未填写'}\n报告位置：{item['report_section'] or '未指定'}")
                chunks.append({'id': 'measure-' + item['id'] + '-r' + str(item['revision']),
                    'source': item['source_file'], 'locator': item['source_locator'],
                    'text': text, 'corpus': 'project_evidence', 'evidence_type': 'measure_adoption',
                    'disposition': status, 'source_evidence_id': item['source_evidence_id'],
                    'reviewed_by': item['reviewed_by']})
        return chunks
