"""Company knowledge records with revision history and approved-only hybrid retrieval."""
from __future__ import annotations

from datetime import date, datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import threading
import uuid

from .documents import HybridEvidenceIndex

CATEGORIES = {
    'regulation': '法律法规与标准',
    'chemical': '危险物料',
    'hazard': '危险有害因素',
    'analysis_rule': '分析规则与计算方法',
    'safety_measure': '安全措施',
    'report_rule': '报告编制规则',
    'case': '历史案例',
    'facility': '安全设施通用知识',
    'emergency_resource': '应急资源与组织通用知识',
}
STATUSES = {'draft', 'approved', 'retired'}
FIELDS = ('category', 'title', 'content', 'source', 'source_url', 'applicability',
          'version', 'effective_from', 'effective_to', 'validity_status')
VALIDITY = {'current', 'unknown', 'superseded', 'repealed', 'not_applicable'}


def _now():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def _date(value, label):
    if not value:
        return ''
    try:
        return date.fromisoformat(value).isoformat()
    except (TypeError, ValueError):
        raise ValueError(label + '必须使用 YYYY-MM-DD 格式')


class KnowledgeBase:
    """A small file-backed KB suitable for the local prototype; writes are atomic."""
    def __init__(self, path, index_path=None):
        self.path = Path(path)
        self.index_path = Path(index_path) if index_path else self.path.with_suffix('.qdrant')
        self.lock = threading.RLock()
        self.index = None
        self.index_digest = ''
        self.index_mode = 'empty'

    def _read(self):
        if not self.path.exists():
            return {'schema_version': 1, 'records': []}
        data = json.loads(self.path.read_text(encoding='utf-8'))
        if not isinstance(data, dict) or not isinstance(data.get('records'), list):
            raise ValueError('知识库数据文件格式无效')
        return data

    def _write(self, data):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temp = self.path.with_suffix(self.path.suffix + '.tmp')
        temp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
        temp.replace(self.path)

    @staticmethod
    def _clean(payload):
        if not isinstance(payload, dict):
            raise ValueError('知识条目必须为对象')
        item = {key: str(payload.get(key, '')).strip() for key in FIELDS}
        if item['category'] not in CATEGORIES:
            raise ValueError('请选择有效的知识分类')
        if not item['validity_status']:
            item['validity_status'] = 'unknown' if item['category'] == 'regulation' else 'not_applicable'
        if item['validity_status'] not in VALIDITY:
            raise ValueError('请选择有效状态')
        if item['category'] != 'regulation' and item['validity_status'] == 'current':
            raise ValueError('只有法规和标准条目可以标记为“现行有效”')
        if item['category'] == 'regulation' and item['validity_status'] == 'not_applicable':
            raise ValueError('法规和标准条目需标记为现行、未知或已失效')
        limits = {'title': 200, 'content': 30000, 'source': 300, 'source_url': 1000,
                  'applicability': 1200, 'version': 120, 'effective_from': 10, 'effective_to': 10}
        for key, maximum in limits.items():
            if len(item[key]) > maximum:
                raise ValueError(f'{key}超过长度限制')
        for key, label in [('title', '标题'), ('content', '知识内容'), ('source', '来源')]:
            if not item[key]:
                raise ValueError('请填写' + label)
        if item['source_url'] and not re.match(r'^https?://', item['source_url'], re.I):
            raise ValueError('来源链接必须以 http:// 或 https:// 开头')
        item['effective_from'] = _date(item['effective_from'], '生效日期')
        item['effective_to'] = _date(item['effective_to'], '失效日期')
        if item['effective_from'] and item['effective_to'] and item['effective_to'] < item['effective_from']:
            raise ValueError('失效日期不能早于生效日期')
        return item

    def list(self, status=None, category=None):
        with self.lock:
            records = self._read()['records']
            return [r for r in records if (not status or r.get('status') == status)
                    and (not category or r.get('category') == category)]

    def create(self, payload):
        item = self._clean(payload)
        timestamp = _now()
        record = {'id': uuid.uuid4().hex, **item, 'status': 'draft', 'revision': 1,
                  'created_at': timestamp, 'updated_at': timestamp, 'reviewed_by': '',
                  'history': [], 'audit': [{'action': 'created', 'at': timestamp, 'status': 'draft'}]}
        with self.lock:
            data = self._read()
            data['records'].append(record)
            self._write(data)
            self._invalidate_index()
        return record

    def create_many(self, payloads):
        if not isinstance(payloads, list) or not 1 <= len(payloads) <= 100:
            raise ValueError('单次导入需要 1 至 100 个可读取内容块')
        records = []
        for payload in payloads:
            item = self._clean(payload)
            timestamp = _now()
            records.append({'id': uuid.uuid4().hex, **item, 'status': 'draft', 'revision': 1,
                'created_at': timestamp, 'updated_at': timestamp, 'reviewed_by': '', 'history': [],
                'audit': [{'action': 'imported', 'at': timestamp, 'status': 'draft', 'revision': 1}]})
        with self.lock:
            data = self._read()
            data['records'].extend(records)
            self._write(data)
            self._invalidate_index()
        return records

    def find_duplicate_document(self, file_sha256='', text='', category=None):
        from .import_identity import find_duplicate
        with self.lock:
            record = find_duplicate(self._read(), file_sha256, text, category)
            return dict(record) if record else None

    def import_chunks(self, payloads, file_sha256, text):
        """Check existing whole documents and old fragments under the write lock."""
        from .import_identity import find_duplicate, document_keys, chunk_key
        with self.lock:
            data = self._read()
            existing = find_duplicate(data, file_sha256, text)
            if existing:
                return {'count': 0, 'duplicate': True, 'existing_id': existing['id'],
                        'existing_title': existing['title'], 'record_ids': [existing['id']]}
            if not isinstance(payloads, list) or not 1 <= len(payloads) <= 100:
                raise ValueError('文件需要1至100个可读取内容块，请拆分较大的文件后导入')
            timestamp = _now()
            records = []
            for payload in payloads:
                item = self._clean(payload)
                records.append({'id': uuid.uuid4().hex, **item, 'status': 'draft', 'revision': 1,
                    'created_at': timestamp, 'updated_at': timestamp, 'reviewed_by': '',
                    'history': [], 'audit': [{'action': 'imported', 'at': timestamp, 'status': 'draft', 'revision': 1}]})
            # Reuse unchanged chunks only within this exact document/version.
            keys = document_keys(text)
            reused = {}
            by_id = {r['id']: r for r in data['records'] if not r.get('migrated_to')}
            for manifest in data.get('document_imports', []):
                if keys.intersection(manifest.get('text_keys', [])):
                    for part in manifest.get('records', []):
                        record = by_id.get(part['id'])
                        if record and chunk_key(record['content']) == part['hash']:
                            reused.setdefault(part['hash'], record)
            selected = []; added = []
            for record in records:
                known = reused.get(chunk_key(record['content']))
                selected.append(known or record)
                if not known: added.append(record)
            data['records'].extend(added)
            data.setdefault('document_imports', []).append({'file_sha256': file_sha256,
                'text_keys': sorted(keys), 'records': [{'id': r['id'], 'hash': chunk_key(r['content'])} for r in selected]})
            self._write(data)
            self._invalidate_index()
            return {'count': len(added), 'duplicate': not added, 'skipped': len(selected)-len(added),
                    'record_ids': [r['id'] for r in selected]}

    def update(self, ident, payload):
        item = self._clean(payload)
        with self.lock:
            data = self._read()
            record = next((r for r in data['records'] if r['id'] == ident), None)
            if not record:
                raise ValueError('没有找到知识条目')
            record['history'].append({**{key: record.get(key, '') for key in FIELDS},
                                      'revision': record['revision'], 'status': record['status'],
                                      'updated_at': record['updated_at'], 'reviewed_by': record.get('reviewed_by', '')})
            record.update(item, revision=record['revision'] + 1, updated_at=_now(),
                          status='draft', reviewed_by='')
            record['audit'].append({'action': 'revised; approval reset', 'at': record['updated_at'],
                                    'revision': record['revision'], 'status': 'draft'})
            self._write(data)
            self._invalidate_index()
            return record

    def delete(self, ident, revision):
        """Remove from active knowledge and retrieval; retain an audit-only archive."""
        if type(revision) is not int or revision < 1:
            raise ValueError('请刷新知识库后再删除')
        with self.lock:
            data = self._read()
            record = next((r for r in data['records'] if r['id'] == ident), None)
            if not record:
                raise ValueError('知识条目已不存在，请刷新列表')
            if record['revision'] != revision:
                raise ValueError('知识条目已被修改，请刷新后重新核对再删除')
            timestamp = _now()
            record['deleted_at'] = timestamp
            record['audit'].append({'action': 'deleted', 'at': timestamp, 'revision': revision})
            data.setdefault('deleted_records', []).append(record)
            data['records'] = [r for r in data['records'] if r['id'] != ident]
            self._write(data)
            self._invalidate_index()
            return {'deleted_id': ident, 'title': record['title']}

    def set_status(self, ident, status, reviewer='', confirm_use=False):
        if status not in STATUSES:
            raise ValueError('知识状态无效')
        reviewer = str(reviewer).strip()[:120]
        if status == 'approved' and not reviewer:
            raise ValueError('审核通过时请填写审核人')
        with self.lock:
            data = self._read()
            record = next((r for r in data['records'] if r['id'] == ident), None)
            if not record:
                raise ValueError('没有找到知识条目')
            if status == 'approved' and (not record.get('source') or not record.get('content')):
                raise ValueError('缺少来源或知识内容，不能审核通过')
            if status=='approved' and confirm_use:
                candidate={**record,'status':'approved'}
                if candidate.get('category')=='regulation' and candidate.get('validity_status')=='unknown':candidate['validity_status']='current'
                eligible,reason=self.retrieval_eligibility(candidate)
                if not eligible:raise ValueError('不能审核启用：'+reason)
                record['validity_status']=candidate.get('validity_status','not_applicable')
            record.update(status=status, reviewed_by=reviewer if status == 'approved' else '', updated_at=_now())
            record['audit'].append({'action': 'status_changed', 'at': record['updated_at'],
                                    'revision': record['revision'], 'status': status,
                                    'reviewed_by': record['reviewed_by'],'confirmed_use':bool(confirm_use),'validity_status':record.get('validity_status','unknown')})
            self._write(data)
            self._invalidate_index()
            return record

    @staticmethod
    def retrieval_eligibility(record, purpose="report"):
        if record.get('status')!='approved':return False,'尚未审核通过或已停用'
        if purpose=='reference' and record.get('category')=='regulation' and record.get('validity_status')=='unknown':
            return True,'仅供已录入条文阅读；有效性未核验，不作为现行合规依据'
        if record.get('category')=='regulation' and record.get('validity_status')!='current':
            state={'unknown':'有效状态未知','superseded':'已被替代','repealed':'已废止','not_applicable':'有效状态不适用'}.get(record.get('validity_status'),'未确认有效状态')
            return False,'法规'+state+'，未纳入检索；请核对适用版本后维护有效状态'
        today=date.today().isoformat()
        if record.get('effective_from') and record['effective_from']>today:return False,'尚未到生效日期'
        if record.get('effective_to') and record['effective_to']<today:return False,'已超过失效日期'
        return True,'已纳入检索；仍需结合问题核对适用性'

    def _approved_chunks(self, purpose="report"):
        today = date.today()
        chunks = []
        for record in self._read()['records']:
            if not self.retrieval_eligibility(record,purpose)[0]:continue
            text = '\n'.join(filter(None, [record['title'], CATEGORIES[record['category']],
                '适用范围：' + (record.get('applicability') or '未填写'),
                '版本：' + (record.get('version') or '未填写'), record['content']]))
            for part, offset in enumerate(range(0, len(text), 1800)):
                body = text[offset:offset + 2200]
                key = hashlib.sha256(f"{record['id']}:{record['revision']}:{part}:{body}".encode()).hexdigest()[:24]
                chunks.append({'id': 'kb-' + key, 'knowledge_id': record['id'], 'revision': record['revision'],
                    'category': record['category'], 'knowledge_status': record['status'], 'source': '知识库：' + record['title'],
                    'source_document': record['source'], 'source_url': record.get('source_url', ''),
                    'locator': f"审核版本 v{record['revision']} · {record.get('version') or '版本未注明'}",
                    'applicability': record.get('applicability', ''),
                    'effective_from': record.get('effective_from', ''), 'effective_to': record.get('effective_to', ''),
                    'validity_status': record.get('validity_status', 'unknown'),
                    'reviewed_by': record.get('reviewed_by', ''), 'corpus': 'approved_knowledge', 'offset': offset, 'text': body})
        return chunks

    def _invalidate_index(self):
        self.index_digest = ''
        if self.index:
            self.index.close()
            self.index = None

    def close(self):
        """Release the local vector store so Windows can move/delete its files."""
        with self.lock:
            self._invalidate_index()

    def search(self, query, limit=5, purpose="report"):
        query = str(query).strip()
        if not query:
            return []
        with self.lock:
            chunks = self._approved_chunks(purpose)
            if not chunks:
                self.index_mode = 'empty'
                return []
            digest = hashlib.sha256(''.join(c['id'] for c in chunks).encode()).hexdigest()
            if digest != self.index_digest:
                self._invalidate_index()
                self.index = HybridEvidenceIndex(chunks, self.index_path, rebuild=True)
                self.index_digest = digest
            results = self.index.search(query, max(1, min(int(limit), 20)))
            self.index_mode = 'hybrid_qdrant_rrf' if self.index.client and not self.index.semantic_error else 'keyword_fallback'
            return results

