"""Document types and six project data domains; none implies professional approval."""
DOCUMENT_TYPES={
 'project_filing':'项目备案/审批','company_certificate':'营业执照/企业证明','production_license':'生产/经营许可',
 'process':'工艺说明与设备资料','process_drawing':'工艺流程图','layout_drawing':'总平面/设备布置图',
 'drawing':'其他专业图纸','equipment_ledger':'设备台账','equipment_inspection':'设备检验报告',
 'materials':'原辅材料清单','sds':'危险化学品SDS/MSDS','safety_analysis':'安全条件综合分析报告',
 'pre_evaluation':'安全预评价/安全评价报告','historical_design':'安全设施设计专篇/历史设计报告',
 'acceptance_report':'验收评价报告','emergency_plan':'应急预案','accident_record':'历史事故记录',
 'hazard_ledger':'隐患排查治理台账','personnel':'从业人员名单','special_operation_certificate':'特种作业证/持证台账',
 'facility_inventory':'安全设施清单','emergency_inventory':'应急资源/物资清单','expert_review':'专家评审资料','other':'其他'}
DOMAINS={
 'regulation':{'label':'法规标准与评价依据','fields':['文件名称','编号及版本','引用条款','来源载明的适用范围'],'query':'法律 法规 标准 评价依据 编号 版本 条款'},
 'hazard':{'label':'危险有害因素','fields':['对象或危险源','危险因素','发生环节及触发条件','可能后果','来源阶段'],'query':'危险源 危险有害因素 物料 SDS MSDS 危险特性 事故'},
 'facility':{'label':'安全设施','fields':['设施名称或编号','位置或建筑布置','设计参数及单位','计划或现场状态','核查依据'],'query':'安全设施 设计参数 建筑 布置 防火 接地 报警 现场核查 落实'},
 'project_base':{'label':'项目基础信息与资质','fields':['对象或单位','事项或证件名称','编号或数据','发证机构或数据来源','日期或有效期限','来源阶段'],'query':'建设单位 项目名称 营业执照 许可 证书 从业人员 特种作业 设备 检验 工艺'},
 'measure':{'label':'对策措施','fields':['针对对象或风险','措施内容','措施提出来源','建议或落实状态','落实位置或依据'],'query':'安全对策 措施 建议 整改 隐患 采纳 落实'},
 'emergency':{'label':'应急组织与资源','fields':['组织岗位或资源名称','职责或响应流程','数量与单位','存放位置或联络信息','有效性或维护要求'],'query':'应急 组织 指挥 响应 流程 救援 物资 装备 数量 联络'}
}
TYPE_DOMAINS={
 'company_certificate':['project_base'],'production_license':['project_base'],'project_filing':['project_base','regulation'],
 'process':['project_base','hazard'],'process_drawing':['project_base','hazard'],'layout_drawing':['facility','project_base'],
 'equipment_ledger':['project_base','facility'],'equipment_inspection':['facility','project_base'],
 'sds':['hazard'],'materials':['hazard'],'accident_record':['hazard','measure'],'hazard_ledger':['hazard','measure'],
 'personnel':['project_base'],'special_operation_certificate':['project_base'],'facility_inventory':['facility'],
 'emergency_inventory':['emergency'],'emergency_plan':['emergency','hazard'],
 'pre_evaluation':['hazard','regulation','measure'],'safety_analysis':['hazard','regulation','measure'],
 'historical_design':['facility','project_base','measure'],'acceptance_report':['facility','measure','project_base']}

def suggest_document_type(filename):
 import re
 rules=[('sds',r'msds|sds|安全技术说明书'),('special_operation_certificate',r'特种作业|持证'),
 ('production_license',r'生产许可|经营许可|排污许可'),('company_certificate',r'营业执照'),
 ('acceptance_report',r'验收.*评价|验收报告'),('pre_evaluation',r'预评价|安全评价'),
 ('expert_review',r'评审意见|专家意见|审查意见'),('historical_design',r'安全设施设计|设计专篇'),('safety_analysis',r'安全生产条件|综合分析'),
 ('emergency_inventory',r'应急.*(?:物资|资源|装备)'),('emergency_plan',r'应急预案'),
 ('equipment_inspection',r'检验报告|检测报告'),('equipment_ledger',r'设备.*(?:台账|台帐|清单)'),
 ('hazard_ledger',r'隐患.*(?:台账|台帐|排查)'),('accident_record',r'事故.*(?:记录|台账|台帐|报告)'),
 ('personnel',r'人员名单|从业人员'),('layout_drawing',r'总平面|总图|布置图'),('process_drawing',r'工艺流程'),
 ('facility_inventory',r'安全设施.*清单'),('project_filing',r'备案|立项|批复')]
 return next((kind for kind,pattern in rules if re.search(pattern,filename,re.I)),'other')
