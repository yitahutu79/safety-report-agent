"""Local intake inventory and source-grounded candidates; no model calls or approvals."""
import copy
import hashlib
import json
import re
from pathlib import Path
from .documents import PDF_PARSER_REVISION,parse_file, EvidenceIndex
from .document_catalog import DOMAINS
from .report_template import extract_body_blocks

PATTERNS={
 'regulation':r'(?:GBZ?|AQ|HG|SH|JGJ)\s*[/T]*\s*\d|《[^》]*(?:法|条例|规定|办法|标准|规范|规程)[^》]*》',
 'hazard':r'危险源|危险有害|危险、有害|触电|火灾|爆炸|中毒|窒息|危险特性',
 'facility':r'安全设施|消防|报警|防雷|接地|通风|防火间距|泄压',
 'project_base':r'建设单位|企业名称|项目名称|项目代码|生产规模|营业执照|许可证|特种作业|设备名称|建筑面积',
 'measure':r'安全对策|安全措施|防范措施|应采取|应设置|建议|隐患|整改|储存于|储存在|存放处|容器.*密封',
 'emergency':r'应急组织|应急指挥|应急响应|应急物资|应急资源|救援队伍|救援装备|疏散'}
TEXT_FIELDS={'regulation':'文件名称','hazard':'危险因素','facility':'设施名称或编号',
             'project_base':'事项或证件名称','measure':'措施内容','emergency':'职责或响应流程'}


def reference_analysis(target,files,previous):
    cache={(d['sha256'],d.get('file')):d for d in previous.get('reference_documents',[])}
    documents=[];chunks=[];warnings=[]
    for file in files:
        if file.get('active',True) and file['role']=='reference' and Path(file['name']).suffix.lower() in {'.docx','.pdf','.txt','.csv','.md','.json'}:
            try:
                cached=cache.get((file['sha256'],file['stored']))
                if cached and Path(file['name']).suffix.lower()=='.pdf' and (cached.get('pdf_parser_revision')!=PDF_PARSER_REVISION or cached.get('ocr_retry')):cached=None
                document=copy.deepcopy(cached or parse_file(target/'uploads'/file['stored']))
                attach_section_context(document)
                for chunk in document['chunks']:
                    chunk.update(source=file['name'],sha256=file['sha256'],source_file_id=file['id'],document_type=file.get('document_type','other'),source_role='reference',corpus='reference_document')
                documents.append(document);chunks+=document['chunks']
                warnings += [file['name']+'：'+w for w in document.get('warnings',[])]
            except (OSError,ValueError) as exc:warnings.append(file['name']+'：参考正文读取失败：'+str(exc))
    return documents,chunks,warnings


def automatic_candidates(analysis,files):
    from .source_passages import extraction_passages
    records=[];coverage=[];excluded=excluded_content_locations(analysis)
    for file in files:
        if not file.get('active',True) or file['role']=='attachment':continue
        chunks=list(extraction_passages(analysis,file))
        count=0;seen=set();domain_counts={d:0 for d in DOMAINS}
        for chunk in chunks:
            if (file['sha256'],chunk['locator']) in excluded:continue
            # Keep whole short lines/paragraphs, not a cut-off source prefix.
            parts=[chunk['text'].strip()] if 15<=len(chunk['text'].strip())<=12000 else []
            for quote in parts:
                for domain,pattern in PATTERNS.items():
                    if not re.search(pattern,quote,re.I):continue
                    signature=hashlib.sha256(json.dumps([file['id'],domain,quote,chunk['locator']],ensure_ascii=False).encode()).hexdigest()
                    if signature in seen:continue
                    seen.add(signature)
                    values={field:'' for field in DOMAINS[domain]['fields']};values[TEXT_FIELDS[domain]]=quote
                    if domain=='regulation':
                        code=re.search(r'(?:GB|AQ)\s*(?:[/／]\s*T)?\s*\d+(?:[.－-]\d+)*(?:[-－]\d{4})?',quote,re.I)
                        if code:values['编号及版本']=code.group()
                    if domain=='project_base':
                        labels=r'建设单位|企业名称|项目名称|项目代码|生产规模|建筑面积|设备名称'
                        pair=re.search(r'('+labels+r')\s*[:：]\s*(.+?)(?=(?:'+labels+r')\s*[:：]|$)',quote)
                        if pair:
                            values['事项或证件名称']=pair.group(1);values['编号或数据']=pair.group(2).strip(' ；;，,')
                            if pair.group(1) in {'建设单位','企业名称'}:values['对象或单位']=values['编号或数据']
                    if domain=='hazard':
                        factors=list(dict.fromkeys(re.findall(r'触电|火灾|爆炸|中毒|窒息|机械伤害|高处坠落|物体打击|灼烫',quote)))
                        if factors:values['危险因素']='、'.join(factors);values['发生环节及触发条件']=quote
                    if domain=='facility':
                        facility=re.search(r'消火栓|灭火器|安全阀|喷淋|报警器|防雷接地|机械通风|消防水泵|防火墙',quote)
                        if facility:values['设施名称或编号']=facility.group();values['核查依据']=quote
                    stage='参考报告记载，当前项目适用性待核对' if file['role']=='reference' else '上传资料记载，非现场核查结论'
                    for field in ('来源阶段','计划或现场状态','建议或落实状态'):
                        if field in values:values[field]=stage
                    records.append({'id':'auto-'+signature[:24],'signature':signature,'domain':domain,'file_id':file['id'],
                        'document_type':file.get('document_type','other'),'title':re.sub(r'\s+',' ',quote)[:70]+('…' if len(re.sub(r'\s+',' ',quote))>70 else ''),'values':values,'status':'draft','revision':1,
                        'evidence_id':chunk['id'],'source_file':file['name'],'source_locator':chunk['locator'],
                        'source_quote':quote,'source_sha256':file['sha256'],'source_role':file['role'],
                        'source_context':quote,'context_complete':True,'extraction_method':'local_pattern_candidate','report_section':'','reviewer':'','review_note':'','history':[]})
                    count+=1;domain_counts[domain]+=1
        coverage.append({'file':file['name'],'readable_chunks':len(chunks),'automatic_candidates':count,'domain_counts':domain_counts,'limit_per_domain':None,
                         'scope':'本地关键词识别的待核对候选，未调用模型；未识别不代表全文已完整提取，长正文另由完整报告复用处理'})
    return records,coverage


def reference_reuse_profile(analysis,files,headings,previous):
    prior={b['id']:b for b in previous.get('body_blocks',[])};blocks=[]
    targets={re.sub(r'\s+','',h['text']):h['text'] for h in headings}
    by_sha={f['sha256']:f for f in files if f.get('active',True) and f['role']=='reference'}
    for document in analysis.get('reference_documents',[]):
        file=by_sha.get(document['sha256'])
        if not file:continue
        original=[{'text':b['text']} for b in document['blocks'] if b.get('level') in (1,2,3)]
        for b in extract_body_blocks(document['blocks'],original,document['sha256']):
            ident='ref-'+file['id']+'-'+b['id'][4:]
            if ident in prior:blocks.append(copy.deepcopy(prior[ident]));continue
            b.update(id=ident,source_heading=b['heading'],heading=targets.get(re.sub(r'\s+','',b['heading']),''),
                     source_file=file['name'],source_file_id=file['id'],source_sha256=file['sha256'])
            blocks.append(b)
    return {'body_blocks':blocks,'content_revision':previous.get('content_revision',0)+int(blocks!=previous.get('body_blocks',[]))}


def available_files(files,analysis):
    readable={c.get('sha256') for c in analysis.get('chunks',[])+analysis.get('reference_chunks',[])}
    return [{k:f.get(k,'') for k in ('id','name','role','document_type','read_status')}|
            {'text_available':f.get('sha256') in readable} for f in files if f.get('active',True)]


def intake_search(analysis,query,limit=8):
    # BM25 indexes all uploaded readable content locally. Only short hits reach the model.
    return SectionEvidenceIndex(analysis.get('chunks',[])+analysis.get('reference_chunks',[])).search(query,limit)


MATERIAL_TYPES={
 'sds':r'\bSDS\b|\bMSDS\b|安全技术说明书', 'project_filing':r'备案|立项批复',
 'company_certificate':r'营业执照', 'production_license':r'生产许可|经营许可',
 'layout_drawing':r'总平面|总图|布置图','process_drawing':r'工艺流程图',
 'equipment_ledger':r'设备台账|设备台帐|设备清单','equipment_inspection':r'设备检验|检验报告',
 'expert_review':r'专家.*意见|评审意见|审查意见','emergency_plan':r'应急预案'}


def annotate_material_availability(result,inventory):
    result=copy.deepcopy(result)
    for request in result.get('requests',[]):
        text=' '.join([request['ask'],request['include']]+request.get('examples',[]))
        kinds={kind for kind,pattern in MATERIAL_TYPES.items() if re.search(pattern,text,re.I)}
        matches=[f for f in inventory if f.get('document_type') in kinds or any(re.search(pattern,f['name'],re.I) for kind,pattern in MATERIAL_TYPES.items() if kind in kinds)]
        if matches:
            request['availability']='reference_pending' if all(f['role']=='reference' for f in matches) else 'uploaded_readable' if any(f['text_available'] for f in matches) else 'uploaded_unreadable'
            request['available_files']=[f['name'] for f in matches]
            request['original_ask']=request['ask']
            request['ask']='已找到上传文件《'+'》《'.join(f['name'] for f in matches)+'》。请核对其对象、版本及以下字段：'+request['include']+'；不必重复上传相同文件，只有具体字段确实缺失时再补充。'
            if request['availability']=='reference_pending':request['ask']+='参考报告须先确认是否属于当前项目及适用版本。'
            if request['availability']=='uploaded_unreadable':request['ask']+='文件已上传，但尚未成功读取文字，请先转换或识别。'
        else:request['availability']='not_confirmed_in_retrieval'
    return result


def attach_section_context(document):
    parents={};contexts={}
    for block in document.get('blocks',[]):
        level=block.get('level')
        if level in (1,2,3):
            parents={k:v for k,v in parents.items() if k<level};parents[level]=block['text']
        contexts[block['locator']]=[parents[k] for k in sorted(parents)]
    for chunk in document.get('chunks',[]):
        headings=contexts.get(chunk['locator'],[])
        chunk['source_headings']=headings;chunk['source_heading']=' / '.join(headings)
    return document


class SectionEvidenceIndex(EvidenceIndex):
    """Use the existing BM25 adapter with source heading context; return unchanged quotes."""
    def __init__(self,chunks):
        self.original={c['id']:c for c in chunks}
        # A matching title alone is not a substitute for the body below that title.
        indexed=[{**c,'text':c.get('source_heading','')+'\n'+c['text']} for c in chunks
                 if c['text'].strip() not in c.get('source_headings',[])]
        super().__init__(indexed)
    def search(self,query,limit=10):
        return [self.original[c['id']] for c in super().search(query,limit)]


def excluded_content_locations(analysis):
    """TOC entries and headings are navigation, not extracted factual records."""
    return { (doc.get('sha256'),block['locator'])
             for doc in analysis.get('documents',[])+analysis.get('reference_documents',[])
             for block in doc.get('blocks',[])
             if block.get('level') in (1,2,3) or 'toc' in (block.get('style_id','')+' '+block.get('style_name','')).lower()
             or '目录' in block.get('style_name','') }
