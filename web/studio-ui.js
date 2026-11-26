/* Task-focused interface. Layout references and original Lucide asset attribution:
 * third_party/lucide/README.md. Existing business actions and evidence remain authoritative. */
'use strict';
document.body.classList.add('studio-ui');
function studioIcon(name){const image=el('img',undefined,'studio-icon');image.src='/ui-icons/'+name+'.svg';image.alt='';image.setAttribute('aria-hidden','true');return image;}
function studioAction(label,icon,fn,style='secondary'){const b=button(label,fn,style);b.prepend(studioIcon(icon));return b;}

// A single page title and navigation hierarchy instead of overlapping tab bars.
const studioHeader=el('div',undefined,'studio-page-header');
const studioHeaderText=el('div');studioHeaderText.append(el('p','安全生产 · 项目工作空间','studio-eyebrow'));
const studioTitle=el('h1','项目工作台');const studioSubtitle=el('p','资料、专业判断与报告编写，在同一工作空间衔接。','studio-subtitle');studioHeaderText.append(studioTitle,studioSubtitle);
const studioProject=el('span','','studio-project-chip');studioHeader.append(studioHeaderText,studioProject);$('#workspace').prepend(studioHeader);
const studioRoutes={materials:['项目资料','整理项目事实，为专业判断和报告编写提供依据。'],draft:['报告编写','逐小节完善正文，确认后再组装完整报告。'],knowledge:['知识中心','从可靠知识到专业报告，让每一处引用有据可查。'],history:['版本记录','查看已保存的报告与修订记录。']};
function updateStudioHeader(){document.body.dataset.studioReportAlert=current?.error||current?.busy?'important':'routine';const route=studioRoutes[view]||studioRoutes.materials;studioTitle.textContent=view==='knowledge'?({maintain:'共用知识库',qa:'知识问答',evaluation:'检索评测'}[knowledgePanel.dataset.focus]||route[0]):route[0];studioSubtitle.textContent=view==='knowledge'&&knowledgePanel.dataset.focus==='maintain'?'管理可靠的法规、标准与专业知识，为报告提供依据。':route[1];if(view==='materials'&&['professional','calculations','measures'].includes(document.body.dataset.materialFocus)){studioTitle.textContent='专业工作台';studioSubtitle.textContent='风险判断、计算复核与措施落实，分别记录、关联使用。';}studioProject.textContent=current?.name||'尚未选择项目';}
const studioShowBefore=showView;showView=function(name){studioShowBefore(name);updateStudioHeader();};
const studioRenderBefore=render;render=function(project){studioRenderBefore(project);updateStudioHeader();};updateStudioHeader();
const studioNavIcons={'项目概览':'layout-dashboard','资料导入':'upload','基本信息':'file-text','图件与位置':'folder-open','项目结构化数据':'sliders-horizontal','编写与修订':'file-text','专业工作台':'shield-check','历史版本':'archive','知识问答':'sparkles','共用知识维护':'library-big','检索评测':'search','测试记录':'circle-check'};
for(const nav of [...taskButtons,addNav,testNav]){const label=nav.textContent.replace('·','').trim();if(!studioNavIcons[label])continue;const previous=nav.querySelector('.task-nav-dot');if(previous){previous.replaceChildren(studioIcon(studioNavIcons[label]));}else{nav.querySelector('svg')?.remove();nav.prepend(studioIcon(studioNavIcons[label]));}}

// Knowledge editing opens on demand, leaving the library free of forms.
const studioKnowledgeForm=$('#kb-category').closest('section');
const studioKnowledgeRecords=$('#kb-records').closest('section');
const studioAdvanced=$('#kb-query').closest('details');
const studioEditDialog=el('dialog',undefined,'studio-edit-dialog');studioEditDialog.id='studio-knowledge-editor';
const studioEditBar=el('div',undefined,'studio-dialog-bar');studioEditBar.append(el('strong','编辑知识内容'),button('关闭',()=>closeStudioEditor(),'secondary'));
studioEditDialog.append(studioEditBar,studioKnowledgeForm);document.body.append(studioEditDialog);studioKnowledgeForm.classList.remove('material-focused-hidden');
let studioFormBaseline='';
function closeStudioEditor(){if(studioEditDialog.open&&JSON.stringify(kbPayload())!==studioFormBaseline&&!confirm('关闭后未保存的修改将放弃，确定关闭？'))return;studioEditDialog.close();}
studioEditDialog.addEventListener('cancel',event=>{event.preventDefault();closeStudioEditor();});
const studioFillBefore=kbFill;kbFill=function(record){studioFillBefore(record);if(record){$('#kb-message').classList.add('hidden');studioFormBaseline=JSON.stringify(kbPayload());if(!studioEditDialog.open)studioEditDialog.showModal();}};
function newStudioKnowledge(){studioFillBefore(null);$('#kb-message').classList.add('hidden');studioFormBaseline=JSON.stringify(kbPayload());studioEditDialog.showModal();$('#kb-title').focus();}
const studioSaveBefore=$('#kb-save').onclick;$('#kb-save').onclick=async()=>{await studioSaveBefore();if(!$('#kb-message').classList.contains('hidden'))studioEditDialog.close();};

// Knowledge maintenance has three separate tasks rather than one long page.
const studioKnowledge=el('section',undefined,'studio-knowledge');studioKnowledge.id='studio-knowledge';
const studioKnowledgeTop=el('div',undefined,'studio-section-heading');const studioKnowledgeCopy=el('div');studioKnowledgeCopy.append(el('h2','共用知识库'),el('p','管理跨项目复用的法规、标准与专业知识。','studio-subtitle'));
const studioKnowledgeActions=el('div',undefined,'studio-actions');studioKnowledgeActions.append(studioAction('上传资料','upload',()=>setStudioKnowledgeTab('upload')),studioAction('新建知识','plus',newStudioKnowledge,'primary'));studioKnowledgeTop.append(studioKnowledgeCopy,studioKnowledgeActions);studioKnowledgeActions.classList.add('studio-maintain-actions');studioHeader.append(studioKnowledgeActions);studioKnowledgeTop.hidden=true;
const studioSubnav=el('div',undefined,'studio-subnav');studioSubnav.setAttribute('role','tablist');studioSubnav.setAttribute('aria-label','知识资料功能');
const studioStats=el('div',undefined,'studio-stats');
const studioLibrary=el('section',undefined,'studio-library');studioLibrary.id='studio-library';
const studioFilters=el('div',undefined,'studio-library-toolbar');
const studioSearchWrap=el('label',undefined,'studio-search');const studioSearch=el('input');studioSearch.type='search';studioSearch.placeholder='搜索标题、正文或来源';studioSearch.setAttribute('aria-label','筛选知识条目');studioSearchWrap.append(studioIcon('search'),studioSearch);
const studioStatus=el('select');studioStatus.setAttribute('aria-label','筛选审核状态');for(const [key,label] of [['','全部状态'],['draft','待审核'],['approved','审核通过'],['retired','已停用']])studioStatus.append(new Option(label,key));
const studioCategory=el('select');studioCategory.setAttribute('aria-label','筛选知识分类');studioCategory.append(new Option('全部分类',''));
studioFilters.append(studioSearchWrap,studioCategory,studioStatus);
const studioList=el('div',undefined,'studio-knowledge-list');const studioListCount=el('p','','studio-list-count');studioLibrary.append(studioFilters,studioListCount,studioList);
const studioUpload=el('div',undefined,'studio-upload-pane');studioUpload.append(publicImport);
const studioDiscovery=el('div',undefined,'studio-discovery-pane');studioDiscovery.append(publicResearchPanel);
studioKnowledge.append(studioKnowledgeTop,studioStats,studioSubnav,studioLibrary,studioDiscovery,studioUpload,studioKnowledgeRecords,studioAdvanced);
knowledgePanel.append(studioKnowledge);studioKnowledgeRecords.classList.add('studio-original-records');studioAdvanced.classList.add('studio-advanced');
knowledgeGroups.maintain=[studioKnowledge];
let studioKnowledgeTab='library';const studioTabButtons=[];
for(const [key,label,icon] of [['library','知识资料','library-big'],['research','联网发现与更新','search'],['upload','上传与导入','upload']]){const b=studioAction(label,icon,()=>setStudioKnowledgeTab(key),'studio-subtab');b.setAttribute('role','tab');b.dataset.studioTab=key;studioTabButtons.push(b);studioSubnav.append(b);}
function setStudioKnowledgeTab(key){studioKnowledgeTab=key;studioLibrary.hidden=key!=='library';studioDiscovery.hidden=key!=='research';studioUpload.hidden=key!=='upload';studioAdvanced.hidden=key!=='library';studioStats.hidden=key!=='library';for(const b of studioTabButtons){b.classList.toggle('active',b.dataset.studioTab===key);b.setAttribute('aria-selected',String(b.dataset.studioTab===key));}}
const studioKnowledgeFocusBefore=setKnowledgeFocus;setKnowledgeFocus=function(focus){studioKnowledgeFocusBefore(focus);if(focus==='maintain'){studioKnowledge.classList.remove('material-focused-hidden');studioKnowledgeRecords.classList.remove('material-focused-hidden');publicImport.classList.remove('material-focused-hidden');publicResearchPanel.classList.remove('material-focused-hidden');studioAdvanced.classList.remove('material-focused-hidden');}for(const link of taskButtons){const key={'知识问答':'qa','共用知识维护':'maintain','检索评测':'evaluation'}[link.textContent.replace('·','').trim()];if(key)link.classList.toggle('studio-current',key===focus);}updateStudioHeader();};
setStudioKnowledgeTab('library');setKnowledgeFocus(knowledgePanel.dataset.focus||'qa');

// Compact library rows and a readable detail sheet, retaining the original edit/review actions.
let studioEntries=[];let studioCategories={};let studioActionRows=new Map();
const studioDetail=el('dialog',undefined,'studio-detail-dialog');studioDetail.id='studio-knowledge-detail';document.body.append(studioDetail);
function showStudioKnowledgeDetail(record){studioDetail.replaceChildren();const top=el('div',undefined,'studio-dialog-bar');top.append(el('strong','知识详情'),button('关闭',()=>studioDetail.close(),'secondary'));const head=el('div',undefined,'studio-detail-heading');head.append(studioIcon(record.category==='regulation'?'book-open':'file-text'),el('h2',record.title));const body=el('div',record.content,'studio-detail-body');const meta=el('dl',undefined,'studio-detail-meta');
 for(const [label,value] of [['知识分类',studioCategories[record.category]],['审核状态',kbStatusLabel(record.status)],['来源',record.source],['版本',record.version||'未注明'],['适用范围',record.applicability||'未注明'],['报告使用',record.retrieval_reason]]){meta.append(el('dt',label),el('dd',value||''));}
 if(record.source_url&&/^https?:\/\//i.test(record.source_url)){const link=el('a','打开原始来源 ↗');link.href=record.source_url;link.target='_blank';link.rel='noopener noreferrer';meta.append(el('dt','原始链接'),el('dd'));meta.lastChild.append(link);}
 const footer=el('div',undefined,'studio-detail-actions');footer.append(studioAction('编辑内容','file-text',()=>{studioDetail.close();kbFill(record);}));
 studioDetail.append(top,head,meta,body,footer);studioDetail.showModal();}
function renderStudioLibrary(){
 studioList.replaceChildren();const q=studioSearch.value.trim().toLowerCase();const rows=studioEntries.filter(r=>(!studioStatus.value||r.status===studioStatus.value)&&(!studioCategory.value||r.category===studioCategory.value)&&(!q||[r.title,r.content,r.source].join(' ').toLowerCase().includes(q)));
 studioListCount.textContent='共 '+studioEntries.length+' 条知识 · 当前显示 '+rows.length+' 条';
 const heading=el('div',undefined,'studio-row studio-row-header');for(const text of ['知识内容','审核状态','操作'])heading.append(el('span',text));studioList.append(heading);
 if(!rows.length){const empty=el('div',undefined,'studio-empty');empty.append(studioIcon('library-big'),el('h3',studioEntries.length?'没有匹配的知识':'建立你的专业知识库'),el('p',studioEntries.length?'换一个关键词或筛选条件试试。':'上传公开资料，或从联网发现开始添加。'));studioList.append(empty);}
 for(const record of rows){const row=el('article',undefined,'studio-row');const summary=el('div',undefined,'studio-row-summary');const glyph=el('span',undefined,'studio-file-icon '+(record.category==='regulation'?'is-regulation':''));glyph.append(studioIcon(record.category==='regulation'?'book-open':'file-text'));
 const copy=el('div');const title=button(record.title,()=>showStudioKnowledgeDetail(record),'studio-row-title');copy.append(title,el('p',studioCategories[record.category]+' · '+(record.version||'版本未注明'),'studio-row-meta'),el('p',record.content,'studio-row-excerpt'));summary.append(glyph,copy);
 const status=el('div',undefined,'studio-row-status');status.append(el('span',kbStatusLabel(record.status),'studio-status studio-status-'+record.status));if(record.retrieval_eligible)status.append(el('small','可供报告检索'));else if(record.status==='approved')status.append(el('small','使用条件待核对'));
 const actions=studioActionRows.get(record.id)||el('div');actions.classList.add('studio-row-actions');
 row.append(summary,status,actions);studioList.append(row);}
}
studioSearch.oninput=renderStudioLibrary;studioStatus.onchange=renderStudioLibrary;studioCategory.onchange=renderStudioLibrary;
async function refreshStudioLibrary(){const data=await api('/api/knowledge');studioEntries=data.records;studioCategories=data.categories;const category=studioCategory.value;studioCategory.replaceChildren(new Option('全部分类',''));for(const [key,label] of Object.entries(data.categories))studioCategory.append(new Option(label,key));studioCategory.value=category;
 const original=[...$('#kb-records').querySelectorAll('.evidence-item')];studioActionRows=new Map();studioEntries.forEach((record,i)=>{const actions=original[i]?.querySelector('.paragraph-actions');if(actions)studioActionRows.set(record.id,actions);});
 studioStats.replaceChildren();for(const [label,count,icon,style] of [['全部知识',studioEntries.length,'library-big','neutral'],['待审核',studioEntries.filter(r=>r.status==='draft').length,'clock-3','amber'],['可供报告检索',studioEntries.filter(r=>r.retrieval_eligible).length,'shield-check','green']]){const metric=el('div',undefined,'studio-metric '+style);const mark=el('span',undefined,'studio-metric-icon');mark.append(studioIcon(icon));const copy=el('div');copy.append(el('span',label),el('strong',String(count)));metric.append(mark,copy);studioStats.append(metric);}renderStudioLibrary();}
const studioLoadBefore=loadKnowledge;loadKnowledge=async function(){const saved=studioEditDialog.open?kbPayload():null;const ident=kbEditingId;await studioLoadBefore();if(saved&&studioEditDialog.open&&ident===kbEditingId)for(const key of kbFields)$('#kb-'+key.replaceAll('_','-')).value=saved[key];await refreshStudioLibrary();};
if(selected)refreshStudioLibrary().catch(error=>notify(error.message));

// Discovery separates a small control column from search results.
const studioResearchHeader=publicResearchPanel.querySelector('.card-heading');const studioResearchIntro=publicResearchPanel.querySelector('.section-description');
const studioResearchLayout=el('div',undefined,'studio-research-layout');const studioResearchControls=el('div',undefined,'studio-research-controls');const studioResearchResults=el('div',undefined,'studio-research-results');
for(const node of [...publicResearchPanel.children])if(node!==studioResearchHeader&&node!==studioResearchIntro){if(['research-results-heading','research-status','research-result-scope','research-results'].includes(node.id))studioResearchResults.append(node);else studioResearchControls.append(node);}
studioResearchLayout.append(studioResearchControls,studioResearchResults);publicResearchPanel.append(studioResearchLayout);
// Keep long compliance explanations available without displaying them all at once.
for(const section of [publicImport,publicResearchPanel,studioKnowledgeForm,$('#facts-card'),$('#professional-card'),$('#calculations-card'),$('#measures-card')]){const p=section?.querySelector(':scope > .section-description');if(p&&p.textContent.length>120){const detail=el('details',undefined,'studio-help');const summary=el('summary','使用说明与核对要求');p.before(detail);detail.append(summary,p);}}

// Put the report first. Directory maintenance remains accessible without filling the writing page.
const studioGenerationSettings=$('#generate')?.closest('details');if(studioGenerationSettings)studioGenerationSettings.open=!current?.has_report;
let studioGenerationInitialized=false;
const studioRenderWithSettings=render;render=function(project){studioRenderWithSettings(project);if(!studioGenerationInitialized&&studioGenerationSettings){studioGenerationSettings.open=!project.has_report;studioGenerationInitialized=true;}};
if(current&&studioGenerationSettings){studioGenerationSettings.open=!current.has_report;studioGenerationInitialized=true;}
// The existing editor creates the outline lazily when the saved report finishes loading.
function arrangeStudioDraft(){
 const draft=$('#view-draft'),outline=$('#persistent-outline-editor'),editor=$('#editor-card');
 const progressHelp=draft.querySelector(':scope > .node-progress-help');
 if(progressHelp){const help=el('details',undefined,'studio-report-tools');help.append(el('summary','编写说明与节点进度'));progressHelp.before(help);help.append(progressHelp);draft.append(help);}
 if(!outline||!editor||$('#studio-outline-settings'))return;
 const tools=el('details',undefined,'studio-report-tools');tools.id='studio-outline-settings';tools.append(el('summary','目录管理 · 编辑、新增或删除章节'));
 outline.before(tools);tools.append(outline);draft.insertBefore(editor,tools);
}
const studioRenderBeforeArrangement=render;render=function(project){studioRenderBeforeArrangement(project);arrangeStudioDraft();};
const studioShowBeforeArrangement=showView;showView=function(name){studioShowBeforeArrangement(name);if(name==='draft')arrangeStudioDraft();};
arrangeStudioDraft();

// Keep all three professional workflows visible and explain their distinct responsibilities.
professionalTabs.setAttribute('role','tablist');professionalTabs.setAttribute('aria-label','专业工作分类');
for(const [key,title,description,icon] of [
 ['analysis','风险与专业判断','识别危险因素，形成专业判断','shield-check'],
 ['calculation','计算复核','核对输入、公式、依据与结果','sliders-horizontal'],
 ['measure','措施落实','记录采纳决定与设计落实位置','circle-check']
]){const control=professionalTabButtons[key];control.dataset.professionalArea=key;control.setAttribute('role','tab');control.setAttribute('aria-selected',String(professionalActive===key));const copy=el('span');copy.append(el('strong',title),el('small',description));control.replaceChildren(studioIcon(icon),copy);}
const studioMaterialFocusBefore=setMaterialFocus;setMaterialFocus=function(focus){studioMaterialFocusBefore(focus);updateStudioHeader();if(focus==='professional'||focus==='calculations'||focus==='measures'){studioTitle.textContent='专业工作台';studioSubtitle.textContent='风险判断、计算复核与措施落实，分别记录、关联使用。';}};
