import copy,json,shutil,subprocess,zipfile
from pathlib import Path
import pytest
from safety_report.content_order import order_content,paragraph_anchor
from safety_report.word import write_docx

ROOT=Path(__file__).resolve().parents[1]

def section():
    return {'id':'2','title':'2 概况','subheadings':['2.1 工艺','2.1.1 流程','2.10 其他'], 'paragraphs':[{'heading':'2.1.1 流程','text':'图表前说明。'},{'heading':'2.1.1 流程','text':'图表后说明。'},{'heading':'2.10 其他','text':'其他小节。'}], 'tables':[{'heading':'2.1.1 流程','caption':'设备表','headers':['设备'],'rows':[['印刷机']],'paragraph_text':'图表前说明。','insertion_order':2}], 'figures':[{'id':'f','heading':'2.1.1 流程','caption':'工艺图','paragraph_text':'图表前说明。','insertion_order':1}]}

@pytest.mark.parametrize('mode',['normal','stale','source','end','duplicate'])
def test_browser_word_order_parity(mode):
    s=section()
    if mode=='stale':s['paragraphs'][0]['text']='新正文。'
    if mode=='duplicate':s['paragraphs'].append(copy.deepcopy(s['paragraphs'][0]))
    if mode=='source':
        s['tables'][0].pop('paragraph_text');s['tables'][0].pop('insertion_order');s['tables'][0]['source_order']=2
        s['paragraphs'][0]['source_order']=1;s['paragraphs'][1]['source_order']=3
    if mode=='end':
        s['tables'][0].pop('paragraph_text');s['figures'][0].pop('paragraph_text')
    node=shutil.which('node')
    if not node:pytest.skip('Node required for browser/Word production-order parity')
    script="const p=require(process.argv[1]);const s=JSON.parse(process.argv[2]);console.log(JSON.stringify(p.reportPreviewOrder(s,'2.1 工艺')))"
    actual=json.loads(subprocess.check_output([node,'-e',script,str(ROOT/'web/report-preview.js'),json.dumps(s)]))
    assert actual==order_content(s,'2.1 工艺')
    assert all(x['heading']!='2.10 其他' for x in actual)
    if mode=='normal':assert [x['kind'] for x in actual]==['heading','paragraph','figure','table','paragraph']
    if mode in ('stale','duplicate'):assert all(x['stale'] for x in actual if x['kind'] in ('figure','table'))


def test_word_interleaves_table_between_paragraphs(tmp_path):
    s=section();s['figures']=[];r={'sections':[s],'confirmed_fields':[],'evidence':[]}
    out=tmp_path/'report.docx';write_docx(r,{},out,[])
    with zipfile.ZipFile(out) as z:xml=z.read('word/document.xml').decode()
    assert xml.index('图表前说明。')<xml.index('设备表')<xml.index('图表后说明。')<xml.index('其他小节。')


def test_anchor_follows_text_after_insertion_and_rejects_wrong_heading():
    s=section();s['paragraphs'].insert(0,{'heading':'2.1 工艺','text':'新段落'})
    assert paragraph_anchor(s,'2.1.1 流程',0,'图表前说明。')['paragraph_index']==1
    with pytest.raises(ValueError):paragraph_anchor(s,'2.10 其他',0,'图表前说明。')


def test_editing_existing_table_persists_location_without_losing_source_layout():
    from safety_report.versions import apply_edits
    s=section();s['tables'][0].pop('paragraph_text');s['tables'][0].pop('insertion_order')
    r={'sections':[s],'evidence':[]};t=copy.deepcopy(s['tables'][0]);t.update(paragraph_index=0,paragraph_text='图表前说明。',insertion_order=8)
    updated=apply_edits(r,[{'title':s['title'],'paragraphs':[dict(p,original_index=i) for i,p in enumerate(s['paragraphs'])],'tables':[t]}])
    new=updated['sections'][0]['tables'][0]
    assert new['paragraph_text']=='图表前说明。' and new['paragraph_hash'] and new['headers']==t['headers']
    new.pop('paragraph_text');new.pop('paragraph_index');new.pop('paragraph_hash');new['insertion_order']+=1
    end=apply_edits(updated,[{'title':s['title'],'paragraphs':[dict(p,original_index=i) for i,p in enumerate(s['paragraphs'])],'tables':[new]}])
    assert 'paragraph_text' not in end['sections'][0]['tables'][0]


def test_inserted_image_url_uses_asset_id_instead_of_report_figure_id():
    node=shutil.which('node')
    if not node:pytest.skip('Node required for production browser URL regression')
    script="const p=require(process.argv[1]);console.log(p.documentImagePreviewPath({id:'report-figure',asset_id:'source-image',source_file_id:'f1'},true));console.log(p.documentImagePreviewPath({id:'catalog-image',source_file_id:'f1'}))"
    lines=subprocess.check_output([node,'-e',script,str(ROOT/'web/report-preview.js')],text=True).splitlines()
    assert lines==['source-images/source-image/preview?file_id=f1&thumb=1','source-images/catalog-image/preview?file_id=f1']
