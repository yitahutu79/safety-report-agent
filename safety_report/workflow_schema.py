"""Working fields for expert records; applicability and conclusions require review."""

def f(key, label, required=True, options=None):
    return {'key': key, 'label': label, 'required': required, **({'options': options} if options else {})}

REGULATORY_FIELDS = [f('rule', '法规标准名称、编号、版本及条款'), f('decision', '项目适用性', options=['适用', '不适用', '待确认']), f('scope_reason', '项目事实、适用范围及判断理由'), f('validity', '版本有效状态', options=['现行', '已废止', '已替代', '待核实']), f('checked_date', '有效状态核验日期（YYYY-MM-DD）'), f('official_source', '核验来源或官方链接')]

SCHEMAS = {
    'facility_design': {
        'hazard': [f('object', '辨识对象和边界'), f('hazard', '危险因素及影响情景')],
        'design': [f('object', '设计对象和位置'), f('measure', '拟采用的安全设施及设计条件'), f('basis', '设计依据或图号')],
        'verification': [f('object', '核查对象'), f('parameters', '设计参数、单位及取值来源'), f('method', '复核方法及适用条件')],
    },
    'pre_evaluation': {
        'scope': [f('object', '评价对象及建设阶段'), f('boundary', '评价范围、边界及排除事项')],
        'hazard': [f('object', '工艺、设备或物料对象'), f('hazard', '危险因素与事故情景'), f('conditions', '触发条件和影响范围')],
        'method': [f('unit', '评价单元和划分依据'), f('method', '评价方法及选择理由'), f('conditions', '适用条件与限制')],
        'assessment': [f('unit', '评价对象或单元'), f('method', '评价方法及依据'), f('process', '输入条件、分析过程和结果'), f('limitations', '不确定性和限制')],
        'recommendation': [f('object', '适用对象或风险'), f('measure', '建议措施及实施条件'), f('basis', '建议依据或问题来源')],
    },
    'acceptance_evaluation': {
        'scope': [f('object', '验收对象与范围'), f('status', '实际建设及运行阶段'), f('boundary', '范围边界和排除事项')],
        'hazard': [f('object', '对象和评价单元'), f('hazard', '危险因素与事故情景')],
        'inspection': [f('object', '设施名称、编号及位置'), f('requirement', '设计或审查要求及来源'), f('actual', '现场实际情况'), f('date', '现场核查日期'), f('result', '核查结果及待核实事项')],
        'testing': [f('object', '检测对象和位置'), f('report', '检测报告编号、日期及机构'), f('result', '报告所载检测项目与结果'), f('conditions', '适用范围、有效期或限制')],
        'rectification': [f('problem', '问题及发现位置'), f('action', '整改措施及责任'), f('progress', '整改状态', options=['未开始', '进行中', '已完成待复查', '复查通过']), f('verification', '进展证据或复查记录')],
        'assessment': [f('unit', '评价对象或单元'), f('method', '评价方法及依据'), f('process', '评价过程、结果与限制')],
    },
    'emergency_plan': {
        'risk': [f('object', '装置、场所或物料'), f('scenario', '事故情景及触发条件'), f('impact', '可能影响范围和对象')],
        'organization': [f('role', '机构或岗位'), f('responsibility', '职责与替代安排'), f('contact', '经核实的联系方式或待核实说明')],
        'warning': [f('trigger', '预警或报告触发条件'), f('recipient', '接报人及报告对象'), f('procedure', '信息内容、路径与时限依据')],
        'response': [f('scenario', '适用事故情景'), f('trigger', '启动条件和响应级别'), f('steps', '处置步骤、职责和停止条件')],
        'resources': [f('resource', '队伍、物资或装备名称'), f('quantity', '数量、能力及单位'), f('location', '存放地点、维护和调配方式')],
        'training': [f('activity', '培训、演练或预案管理事项'), f('responsibility', '责任岗位、频次及记录依据')],
        'special': [f('scenario', '专项或现场处置适用情景'), f('procedure', '处置步骤及负责岗位'), f('boundary', '适用条件与衔接关系')],
    },
}

# 一期新增类型的工作字段为待专业人员确认的试用结构。
SCHEMAS.update({
    'worktrade_conditions': {
        'scope': [f('object', '对象、范围及边界'), f('basis', '来源和适用阶段')],
        'hazard': [f('object', '设备、工艺、场所或物料'), f('hazard', '危险因素、触发条件和影响')],
        'conditions': [f('object', '条件分析对象和位置'), f('analysis', '项目事实、分析过程和限制'), f('basis', '分析依据和来源')],
        'recommendation': [f('object', '适用对象或风险'), f('measure', '建议措施与实施条件'), f('basis', '建议来源')],
    },
    'worktrade_current_evaluation': {
        'scope': [f('object', '对象、范围及边界'), f('basis', '来源和适用阶段')],
        'hazard': [f('object', '设备、工艺、场所或物料'), f('hazard', '危险因素、触发条件和影响')],
        'method': [f('unit', '评价单元和划分依据'), f('method', '评价方法、选择理由及局限')],
        'inspection': [f('object', '检查对象及位置'), f('actual', '现场实际情况和证据'), f('date', '检查日期及待核实事项')],
        'rectification': [f('problem', '问题及发现位置'), f('action', '整改措施及责任'), f('progress', '整改状态', options=['未开始', '进行中', '已完成待复查', '复查通过']), f('verification', '进展证据或复查记录')],
    },
    'safety_standardization': {
        'scope': [f('object', '对象、范围及边界'), f('basis', '来源和适用阶段')],
        'management': [f('object', '制度或管理事项'), f('actual', '实际落实情况和记录'), f('basis', '依据和适用范围')],
        'inspection': [f('object', '检查对象及位置'), f('actual', '现场实际情况和证据'), f('date', '检查日期及待核实事项')],
        'assessment': [f('object', '自评对象与范围'), f('method', '自评方法与证据'), f('result', '结果、问题及限制')],
    },
    'dual_prevention': {
        'scope': [f('object', '对象、范围及边界'), f('basis', '来源和适用阶段')],
        'risk': [f('object', '辨识对象或作业活动'), f('hazard', '风险情景及影响'), f('method', '分级方法、条件和依据')],
        'control': [f('object', '风险事项及位置'), f('measure', '管控措施'), f('responsibility', '责任岗位及执行证据')],
        'rectification': [f('problem', '问题及发现位置'), f('action', '整改措施及责任'), f('progress', '整改状态', options=['未开始', '进行中', '已完成待复查', '复查通过']), f('verification', '进展证据或复查记录')],
        'training': [f('activity', '培训或运行改进事项'), f('actual', '执行情况及记录')],
    },
})

for schema in SCHEMAS.values():
    schema['regulatory'] = REGULATORY_FIELDS
