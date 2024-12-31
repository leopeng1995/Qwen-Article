from abc import ABC
from collections import defaultdict

from tenacity import (
    retry, 
    stop_after_attempt, 
    retry_if_exception
)

from qwergpt.llms import (
    TongyiLLM,
)
from qwergpt.schema import Message
from qwergpt.logs import logger
from qwergpt.utils import (
    parse_json,
    should_retry, 
)
from qwergpt.pipelines import PipelineData

from app.law.schema import ALL_DATABASE_SCHEMA


# 与数据表关联的工具
TABLE_TOOL_MAP = {
    "CompanyInfo": ["get_company_info"],
    "CompanyRegister": ["get_company_register", "get_company_register_name"],
    "SubCompanyInfo": ["get_parent_company_info", "get_sub_company_info_list"],
    "LegalDoc": ["get_legal_document", "get_legal_document_list", "get_legal_abstract", "extract_year_from_case_num", "extract_code_from_case_num"],
    "CourtInfo": ["get_court_info", "extract_code_from_case_num"],
    "CourtCode": ["get_court_code", "extract_code_from_case_num"],
    "LawfirmInfo": ["get_lawfirm_info"],
    "LawfirmLog": ["get_lawfirm_log"],
    "AddrInfo": ["get_address_info"],
    "AddrCode": ["get_address_code"],
    "TempInfo": ["get_temp_info"],
    "LegalAbstract": ["get_legal_abstract"],
    "XzgxfInfo": ["get_xzgxf_info", "get_xzgxf_info_list", "extract_year_from_case_num"],
}


FILTER_DATABASE_PROMPT_TEMPLATE: str = """
[数据表定义]
{database_schema}

[字段预处理]
问题的字段名称可能与数据库的字段名称存在差异，可能使用近义词、同义词、简称或者缩写，需要做字段预处理，统一成数据库的字段名称。

例子:
* 注册编号、注册编码: 注册号
* 成立时间、创办日期: 成立日期
* 法人: 法定代表人
* 邮编: 邮政编码
* 办公地点: 办公地址
* 联系方式: 联系电话、传真、电子邮箱
* 代字: 法院代字
* 传真号码、传真电话: 传真

[注意事项]
* 查询公司注册在哪个区县，需要查询 **CompanyInfo** 表的 **注册地址** 字段，再根据 **注册地址** 字段值查询 **AddrInfo** 表
* 查询公司法人，需要 **CompanyInfo** 表和 **CompanyRegister** 表
* 查询 **城市区划代码**、**区县区划代码**，需要 **AddressCode** 表
* 查询法院的 **城市区划代码**、**区县区划代码**，需要 **CourtInfo** 表
* 查询案件的审理法院，需要 **CourtCode** 表
* 查询公司、法院、律师事务所的天气情况，需要相应的地址
* 查询公司、法院、律师事务所在什么地方，除了地址，还需要回答省份、城市、区县信息，需要 **AddrInfo** 表
* 查询公司的基本信息（如主营业务、传真、电子邮箱等），优先使用 **CompanyInfo** 表
* 查询公司的工商登记信息（如统一社会信用代码、注册资本等），使用 **CompanyRegister** 表
* 如果需要同时查询公司的基本信息和工商登记信息，需要同时使用 **CompanyInfo** 表和 **CompanyRegister** 表
* 在回答问题时，请确保使用数据表定义中列出的准确字段名称。
* 公司代码，需要 CompanyInfo 表
* 统一社会信用代码，需要 CompanyRegister 表

[问题]
{question}

[任务]
根据 **数据表定义** 和 **注意事项**，判断需要查询哪些表才能回答 **问题**。
请仔细考虑问题中的关键信息，以确定正确的查询表。
请务必使用数据表定义中列出的准确字段名称。
按照以下格式输出一个json列表:
```json
[
    {{
        "table_name": str = "数据表的英文名称",
        "fields": str = "问题里涉及到数据表的准确字段名称",
    }},
    ...
]
```
"""


def merge_tables(tables):
    # 使用 defaultdict 来分组相同 table_name 的元素
    merged = defaultdict(set)
    
    # 遍历输入的列表
    for item in tables:
        # 将 fields 字符串分割成集合，并添加到对应的 table_name 中
        merged[item['table_name']].update(item['fields'].split(','))
    
    # 将结果转换为所需的格式
    result = [{'table_name': k, 'fields': ','.join(sorted(v))} for k, v in merged.items()]
    
    return result


def fix_tables_field(tables):
    for item in tables:
        if isinstance(item['fields'], str):
            if '律师事务所成立日期' in item['fields']:
                item['fields'] = item['fields'].replace('律师事务所成立日期', '事务所成立日期')
            if '律师事务所注册资本' in item['fields']:
                item['fields'] = item['fields'].replace('律师事务所注册资本', '事务所注册资本')


class Filter(ABC):

    def __init__(self, model: str = 'glm-4-air'):
        self._llm = TongyiLLM(model=model)

    async def _filter(self, question):
        # 筛选数据表、工具
        messages = []
        filter_prompt = FILTER_DATABASE_PROMPT_TEMPLATE.format(
            database_schema=ALL_DATABASE_SCHEMA,
            question=question
        )
        logger.debug(f"Filter Prompt: {filter_prompt}")
        messages.append(
            Message(role='user', content=filter_prompt)
        )
        message = await self._llm.acomplete(messages)
        messages.append(message)
        
        return message

    def _complement_fields(self, filtered_tables):
        # 需要补充一些字段，比如主键
        for tbl in filtered_tables:
            if tbl['table_name'] == 'LegalDoc' and '案号' not in tbl['fields']:
                tbl['fields'] = tbl['fields'] + f", 案号"

        return filtered_tables
    
    def _expand_tables(self, question, tables: list):
        table_names = set([t['table_name'] for t in tables])

        # 扩充过滤表，因为可能缺乏信息，比如涉及公司的问题要先去查上市公司表
        # 因为上市公司表的法定代表人和工商照面表有很多是不一致的
        # 工商是一年一更新，上市公司最慢是一季度一更新，如果有增减持会时时更新
        if 'CompanyRegister' in table_names and 'CompanyInfo' not in table_names:
            if '法人' in question or '法定代表人' in question:
                tables.append({
                    'fields': '公司名称, 法人代表',
                    'table_name': 'CompanyInfo'
                })
            if '公司简称' in question:
                tables.append({
                    'fields': '公司名称, 公司简称',
                    'table_name': 'CompanyInfo'
                })
        # 为了解决「北京市密云区人民法院所在的区县区划代码是多少」
        if 'CourtCode' in table_names or 'CourtInfo' in table_names:
            if '区县区划代码' in question:
                tables.append({
                    'fields': '地址',
                    'table_name': 'AddrInfo'
                })
                tables.append({
                    'fields': '区县区划代码',
                    'table_name': 'AddrCode'
                })
                tables.append({
                    'fields': '法院名称,法院地址',
                    'table_name': 'CourtInfo'
                })

        return tables

    @retry(stop=stop_after_attempt(3), retry=retry_if_exception(should_retry))
    async def run(self, pipeline_data: PipelineData) -> PipelineData:
        question = pipeline_data.get('preprocessor.question')

        message = await self._filter(question)
        text = message.content
        filtered_tables =  parse_json(text)

        filtered_tables = self._complement_fields(filtered_tables)
        filtered_tables = self._expand_tables(question, filtered_tables)

        # 去除重复项
        filtered_tables = merge_tables(filtered_tables)

        # 替换容易错的字段名称
        fix_tables_field(filtered_tables)

        filtered_tool_list = []
        for table in filtered_tables:
            table_name = table['table_name']
            if table_name in TABLE_TOOL_MAP:
                filtered_tool_list.extend(TABLE_TOOL_MAP[table_name])

        # 去除重复项
        filtered_tool_list = list(set(filtered_tool_list))

        # 增加无关数据表的工具函数
        common_tool_list = [
            'convert_amount_unit',
            'convert_to_float',
            'rank',
        ]
        filtered_tool_list.extend(common_tool_list)

        print(question)
        if '整合报告' in question:
            filtered_tool_list.append('save_dict_list_to_word')

        pipeline_data.set('filtered_tables', filtered_tables)
        pipeline_data.set('filtered_tool_list', filtered_tool_list)

        return pipeline_data
