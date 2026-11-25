// Pure block ordering shared by browser preview and parity-tested against Word export.
function reportHeadingInScope(heading,scope){if(!scope||heading===scope)return true;const parent=scope.match(/^\d+(?:\.\d+)*/),child=heading.match(/^\d+(?:\.\d+)*/);return !!(parent&&child&&child[0].startsWith(parent[0]+'.'));}
function reportPreviewOrder(section,scope=''){
 const paragraphs=section.paragraphs||[],items=[];for(const [kind,key] of [['paragraph','paragraphs'],['table','tables'],['figure','figures']])for(const [index,item] of (section[key]||[]).entries())items.push({kind,index,heading:item.heading||section.title,item});
 const headings=[...new Set([section.title,...(section.subheadings||[]),...items.map(x=>x.heading)])],result=[];
 const manual=x=>Number.isInteger(x.item.insertion_order)?x.item.insertion_order:0,source=x=>Number.isInteger(x.item.source_order)?x.item.source_order:Infinity,event=(x,stale=false)=>({kind:x.kind,index:x.index,heading:x.heading,stale});
 for(const heading of headings){if(!reportHeadingInScope(heading,scope))continue;const group=items.filter(x=>x.heading===heading);if(!group.length)continue;result.push({kind:'heading',heading});const base=[],anchored=new Map(),end=[];
 for(const x of group){const item=x.item,anchor=item.paragraph_text;if(x.kind!=='paragraph'&&anchor!==undefined&&anchor!==null){const matches=paragraphs.map((p,i)=>p.text===anchor&&(p.heading||section.title)===heading?i:-1).filter(i=>i>=0);if(matches.length===1){const list=anchored.get(matches[0])||[];list.push(x);anchored.set(matches[0],list);}else end.push([x,true]);}else if(x.kind==='figure'||x.kind==='table'&&'insertion_order' in item)end.push([x,false]);else base.push(x);}
 for(const x of base.sort((a,b)=>source(a)-source(b))){result.push(event(x));if(x.kind==='paragraph')for(const a of (anchored.get(x.index)||[]).sort((a,b)=>manual(a)-manual(b)))result.push(event(a));}
 for(const [x,stale] of end.sort((a,b)=>manual(a[0])-manual(b[0])))result.push(event(x,stale));
 }return result;
}
function resolveReportPreviewTarget(report,id,heading){const index=report.sections.findIndex(s=>(s.id||s.title.match(/^\d+/)?.[0])===id);if(index<0)throw Error('目标章节已变化，请刷新');const section=report.sections[index];if(![section.title,...(section.subheadings||[])].includes(heading))throw Error('目标小节已变化，请刷新');return {chapter:index,scope:heading===section.title?'':heading};}
function documentImagePreviewPath(item,thumb=false){return 'source-images/'+encodeURIComponent(item.asset_id||item.id)+'/preview?file_id='+encodeURIComponent(item.source_file_id)+(thumb?'&thumb=1':'');}
if(typeof module!=='undefined')module.exports={documentImagePreviewPath,reportHeadingInScope,reportPreviewOrder,resolveReportPreviewTarget};
