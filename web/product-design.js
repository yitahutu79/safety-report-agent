
// Product shell: task-oriented navigation and a project overview built from live state.
const hero=$('.intro');
const heroText=hero.querySelector('div');
heroText.classList.add('hero-copy');
heroText.querySelector('.eyebrow').textContent='SAFETY INTELLIGENCE  /  项目工作区';
heroText.querySelector('p').textContent='让每一份专业判断，都有据可依。';
const heroActions=el('div',undefined,'hero-actions');
heroActions.classList.add('hidden');
heroActions.append(button('进入报告编写  ↗',()=>{showView('draft');window.scrollTo({top:0,behavior:'smooth'});},'hero-primary'),button('管理项目资料',()=>{showView('materials');setMaterialFocus('overview');window.scrollTo({top:0,behavior:'smooth'});},'hero-secondary'));
heroText.append(heroActions);
const heroVisual=el('div',undefined,'hero-visual');heroVisual.setAttribute('aria-hidden','true');
heroVisual.innerHTML='<div class="hero-orbit orbit-one"></div><div class="hero-orbit orbit-two"></div><div class="hero-document"><span class="document-stamp">SAFETY / 01</span><i></i><i></i><i></i><div class="document-chart"><b></b><b></b><b></b><b></b><b></b><b></b><b></b></div><span class="document-footer">PROFESSIONAL REPORT</span></div><div class="hero-float"><span>✦</span><div><strong>专业报告工作台</strong><small>资料 · 分析 · 编写</small></div></div>';
hero.append(heroVisual);
const progressHeading=el('div',undefined,'overview-heading');progressHeading.innerHTML='<div><span class="overline">YOUR WORKFLOW</span><h2>项目编制流程</h2><p>从基础资料到报告草稿，按步骤推进。</p></div><span class="overview-hint">点击卡片快速前往 <b>↗</b></span>';
$('#workflow-summary').before(progressHeading);
const materialPanel=$('#view-materials');
const materialCards={overview:[$('#upload-title').closest('section'),$('#facts-card')],upload:[$('#upload-title').closest('section')],facts:[$('#facts-card')],figure:[$('#figure-card')],professional:[$('#professional-card')],measures:[$('#measures-card')],calculations:[$('#calculations-card')]};
function setMaterialFocus(focus){
  const visible=materialCards[focus]||materialCards.overview;
  for(const cards of Object.values(materialCards))for(const card of cards)if(card)card.classList.toggle('material-focused-hidden',!visible.includes(card));
  materialPanel.dataset.focus=focus;
  document.body.dataset.materialFocus=focus;
}
setMaterialFocus('overview');
const focusByLabel={'资料导入':'upload','基本信息':'facts','图件与位置':'figure','专业分析':'professional','安全措施':'measures','分析计算':'calculations'};
for(const link of taskButtons){const label=link.textContent.replace('·','').trim();const focus=focusByLabel[label];if(focus)link.addEventListener('click',()=>{setMaterialFocus(focus);requestAnimationFrame(()=>{const card=(materialCards[focus]||[]).find(x=>x&&!x.classList.contains('hidden'));if(card)card.scrollIntoView({behavior:'smooth',block:'start'});});});}
const knowledgePanel=$('#view-knowledge');
const knowledgeGroups={qa:[$('#knowledge-qa')],maintain:[publicImport,$('#kb-category').closest('section'),$('#kb-records').closest('section'),$('#kb-query').closest('details')],evaluation:[$('#rag-advanced')]};
function setKnowledgeFocus(focus){const visible=knowledgeGroups[focus]||knowledgeGroups.qa;for(const group of Object.values(knowledgeGroups))for(const node of group)if(node)node.classList.toggle('material-focused-hidden',!visible.includes(node));knowledgePanel.dataset.focus=focus;}
setKnowledgeFocus('qa');
const knowledgeFocusByLabel={'知识问答':'qa','知识维护':'maintain','检索评测':'evaluation'};
for(const link of taskButtons){const focus=knowledgeFocusByLabel[link.textContent.replace('·','').trim()];if(focus)link.addEventListener('click',()=>setKnowledgeFocus(focus));}
const uploadStep=$('#workflow-summary');uploadStep.addEventListener('click',event=>{const step=event.target.closest('.workflow-step');if(!step)return;const text=step.textContent;if(text.includes('整理资料'))setMaterialFocus('upload');if(text.includes('核对信息'))setMaterialFocus('facts');});
const addNav=el('button','⌘   项目概览','overview-nav');addNav.type='button';addNav.onclick=()=>{if(!selected){notify('请先创建或选择项目');return;}showView('materials');setMaterialFocus('overview');taskButtons.forEach(x=>x.classList.remove('is-current'));addNav.classList.add('is-current');window.scrollTo({top:0,behavior:'smooth'});};sidebarNav.insertBefore(addNav,sidebarNav.querySelector('.task-nav-group'));
for(const link of taskButtons)link.addEventListener('click',()=>addNav.classList.remove('is-current'));
const showViewBeforeProductShell=showView;showView=function(name){showViewBeforeProductShell(name);document.body.dataset.currentView=name;if(name==='materials'){setMaterialFocus('overview');taskButtons.forEach(x=>x.classList.remove('is-current'));addNav.classList.add('is-current');}else addNav.classList.remove('is-current');if(name==='knowledge')setKnowledgeFocus('qa');};
document.body.dataset.currentView=view;
const renderBeforeProductShell=render;render=function(project){renderBeforeProductShell(project);heroActions.classList.toggle('hidden',!project);};

// Small local line icons; navigation remains fully functional without a CDN.
const navIconPaths={
 '资料导入':'M4 4h10l4 4v12H4z|M14 4v4h4|M7 13h8|M7 16h6',
 '基本信息':'M12 11a3 3 0 1 0 0-6 3 3 0 0 0 0 6z|M6 19c.4-3.2 2.4-5 6-5s5.6 1.8 6 5',
 '图件与位置':'M4 5h16v14H4z|M7 16l4-4 3 3 2-2 2 3|M8 9h.01',
 '编写与修订':'M4 4h12v16H4z|M7 8h6|M7 12h6|M7 16h4',
 '专业分析':'M5 19V9|M10 19V5|M15 19v-7|M20 19H3',
 '安全措施':'M12 3l7 3v5c0 4-2.5 7-7 10-4.5-3-7-6-7-10V6z|M9 12l2 2 4-4',
 '分析计算':'M5 4h14v16H5z|M8 7h8v3H8z|M8 13h1|M12 13h1|M16 13h1|M8 16h1|M12 16h1|M16 16h1',
 '历史版本':'M5 8V4|M5 8h4|M5 8a8 8 0 1 1-1 7|M12 7v5l3 2',
 '知识问答':'M4 5h16v11H9l-4 3v-3H4z|M8 9h8|M8 12h5',
 '知识维护':'M5 4h11l3 3v13H5z|M8 10h8|M8 13h8|M8 16h5',
 '检索评测':'M10 16a6 6 0 1 0 0-12 6 6 0 0 0 0 12z|M14.5 14.5L20 20'
};
function navIcon(path){const svg=document.createElementNS('http://www.w3.org/2000/svg','svg');svg.setAttribute('viewBox','0 0 24 24');svg.setAttribute('aria-hidden','true');for(const part of path.split('|')){const node=document.createElementNS('http://www.w3.org/2000/svg','path');node.setAttribute('d',part);svg.append(node);}return svg;}
for(const link of taskButtons){const label=link.textContent.replace('·','').trim();const slot=link.querySelector('.task-nav-dot');if(slot&&navIconPaths[label]){slot.textContent='';slot.append(navIcon(navIconPaths[label]));}}
addNav.textContent='项目概览';addNav.prepend(navIcon('M4 4h6v6H4z|M14 4h6v6h-6z|M4 14h6v6H4z|M14 14h6v6h-6z'));

// Projects move to a recoverable local recycle bin; report versions remain intact.
const listProjectsBeforeRecycle=listProjects;
listProjects=async function(){
 const projects=await listProjectsBeforeRecycle();
 const buttons=[...$('#projects').querySelectorAll('button')];
 projects.forEach((project,index)=>{
  const original=buttons[index];if(!original)return;
  const row=el('div',undefined,'project-list-row');original.before(row);row.append(original);
  const remove=button('移入回收站',async()=>{
   if(project.id===selected&&(current?.busy||preflightBusy))throw Error('项目正在处理，请先停止或等待完成');
   const name=prompt('项目将移入回收站，资料、草稿及版本会一并保留，可从回收站恢复。\n请输入完整项目名称以确认：\n'+project.name);
   if(name===null)return;if(name!==project.name)throw Error('项目名称不匹配，未删除');
   if(project.id===selected&&(factsDirty||editorDirty||dirtyFileForms.size||dirtyAssetForms.size||professionalDirty||dirtyLedgers.size)&&!confirm('此项目有未保存的页面修改，移入回收站将丢失这些未保存修改。是否继续？'))return;
   await post('/api/projects/'+project.id+'/trash',{name});
   if(project.id===selected){clearTimeout(polling);selected=null;current=null;report=null;loadedVersion=null;factsDirty=false;editorDirty=false;dirtyFileForms.clear();dirtyAssetForms.clear();dirtyLedgers.clear();clearProfessional();localStorage.removeItem('safety-selected');const remaining=await listProjects();if(remaining.length)await selectProject(remaining[0].id);else{$('#workspace').classList.add('hidden');$('#welcome').classList.remove('hidden');$('#project-title').textContent='从项目资料，到可修改的报告';if(typeof heroActions!=='undefined')heroActions.classList.add('hidden');showView('materials');}}
   else await listProjects();notify('项目已移入回收站，可以恢复');
  },'project-trash-button');remove.setAttribute('aria-label','将'+project.name+'移入回收站');row.append(remove);
 });
 return projects;
};
const recycleButton=button('回收站',async()=>{
 const projects=await api('/api/projects-trash');const dialog=$('#project-trash-dialog');const list=$('#project-trash-list');list.replaceChildren();
 if(!projects.length)list.append(el('p','回收站暂无项目。','muted'));
 for(const project of projects){const row=el('div',undefined,'trash-row');const text=el('div');text.append(el('strong',project.name),el('small','恢复后资料、草稿和历史版本会一并保留。'));row.append(text,button('恢复',async()=>{await post('/api/projects/'+project.id+'/restore-project');dialog.close();await listProjects();await selectProject(project.id);notify('项目已恢复');}));list.append(row);}
 dialog.showModal();
},'recycle-button');
$('#projects').after(recycleButton);
const recycleDialog=el('dialog');recycleDialog.id='project-trash-dialog';recycleDialog.innerHTML='<h2>项目回收站</h2><p class="muted">项目移入回收站后不会出现在项目列表，可在此恢复。</p><div id="project-trash-list"></div><div class="dialog-actions"><button type="button" class="secondary" id="project-trash-close">关闭</button></div>';document.body.append(recycleDialog);$('#project-trash-close').onclick=()=>recycleDialog.close();
listProjects().catch(error=>notify(error.message));

// Local test record is available even before a project is selected.
const testRecordPanel=el('section',undefined,'card test-record-panel hidden');
testRecordPanel.id='test-record-panel';
testRecordPanel.innerHTML='<div class="test-record-heading"><div><span class="overline">TEST RECORD</span><h2>全流程测试记录</h2><p class="section-description">查看实际测试结果、未通过问题与待完成事项。</p></div><span class="tag">2026-11-17</span></div><div id="test-record-content" aria-live="polite"></div>';
$('#workspace').after(testRecordPanel);
function renderTestRecord(markdown){
 const root=$('#test-record-content');root.replaceChildren();const lines=markdown.split(/\r?\n/);
 for(let i=0;i<lines.length;i++){
  const line=lines[i].trim();if(!line)continue;
  if(line.startsWith('|')){const rows=[];while(i<lines.length&&lines[i].trim().startsWith('|')){const cells=lines[i].trim().slice(1,-1).split('|').map(x=>x.trim());if(!cells.every(x=>/^:?-+:?$/.test(x)))rows.push(cells);i++;}i--;if(rows.length){const wrap=el('div',undefined,'test-table-wrap'),table=el('table',undefined,'test-record-table');rows.forEach((cells,index)=>{const tr=el('tr');for(const cell of cells)tr.append(el(index?'td':'th',cell));table.append(tr);});wrap.append(table);root.append(wrap);}continue;}
  if(line.startsWith('# ')){root.append(el('h3',line.slice(2)));continue;}
  if(line.startsWith('## ')){root.append(el('h3',line.slice(3)));continue;}
  const number=line.match(/^(\d+)\.\s+(.+)$/);root.append(el('p',number?number[1]+'．'+number[2]:line));
 }
}
const testNav=button('测试记录',async()=>{
 const data=await api('/api/test-record');
 $('#workspace').classList.add('hidden');$('#welcome').classList.add('hidden');$('.intro').classList.add('hidden');testRecordPanel.classList.remove('hidden');document.body.dataset.currentView='test-record';
 taskButtons.forEach(x=>x.classList.remove('is-current'));addNav.classList.remove('is-current');testNav.classList.add('is-current');renderTestRecord(data.content);window.scrollTo({top:0,behavior:'smooth'});
},'task-nav-link');
testNav.prepend(navIcon('M5 4h14v16H5z|M8 8h8|M8 12h8|M8 16h5'));
const recordGroup=el('div',undefined,'task-nav-group');recordGroup.append(el('div','项目交付','task-nav-heading'),testNav);sidebarNav.append(recordGroup);
const showViewBeforeTestRecord=showView;
showView=function(name){testRecordPanel.classList.add('hidden');testNav.classList.remove('is-current');$('.intro').classList.remove('hidden');$('#workspace').classList.toggle('hidden',!selected);$('#welcome').classList.toggle('hidden',!!selected);showViewBeforeTestRecord(name);};

// Acknowledge a previous failure without changing the report or hiding a newer error.
const renderBeforeErrorAcknowledgement=render;
render=function(project){
 renderBeforeErrorAcknowledgement(project);
 if(project.error&&!project.busy){
  const notice=$('#project-notice');
  notice.append(button('关闭上次错误提示',async()=>{
   await post(endpoint('ack-error'),{expected_error:project.error});
   await refresh();notify('已关闭提示；历史报告版本未改变。');
  },'secondary notice-dismiss'));
 }
};


// Editorial workbench: separate reading from forms, preserving the versioned editor.
const knowledgeTabs=el('nav',undefined,'knowledge-tabs');knowledgeTabs.setAttribute('aria-label','知识中心功能');
for(const [key,label] of [['qa','知识问答'],['maintain','资料与审核'],['evaluation','检索评测']]){
 const b=button(label,()=>setKnowledgeFocus(key),'knowledge-tab');b.dataset.focus=key;knowledgeTabs.append(b);
}
knowledgePanel.prepend(knowledgeTabs);
const focusKnowledgeBeforeEditorial=setKnowledgeFocus;
setKnowledgeFocus=function(focus){focusKnowledgeBeforeEditorial(focus);for(const b of knowledgeTabs.querySelectorAll('button')){b.classList.toggle('active',b.dataset.focus===focus);b.setAttribute('aria-pressed',String(b.dataset.focus===focus));}};
setKnowledgeFocus('qa');
const qaExamples=el('div',undefined,'qa-examples');
for(const text of ['概括资料中的适用范围与限制','有哪些需要进一步核实的条件？','根据现有资料，说明相关安全措施及依据'])qaExamples.append(button(text,()=>{$('#qa-question').value=text;$('#qa-question').focus();},'qa-example'));
$('#qa-question').closest('label').before(qaExamples);
$('#qa-ask').textContent='生成有依据的回答';
const qaRenderBeforeEditorial=showQa;
showQa=function(project){qaRenderBeforeEditorial(project);const box=$('#qa-result');if(project.qa_result&&!project.busy){const actions=el('div',undefined,'answer-actions');actions.append(button('复制回答',async()=>{const content=[project.qa_result.question,...(project.qa_result.paragraphs||[]).map(p=>p.text),...(project.qa_result.missing||[]).map(t=>'待核实：'+t)].join('\n\n');await navigator.clipboard.writeText(content);notify('回答已复制');},'secondary'));box.append(actions);const references=box.querySelector('details summary');if(references)references.textContent='参考来源 · '+(project.qa_result.sources||[]).length+' 条（展开核对）';}};
let editorialMode='read';
function drawReadingView(){
 const preview=$('#reading-content');if(!preview||!report)return;preview.replaceChildren();
 const section=report.sections[currentChapter];let heading='';
 for(const row of $('#paragraph-editor').querySelectorAll('.paragraph-block')){
  const title=row.querySelector('select').value;
  if(title&&title!==section.title&&title!==heading){preview.append(el('h4',title));heading=title;}
  preview.append(el('p',row.querySelector('textarea').value||'（空段落）'));
 }
 for(const source of $('#table-editor').querySelectorAll('.editor-table')){
  preview.append(el('h4',source.querySelector('h3').textContent));const wrap=el('div',undefined,'reading-table-wrap');const table=el('table');
  for(const original of source.querySelectorAll('tr')){const tr=el('tr');for(const cell of original.children)tr.append(el(cell.tagName==='TH'?'th':'td',cell.querySelector('textarea').value));table.append(tr);}wrap.append(table);preview.append(wrap);
 }
 if(!preview.children.length)preview.append(el('p','本章尚无正文。可以使用右侧编写助手生成，或切换编辑补充内容。','reading-empty'));
 const count=[...$('#paragraph-editor').querySelectorAll('textarea')].reduce((n,x)=>n+x.value.replace(/\s/g,'').length,0);
 $('#reading-meta').textContent=count+' 字 · '+$('#table-editor').children.length+' 张表 · '+(editorDirty?'含未保存修改':'已保存版本')+' · 图件及分页以 Word 为准';
}
function setEditorialMode(mode){editorialMode=mode;const paper=$('.chapter-paper');if(!paper)return;paper.dataset.mode=mode;for(const b of paper.querySelectorAll('.paper-mode')){b.classList.toggle('active',b.dataset.mode===mode);b.setAttribute('aria-pressed',String(b.dataset.mode===mode));}drawReadingView();}
const editorBeforeEditorial=renderEditor;
renderEditor=function(){editorBeforeEditorial();if(!report)return;const paper=$('.chapter-paper');
 if(!$('#paper-mode-bar')){
  const bar=el('div',undefined,'paper-mode-bar');bar.id='paper-mode-bar';
  for(const [mode,label] of [['read','阅读排版'],['edit','编辑正文']]){const b=button(label,()=>setEditorialMode(mode),'paper-mode');b.dataset.mode=mode;bar.append(b);}
  bar.append(button('专注阅读',()=>{const focused=document.body.classList.toggle('editorial-focus');bar.lastChild.textContent=focused?'退出专注':'专注阅读';},'focus-toggle'));
  paper.prepend(bar);const meta=el('div',undefined,'reading-meta');meta.id='reading-meta';$('#chapter-paper-title').after(meta);
  const preview=el('article',undefined,'reading-content');preview.id='reading-content';paper.append(preview);
  const presets=el('div',undefined,'writing-presets');presets.append(el('span','快捷修改要求','preset-label'));
  const prompts={'专业化表达':'在不改变事实、数字、单位和确定程度的前提下，改为正式工程报告语言；删除口语和空泛套话，保留依据与限制。','整理逻辑':'按本章对象、已知条件、分析及有依据的结果重新组织，合并重复信息，避免跨章复述。','压缩重复':'仅精简重复、空泛表达，保留所有有效参数、适用条件、例外和来源。'};
  for(const [label,text] of Object.entries(prompts))presets.append(button(label,()=>{const input=$('#chapter-prompt');input.value=(input.value.trim()?input.value.trim()+'\n':'')+text;input.dispatchEvent(new Event('input'));input.focus();},'writing-preset'));
  $('#chapter-prompt-box').before(presets);
 }
 setEditorialMode(editorialMode);
};
$('#add-paragraph').addEventListener('click',()=>setEditorialMode('edit'));
$('#editor-card').addEventListener('input',event=>{if(!event.target.closest('#paragraph-editor,#table-editor'))return;if($('#reading-meta'))$('#reading-meta').textContent='含未保存修改 · 保存本章后生成新版本';});
const editorialShowView=showView;showView=function(name){if(name!=='draft')document.body.classList.remove('editorial-focus');editorialShowView(name);};

// Resume completed nodes for the same request; the user can start fresh explicitly.
const nodeProgressHelp=el('div',undefined,'node-progress-help');
nodeProgressHelp.append(el('div','按目录逐小节编写：每个小节独立调用模型，完成检查后暂存；失败或停止后，使用相同模型、章节和修改要求重试，可恢复已完成部分。资料或设置改变后自动重新执行；整章未通过审核时不会写入报告版本。'));
nodeProgressHelp.append(button('清除未完成节点进度',async()=>{if(!selected)return;if(!confirm('清除后，下次生成将从头执行。已有报告、项目资料和历史版本不会删除。继续吗？'))return;await post(endpoint('clear-node-progress'),{});notify('已清除未完成节点进度');},'secondary'));
generationDisclosure.before(nodeProgressHelp);
