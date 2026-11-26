/* Design profiles adapted from VoltAgent/awesome-design-md; see root DESIGN.md. */
'use strict';
const designProfiles=[
 {id:'notion',name:'彩色工作空间',source:'Notion',description:'清晰卡片 · 柔和彩色 · 轻快工作空间',layout:'cards'},
 {id:'claude',name:'暖色阅读',source:'Claude',description:'纸色画布 · 编辑式标题 · 安静阅读',layout:'list'},
 {id:'linear',name:'深色专业',source:'Linear',description:'深色表面 · 紧凑列表 · 专注编写',layout:'list'},
 {id:'apple',name:'极简银白',source:'Apple · awesome-design-md',description:'银白画布 · 宽松阅读 · 圆润控件',layout:'list'},
 {id:'stripe',name:'商务靛蓝',source:'Stripe · awesome-design-md',description:'深蓝侧栏 · 精细分区 · 紧凑工作台',layout:'list'}
];
const designPreference='safety-design-profile';const designLayoutPreference='safety-knowledge-layout';
function readDesignPreference(key){try{return localStorage.getItem(key);}catch{return null;}}
function saveDesignPreference(key,value){try{localStorage.setItem(key,value);}catch{/* Appearance still works when browser storage is unavailable. */}}
const appearanceDialog=el('dialog',undefined,'design-picker');appearanceDialog.id='design-picker';appearanceDialog.setAttribute('aria-labelledby','design-picker-title');
const appearanceBar=el('div',undefined,'design-picker-heading');const appearanceCopy=el('div');const appearanceTitle=el('h2','选择你的工作空间');appearanceTitle.id='design-picker-title';appearanceCopy.append(appearanceTitle,el('p','五套工作空间，切换后立即预览。仅改变网页外观。'));
appearanceBar.append(appearanceCopy,button('关闭',()=>appearanceDialog.close(),'secondary'));appearanceDialog.append(appearanceBar);
const appearanceOptions=el('div',undefined,'design-options');appearanceOptions.setAttribute('role','radiogroup');appearanceOptions.setAttribute('aria-label','工作台外观主题');appearanceDialog.append(appearanceOptions);
const appearanceNote=el('div',undefined,'design-picker-note');appearanceNote.append(el('span','设计参考 · VoltAgent / awesome-design-md'),button('完成',()=>appearanceDialog.close(),'primary'));appearanceDialog.append(appearanceNote);document.body.append(appearanceDialog);
const appearanceLabel=el('span');const appearanceButton=button('',()=>appearanceDialog.showModal(),'design-appearance-button');appearanceButton.id='design-appearance-button';appearanceButton.setAttribute('aria-haspopup','dialog');const appearanceMark=el('span',undefined,'design-appearance-mark');appearanceMark.innerHTML='<i></i><i></i><i></i>';appearanceButton.append(appearanceMark,appearanceLabel);$('.header-tags').prepend(appearanceButton);
for(const profile of designProfiles){const choice=button('',()=>applyDesignProfile(profile.id,true),'design-choice');choice.dataset.preview=profile.id;choice.dataset.designChoice=profile.id;choice.setAttribute('role','radio');choice.setAttribute('aria-label',profile.name);
 const preview=el('div',undefined,'design-miniature');preview.setAttribute('aria-hidden','true');preview.innerHTML='<div class="design-mini-side"><b></b><i></i><i></i><i></i><i></i></div><div class="design-mini-main"><div class="design-mini-title"></div><div class="design-mini-caption"></div><div class="design-mini-tiles"><i></i><i></i><i></i></div><div class="design-mini-row"></div><div class="design-mini-row"></div></div>';
 const copy=el('div',undefined,'design-choice-copy');copy.append(el('strong',profile.name),el('span',profile.source),el('p',profile.description));choice.append(preview,copy);appearanceOptions.append(choice);}
const knowledgeLayoutControls=el('div',undefined,'design-layout-controls');knowledgeLayoutControls.setAttribute('role','group');knowledgeLayoutControls.setAttribute('aria-label','知识资料展示方式');
for(const [key,label,icon] of [['cards','卡片','layout-dashboard'],['list','列表','file-text']]){const b=studioAction(label,icon,()=>{saveDesignPreference(designLayoutPreference+'-'+document.body.dataset.designTheme,key);setDesignKnowledgeLayout(key);},'design-layout-button');b.dataset.knowledgeLayout=key;knowledgeLayoutControls.append(b);}studioFilters.append(knowledgeLayoutControls);
function setDesignKnowledgeLayout(layout){document.body.dataset.knowledgeLayout=layout;for(const b of knowledgeLayoutControls.children){const active=b.dataset.knowledgeLayout===layout;b.classList.toggle('active',active);b.setAttribute('aria-pressed',String(active));}}
function applyDesignProfile(id,persist=false){const profile=designProfiles.find(p=>p.id===id)||designProfiles[0];document.body.dataset.designTheme=profile.id;document.documentElement.style.colorScheme=profile.id==='linear'?'dark':'light';appearanceLabel.textContent='外观 · '+profile.name;appearanceButton.setAttribute('aria-label','切换外观，当前'+profile.name);
 for(const choice of appearanceOptions.children){const active=choice.dataset.designChoice===profile.id;choice.setAttribute('aria-checked',String(active));choice.classList.toggle('selected',active);}
 const storedLayout=readDesignPreference(designLayoutPreference+'-'+profile.id);setDesignKnowledgeLayout(['cards','list'].includes(storedLayout)?storedLayout:profile.layout);
 if(persist)saveDesignPreference(designPreference,profile.id);
}
applyDesignProfile(readDesignPreference(designPreference));

bindQualityChoiceKeys(appearanceOptions,'[role=radio]');

const typeControls=el('div',undefined,'design-type-controls');typeControls.setAttribute('role','group');typeControls.setAttribute('aria-label','工作台文字大小');typeControls.append(el('strong','文字大小'));
function setWorkspaceType(size,persist=false){document.body.dataset.typeSize=['standard','comfortable','large'].includes(size)?size:'comfortable';for(const item of typeControls.querySelectorAll('button')){const active=item.dataset.size===document.body.dataset.typeSize;item.classList.toggle('active',active);item.setAttribute('aria-pressed',String(active));}if(persist)saveDesignPreference('safety-type-size',document.body.dataset.typeSize);}
for(const [size,label] of [['standard','紧凑'],['comfortable','舒适'],['large','大字']]){const control=button(label,()=>setWorkspaceType(size,true),'secondary');control.dataset.size=size;typeControls.append(control);}appearanceNote.before(typeControls);setWorkspaceType(readDesignPreference('safety-type-size'));
const profileCopy={notion:'活泼彩色 · 分组卡片 · 图文工作空间',claude:'典雅书稿 · 衬线正文 · 纵向阅读',linear:'科技深空 · 精密列表 · 高对比度',apple:'简约银白 · 文档目录 · 大幅留白',stripe:'商务靛蓝 · 深色侧栏 · 数据表格'};
for(const choice of appearanceOptions.children)choice.querySelector('.design-choice-copy p').textContent=profileCopy[choice.dataset.designChoice];

// Phosphor duotone assets are bundled locally; each function has its own scene.
const workspaceArt=el('div',undefined,'workspace-art function-art');workspaceArt.setAttribute('aria-hidden','true');studioHeaderText.after(workspaceArt);
const functionScenes={
 overview:{icon:'folders',support:'clipboard-text',layout:'files'},
 upload:{icon:'cloud-arrow-down',support:'folders',layout:'upload'},
 facts:{icon:'identification-card',support:'list-checks',layout:'identity'},
 figure:{icon:'image',support:'magnifying-glass',layout:'gallery'},
 structured:{icon:'database',support:'list-checks',layout:'database'},
 draft:{icon:'note-pencil',support:'clipboard-text',layout:'writing'},
 qa:{icon:'chat-circle-dots',support:'magnifying-glass',layout:'conversation'},
 library:{icon:'books',support:'shield-check',layout:'shelf'},
 research:{icon:'magnifying-glass',support:'cloud-arrow-down',layout:'research'},
 evaluation:{icon:'target',support:'list-checks',layout:'target'},
 analysis:{icon:'shield-check',support:'clipboard-text',layout:'shield'},
 calculation:{icon:'calculator',support:'chart-bar',layout:'calculation'},
 measure:{icon:'list-checks',support:'shield-check',layout:'checklist'},
 history:{icon:'clock-counter-clockwise',support:'clipboard-text',layout:'timeline'}
};
function functionSceneKey(){if(view==='draft')return 'draft';if(view==='history')return 'history';if(view==='knowledge'){const focus=knowledgePanel.dataset.focus;if(focus==='maintain')return studioKnowledgeTab==='research'?'research':studioKnowledgeTab==='upload'?'upload':'library';return focus==='evaluation'?'evaluation':'qa';}const focus=document.body.dataset.materialFocus||'overview';return ['professional','calculations','measures'].includes(focus)?professionalActive:(functionScenes[focus]?focus:'overview');}
function sceneGlyph(name,style){const glyph=el('span',undefined,'scene-glyph '+style);glyph.style.setProperty('--scene-mask','url("/ui-icons/ph-'+name+'.svg")');return glyph;}
function updateFunctionScene(){const key=functionSceneKey();if(workspaceArt.dataset.function===key)return;workspaceArt.dataset.function=key;const spec=functionScenes[key];workspaceArt.dataset.scene=spec.layout;workspaceArt.replaceChildren();const backdrop=el('div',undefined,'scene-backdrop');const sheet=el('div',undefined,'scene-sheet');sheet.append(sceneGlyph(spec.icon,'scene-main'));const lines=el('div',undefined,'scene-lines');lines.append(el('i'),el('i'),el('i'));sheet.append(lines);const support=el('div',undefined,'scene-support');support.append(sceneGlyph(spec.support,'scene-small'));const accent=el('span',undefined,'scene-accent');const path=el('div',undefined,'scene-path');workspaceArt.append(backdrop,path,accent,sheet,support);}
const sceneHeaderBefore=updateStudioHeader;updateStudioHeader=function(){sceneHeaderBefore();if(view==='materials'){const title={overview:'项目概览',upload:'项目资料',facts:'项目信息',figure:'图件与位置',structured:'项目结构化数据'}[document.body.dataset.materialFocus];if(title)studioTitle.textContent=title;}updateFunctionScene();};
const sceneProfessionalBefore=setProfessionalTab;setProfessionalTab=function(key){sceneProfessionalBefore(key);updateFunctionScene();};
const sceneKnowledgeTabBefore=setStudioKnowledgeTab;setStudioKnowledgeTab=function(key){sceneKnowledgeTabBefore(key);updateFunctionScene();};updateFunctionScene();
const functionNavIcons={'项目概览':'folders','资料导入':'cloud-arrow-down','基本信息':'identification-card','图件与位置':'image','项目结构化数据':'database','编写与修订':'note-pencil','专业工作台':'shield-check','历史版本':'clock-counter-clockwise','知识问答':'chat-circle-dots','共用知识维护':'books','检索评测':'target','测试记录':'list-checks'};
for(const control of [...taskButtons,addNav,testNav]){const name=control.textContent.replace('·','').trim();const icon=control.querySelector('.studio-icon');if(icon&&functionNavIcons[name])icon.src='/ui-icons/ph-'+functionNavIcons[name]+'.svg';}

const fontChoices=[['theme','跟随主题','专业报告，清晰有序'],['sans','现代黑体','清晰利落 · 高效工作'],['serif','正式宋体','严谨端正 · 书稿阅读'],['wenkai','霞鹜文楷','自然舒展 · 轻松阅读']];
const fontPanel=el('section',undefined,'design-font-panel');fontPanel.append(el('h3','字体风格'),el('p','预览标题与阅读内容，操作菜单保持清晰易读。','muted'));const fontOptions=el('div',undefined,'design-font-options');fontOptions.setAttribute('role','radiogroup');fontOptions.setAttribute('aria-label','字体风格');fontPanel.append(fontOptions);typeControls.before(fontPanel);
function setWorkspaceFont(key,persist=false){const valid=fontChoices.some(v=>v[0]===key)?key:'theme';document.body.dataset.fontStyle=valid;for(const control of fontOptions.children){const active=control.dataset.font===valid;control.setAttribute('aria-checked',String(active));control.classList.toggle('active',active);}if(persist)saveDesignPreference('safety-font-style',valid);}
for(const [key,label,sample] of fontChoices){const control=button('',()=>setWorkspaceFont(key,true),'design-font-choice');control.dataset.font=key;control.setAttribute('role','radio');control.setAttribute('aria-label',label);control.append(el('span',label),el('strong',sample),el('small','安全生产技术报告 · Aa 123'));fontOptions.append(control);}bindQualityChoiceKeys(fontOptions,'[role=radio]');setWorkspaceFont(readDesignPreference('safety-font-style'));
