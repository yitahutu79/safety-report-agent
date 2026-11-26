/* Design profiles adapted from VoltAgent/awesome-design-md; see root DESIGN.md. */
'use strict';
const designProfiles=[
 {id:'notion',name:'彩色工作空间',source:'Notion',description:'清晰卡片 · 柔和彩色 · 轻快工作空间',layout:'cards'},
 {id:'claude',name:'暖色阅读',source:'Claude',description:'纸色画布 · 编辑式标题 · 安静阅读',layout:'list'},
 {id:'linear',name:'深色专业',source:'Linear',description:'深色表面 · 紧凑列表 · 专注编写',layout:'list'}
];
const designPreference='safety-design-profile';const designLayoutPreference='safety-knowledge-layout';
function readDesignPreference(key){try{return localStorage.getItem(key);}catch{return null;}}
function saveDesignPreference(key,value){try{localStorage.setItem(key,value);}catch{/* Appearance still works when browser storage is unavailable. */}}
const appearanceDialog=el('dialog',undefined,'design-picker');appearanceDialog.id='design-picker';appearanceDialog.setAttribute('aria-labelledby','design-picker-title');
const appearanceBar=el('div',undefined,'design-picker-heading');const appearanceCopy=el('div');const appearanceTitle=el('h2','选择你的工作空间');appearanceTitle.id='design-picker-title';appearanceCopy.append(appearanceTitle,el('p','三套完整设计，切换后立即预览。仅改变网页外观。'));
appearanceBar.append(appearanceCopy,button('关闭',()=>appearanceDialog.close(),'secondary'));appearanceDialog.append(appearanceBar);
const appearanceOptions=el('div',undefined,'design-options');appearanceOptions.setAttribute('role','radiogroup');appearanceOptions.setAttribute('aria-label','工作台外观主题');appearanceDialog.append(appearanceOptions);
const appearanceNote=el('div',undefined,'design-picker-note');appearanceNote.append(el('span','设计参考 · VoltAgent / awesome-design-md'),button('完成',()=>appearanceDialog.close(),'primary'));appearanceDialog.append(appearanceNote);document.body.append(appearanceDialog);
const appearanceLabel=el('span');const appearanceButton=button('',()=>appearanceDialog.showModal(),'design-appearance-button');appearanceButton.id='design-appearance-button';appearanceButton.setAttribute('aria-haspopup','dialog');const appearanceMark=el('span',undefined,'design-appearance-mark');appearanceMark.innerHTML='<i></i><i></i><i></i>';appearanceButton.append(appearanceMark,appearanceLabel);$('.header-tags').prepend(appearanceButton);
for(const profile of designProfiles){const choice=button('',()=>applyDesignProfile(profile.id,true),'design-choice');choice.dataset.preview=profile.id;choice.dataset.designChoice=profile.id;choice.setAttribute('role','radio');choice.setAttribute('aria-label',profile.name);
 const preview=el('div',undefined,'design-miniature');preview.setAttribute('aria-hidden','true');preview.innerHTML='<div class="design-mini-side"><b></b><i></i><i></i><i></i><i></i></div><div class="design-mini-main"><div class="design-mini-title"></div><div class="design-mini-caption"></div><div class="design-mini-tiles"><i></i><i></i><i></i></div><div class="design-mini-row"></div><div class="design-mini-row"></div></div>';
 const copy=el('div',undefined,'design-choice-copy');copy.append(el('strong',profile.name),el('span',profile.source),el('p',profile.description));choice.append(preview,copy);appearanceOptions.append(choice);}
const knowledgeLayoutControls=el('div',undefined,'design-layout-controls');knowledgeLayoutControls.setAttribute('role','group');knowledgeLayoutControls.setAttribute('aria-label','知识资料展示方式');
for(const [key,label,icon] of [['cards','卡片','layout-dashboard'],['list','列表','file-text']]){const b=studioAction(label,icon,()=>{saveDesignPreference(designLayoutPreference,key);setDesignKnowledgeLayout(key);},'design-layout-button');b.dataset.knowledgeLayout=key;knowledgeLayoutControls.append(b);}studioFilters.append(knowledgeLayoutControls);
function setDesignKnowledgeLayout(layout){document.body.dataset.knowledgeLayout=layout;for(const b of knowledgeLayoutControls.children){const active=b.dataset.knowledgeLayout===layout;b.classList.toggle('active',active);b.setAttribute('aria-pressed',String(active));}}
function applyDesignProfile(id,persist=false){const profile=designProfiles.find(p=>p.id===id)||designProfiles[0];document.body.dataset.designTheme=profile.id;document.documentElement.style.colorScheme=profile.id==='linear'?'dark':'light';appearanceLabel.textContent='外观 · '+profile.name;appearanceButton.setAttribute('aria-label','切换外观，当前'+profile.name);
 for(const choice of appearanceOptions.children){const active=choice.dataset.designChoice===profile.id;choice.setAttribute('aria-checked',String(active));choice.classList.toggle('selected',active);}
 const storedLayout=readDesignPreference(designLayoutPreference);setDesignKnowledgeLayout(['cards','list'].includes(storedLayout)?storedLayout:profile.layout);
 if(persist)saveDesignPreference(designPreference,profile.id);
}
applyDesignProfile(readDesignPreference(designPreference));
