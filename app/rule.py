RULE_PROMPT: str = """
[字段映射]
查询的字段不一定是准确的字段名称，需要根据查询的字段，改成准确的字段名称。比如:
* 邮编: 邮政编码（CompanyInfo 表）
* 申请人、上诉人: 原告（LegalDoc 表）
* 控股公司: 关联上市公司全称（SubCompanyInfo 表）
* 申请人、被申请人: 原告、被告（LegalDoc 表）或申请人（XzgxfInfo 表）
* 判决当天: 日期（LegalDoc 表）

[公司规则]
* 对于题目中提到的任何公司名称，必须严格按照以下步骤进行公司名称的验证和确认:
    1. 首先使用 get_company_info 工具查询公司名称
    2. 如果 get_company_info 返回空列表，则使用 get_company_register 工具查询公司名称
    3. 将查询到的准确公司名称保存为变量，用于所有后续涉及该公司的操作

```python
company_info = get_company_info("示例公司名称")
if not company_info:
    company_register = get_company_register("示例公司名称")
    company_name = company_register.get("公司名称")
else:
    company_name = company_info.get("公司名称")
```

* 如果给出的是统一社会信用代码:
    1. 首先使用 get_company_register_name 工具获取结果
    2. 从返回的字典中提取 "公司名称" 字段作为准确公司名称
    3. 将提取的准确公司名称保存为变量，用于所有后续涉及该公司的操作
* 严禁在未经验证的情况下直接使用题目中给出的公司名称或统一社会信用代码进行后续查询或操作
* 在所有涉及公司名称的后续步骤中，必须使用经过验证的准确公司名称作为参数，而不是直接使用问题中给出的公司名称。
* 每次使用公司名称作为参数时，都应该引用之前验证步骤中获得的准确公司名称变量。
* 根据 **字段映射**，确定需要查询的字段属于哪张数据表:
    1. CompanyInfo 表: 上市公司
    2. CompanyRegister 表: 所有公司（上市公司和非上市公司）
* 上市公司和非上市公司都可以涉案和限制高消费
* 涉及 CompanyRegister 的字段，上市公司和非上市公司都可以使用 get_company_register 工具
* 查询本公司的控股公司或本公司的被投资信息:
    1. 使用 get_parent_company_info 工具获取控股公司信息
    2. 从返回结果中提取:
        a. 控股公司名称: '关联上市公司全称'
        b. 全资子公司: 上市公司参股比例等于浮点数 100.0（float）
        c. 被投资金额: 上市公司投资金额
* 查询本公司的子公司信息:
    1. 使用 get_sub_company_info_list 工具获取子公司列表
    2. 从返回结果中提取子公司信息
* **上市公司参股比例** 是数字字符串，没有百分比 % 符号，使用 convert_to_float 工具转成 float 类型比较
* 查询公司的行业，有两种情况:
    1. CompanyInfo 表使用的是 **所属行业**
    2. CompanyRegister 表使用的是 **行业一级**、**行业二级** 和 **行业三级**
* 上市公司投资金额比较，使用 convert_to_float 工具转成 float

[案件规则]
* 案号格式: （起诉年份）+ 法院代字 + 案件类型代字 + 案件编号 + "号"
* 查询案件相关信息时，首先使用 get_legal_document 工具，包括原告、被告等关键信息。
* 根据案号查询法院代字、法院级别:
    1. 根据案号使用 extract_code_from_case_num 工具得到法院代字
    2. 根据上一步的结果，使用 get_court_code 工具得到 CourtCode 表
    3. 如果 get_court_code 返回空结果，跳过后续依赖于该结果的步骤
* 查询民事初审案件时，判断案号是否包含"民初"字符串，而不是从文书类型中判断
* 涉案时间，默认为"起诉日期"，如果问题中有特殊说明，按照问题的提示
* 判断案件胜诉方、败诉方时，通过 LegalDoc 的"判决结果"字段进行判断
* 处理案件的 **原告律师事务所** 或 **被告律师事务所** 时，必须考虑以下三种情况并严格执行：
    1. 空字符串：必须跳过，不进行任何计数或处理
    2. 单个律师事务所：作为一个独立项进行计数或处理
    3. 多个律师事务所：以 "," 分隔，需要分别计数或处理每个律师事务所
* 在进行律师事务所相关的统计或分析时，必须首先检查字段是否为空，如果为空则跳过，以避免将空字符串误认为是有效的律师事务所名称
* 使用 split(',') 方法处理可能包含多个律师事务所的字段时，必须先检查原字符串是否为空，如果为空则不执行 split() 操作
* 原告律师事务所地址、被告律师事务所地址，根据律师事务所名称使用 get_lawfirm_info 工具
* 查询审理城市、地点，根据审理法院的地址，使用 get_address_info 工具
* 查询公司作为原告或被告的案件，确定公司在案件中的身份：
    a. 使用 get_legal_document_list 工具获取案件列表，遍历案件列表，检查公司名称是否在"原告"或"被告"字段中
    b. 如果公司名称在"原告"字段中，则公司为原告，对方为被告，对方律师事务所是被告律师事务所
    c. 如果公司名称在"被告"字段中，则公司为被告，对方为原告，对方律师事务所是原告律师事务所

```python
# company_name 是通过公司规则得到的准确公司名称
opposite_lawfirm_name = legal_doc.get("原告律师事务所") if company_name in legal_doc.get("被告") else legal_doc.get("被告律师事务所")
```
    
* 查询审理法院:
    1. 根据案号使用 extract_code_from_case_num 工具得到法院代字
    2. 根据上一步的结果，使用 get_court_code 工具得到 CourtCode 表
    3. 从 CourtCode 表的返回结果中提取 "法院名称" 字段作为法院名称字符串
    4. 使用提取的法院名称字符串作为参数，调用 get_court_info 工具获取 CourtInfo 表
* 确定法院名称:
    1. 首先检查问题中是否直接给出了法院名称
    2. 如果问题中直接给出了法院名称，直接使用该名称
    3. 如果问题中没有直接给出法院名称，则按以下步骤操作：
        a. 根据案号使用 extract_code_from_case_num 工具得到法院代字
        b. 根据上一步的结果，使用 get_court_code 工具得到 CourtCode 表
        c. 从 CourtCode 表的返回结果中提取 "法院名称" 字段作为法院名称字符串
* 获取法院详细信息:
    1. 无论法院名称是直接给出还是通过案号解析得到，都使用该名称作为参数调用 get_court_info 工具获取 CourtInfo 表
    2. 从 CourtInfo 表中获取所需的法院详细信息，如法院负责人
* 严禁直接从 LegalDoc 表中读取法院名称

[法院规则]
* 根据 **字段映射**，确定需要查询的字段属于哪张数据表:
    1. CourtInfo 表: 包括法院负责人、成立日期、法院地址、法院联系电话、法院官网
    2. CourtCode 表: 包括法院代字、法院级别等
* 法院级别: 使用 get_court_code 工具获取 **法院级别** 字段
    a. 法院排序（从小到大）: 基层法院、中级法院、高级法院和最高法
* 获取法院名称:
    1. 如果问题中直接给出了法院名称，直接使用该名称
    2. 如果需要从案号解析，使用 get_court_code 工具获取 CourtCode 表，然后从返回的字典中提取 法院名称 字段
* 获取法院详细信息:
    1. 无论法院名称是直接给出还是通过案号解析得到，都使用该名称作为参数调用 get_court_info 工具获取 CourtInfo 表
    2. 从 CourtInfo 表中获取所需的法院详细信息，如法院负责人

[日期规则]
* 查询日期: 默认使用年份，但是问题可能缩写，省略了年份的前两位数字，请补充。
* 案件审理年份: 使用 extract_year_from_case_num 工具获取，返回结果是 int
* 案件判决当天: 使用 get_legal_document 获取 **日期** 字段，格式为 yyyy-MM-DD HH:mm:ss
* 案件立案年份: 使用 extract_year_from_case_num 工具获取，返回结果是 int
* 案件起诉年份: 使用 extract_year_from_case_num 工具获取，返回结果是 int
* 公司涉诉年份: 如无特殊说明，默认使用案件起诉日期，即案件案号的年份
如果需要转换日期格式，可以使用适当的日期处理工具或函数。

[地址规则]
* 获取地址:
    * 法院地址: 使用 get_court_info 工具获取 **法院地址** 字段
    * 律师事务所地址: 使用 get_lawfirm_info 工具获取 **律师事务所地址** 字段
    * 公司地址: 使用 get_company_info 工具，根据查询需求判断使用 **注册地址**、**办公地址** 或 **企业地址** 字段
* 查询 **城市区划代码**、**区县区划代码**，需要使用 get_address_code 工具。但是有2种情况:
    1. 法院、律师事务所、公司，需要地址使用 get_address_info 工具，地址来源参考 **获取地址**：        
    2. 问题中的地址参数: XX省XX市XX区，提取参数直接使用 get_address_code 工具
* 查询公司的 **注册地址**，需要判断公司是否为上市公司：
    a. 首先使用 get_company_info 工具获取 **注册地址**，判断结果是否为空列表
    b. 如果上一步结果为空列表，则使用 get_company_register 工具获取 **企业地址**
* 查询所在什么地方、所在城市、所在地区、所在区县：
    1. 首先参考 **获取地址** 规则，得到完整地址
    2. 然后使用 get_address_info 工具，将完整地址作为参数进行查询
    3. 从 get_address_info 返回的结果中提取相应的信息（省份、城市、区县等）

[单位规则]
你需要区分查询单位和原始单位。
如果查询单位和原始单位不一致:
    1. 第一步，使用 convert_to_float 工具转换成浮点数
    2. 第二步，使用 convert_amount_unit 工具统一单位比较
* 查询单位: 默认使用 **元**，如果问题有特殊说明单位，请使用问题里的单位
* 原始单位:
    * 涉案金额: float，元
    * 公司注册资本: float，万元
    * 上市公司投资金额: string，单位在字符串中
    * 首发募资净额: float，万元
    * 律师事务所注册资本: string，单位在字符串中
* 查询如果没有说明单位，使用原始单位
* 使用 convert_amount_unit 工具时，除非问题明确要求保留特定小数位数，否则不要设置小数点位数参数

[报告规则]
* 查询公司的工商信息
* 查询符合问题要求的该公司子公司列表
* 查询符合问题要求的裁判文书（LegalDoc）列表
* 查询符合问题要求的限制高消费（XzgxfInfo）列表
查询以上信息后，使用 save_dict_list_to_word 工具，具体使用方法参考 **工具列表**

[天气规则]
* 使用 get_temp_info 工具需要省份、城市和日期
* 使用 get_address_info 工具获取省份、城市，需要地址，地址严格按照以下方式获取:
    a. 律师事务所地址: get_lawfirm_info 工具
    b. 法院地址: get_court_info 工具

[常见错误]
* 严重错误：直接从裁判文书（LegalDoc）读取法院名称或法院地址。正确步骤如下（必须严格遵守）：
    1. 根据案号使用 extract_code_from_case_num 工具得到法院代字
    2. 根据上一步的结果，使用 get_court_code 工具得到 CourtCode 表
    3. 从 CourtCode 表的返回结果中提取 "法院名称" 字段作为法院名称字符串
    3. 使用提取的法院名称字符串作为参数，调用 get_court_info 工具获取 CourtInfo 表
* 在后续步骤中直接使用问题中给出的公司名称，而不是使用经过验证的准确公司名称。
* 忽视公司名称验证流程，直接进行后续查询操作。
* 错误使用工具，反思 **工具列表** 里各个工具的描述
* 错误使用工具查询控股公司名称，正确步骤是 get_parent_company_info 工具获取 **关联上市公司全称** 字段
* 错误假设参数，正确步骤是使用 **问题** 的参数，或使用工具得到的参数
* 错误读取字段，正确步骤是根据 **工具列表** 的 Returns 描述，读取 **数据表定义** 的字段

[答题思路]
1. 仔细阅读并理解问题，提取关键信息和查询条件
2. NER 是根据 QUERY 做的命名实体识别结果，提取其中信息作为变量
3. 对于涉及的每个公司名称，严格按照 [公司规则] 进行验证
    a. 先使用 get_company_info 工具查询
    b. 如果返回空列表，则使用 get_company_register 工具查询
    c. 对于统一社会信用代码，使用 get_company_register_name 工具查询
    d. 将验证后的准确公司名称保存为变量，用于后续所有操作
4. 根据问题类型（公司信息、案件信息、法院信息、律师事务所信息、地址查询、天气查询等），参考相应的规则部分
5. 制定查询计划，明确使用的工具和查询顺序
6. 执行查询，注意事项:
    * 使用验证过的公司名称、法院名称和律师事务所名称
    * 使用正确的参数
    * 对于可能返回空结果的工具调用（如 get_court_code），添加适当的条件检查和错误处理逻辑
7. 处理特殊字段（如律师事务所）时：
    - 检查字段是否为空，如果为空则跳过
    - 对于可能包含多个值的字段，先检查是否为空，再进行分割处理
    - 确保不会将空值误认为有效数据进行处理
8. 进行单位转换时，除非问题明确要求保留特定小数位数，否则不要在 convert_amount_unit 工具中设置小数点位数参数
9. 整理查询结果，确保答案完整且符合问题要求
10. 查询结果验证:
    - 检查所有查询结果是否合理且符合预期
    - 验证关键信息(如公司名称、金额、日期)的一致性
    - 如果发现异常，重新检查查询过程和使用的参数
11. 检查是否违反了 [常见错误] 中列出的任何点
12. 如需生成报告，参考 [报告规则] 使用相应工具
"""