import re
import os
import aiohttp
from abc import ABC
from typing import List

from tenacity import (
    retry, 
    stop_after_attempt, 
    retry_if_exception 
)

from qwergpt.logs import logger
from qwergpt.llms import TongyiLLM
from qwergpt.schema import Message
from qwergpt.utils import (
    parse_json,
    has_digits,
    no_digits,
    all_digits,
    should_retry,
)
from qwergpt.pipelines import PipelineData

from app.law.utils import (
    correct_case_num,
    preprocess_case_num, 
    preprocess_xzgxf_case_num,
    is_empty,
    augment_case_num,
    merge_adjacent_chars,
)
from app.law.schema import NamedEntityType


NAMED_ENTITY_RECOGNITION_PROMPT_TEMPLATE: str = """
[命名实体类型]
{named_entity_type_desc}

[注意事项]
* 案号中间如果有法院名称，请单独把法院名称识别出来
* 允许实体之间的重叠，不要完全分割识别
* 尽可能识别完整的实体名称

[问题]
{question}

[任务]
根据 **命名实体类型** 和 **注意事项**，针对 **问题** 识别出所有的命名实体。
保持 **问题** 中的原文，不要做修改。
只识别 **命名实体类型** 的类型。
问题未提供的信息，避免输出。
按照以下格式输出一个json列表:
```json
[
    {{
        "type": str = "命名实体类型",
        "content": str = "识别出的实体内容",
    }},
    ...
]
```
"""

AUGMENT_NAME_PROMPT_TEMPLATE: str = """
[任务描述]
你的任务是对给定的机构名称进行标准化和扩展。请补充可能缺少的省份、城市或区县信息，并纠正可能存在的错别字或不规范表述。

[示例]
输入: 北京丰台区人民法院
输出:
```json
[
  "北京市丰台区人民法院",
  "北京丰台区人民法院",
  "丰台区人民法院"
]
```

输入: 漳州中级人民法院
输出:
```json
[
  "福建省漳州市中级人民法院",
  "漳州市中级人民法院",
  "福建漳州中级人民法院"
]
```

[输入格式]
输入将是一个机构名称，可能是公司、法院、律师事务所或其他类型的机构。

[输出要求]
名称应从最详细到相对简略排序。
确保名称的准确性和完整性。
如果原名称中有明显错误，请在输出中予以更正。
返回一个JSON数组，包含3个标准化后的名称字符串。

[注意事项]
如果无法确定确切的省份或城市，请基于可用信息做出最佳推测。
对于不同类型的机构（如公司、法院、律师事务所等），可能需要采用不同的标准化规则。
如遇到不常见或可能有多种解释的名称，请提供多个可能的标准化版本。

请按照以上格式处理给定的机构名称，并输出JSON格式的结果，只包含标准化后的名称字符串列表。

[输入]: {name}
[输出]: """

domain = "comm.chatglm.cn"
url_prefix = f"https://{domain}/law_api/s1_b"

NAMED_ENTITY_TYPE_SET = set()
for ne in NamedEntityType:
    NAMED_ENTITY_TYPE_SET.add(ne.name)

def remove_duplicates(filtered_entities):
    seen = set()
    unique_entities = []

    for entity in filtered_entities:
        # 创建一个唯一标识符，包含 type 和 content
        identifier = (entity['type'], entity['content'])

        # 如果这个标识符之前没有出现过，就保留这个实体
        if identifier not in seen:
            seen.add(identifier)
            unique_entities.append(entity)

    return unique_entities

class Preprocessor(ABC):
    _llm: TongyiLLM

    def __init__(self, model: str):
        self._llm = TongyiLLM(model=model)

    async def recognize_named_entity(self, question):
        named_entity_type_desc = "\n".join(f"- {ne.name}: {ne.desc}" for ne in NamedEntityType)
        prompt = NAMED_ENTITY_RECOGNITION_PROMPT_TEMPLATE.format(
            named_entity_type_desc=named_entity_type_desc,
            question=question
        )
        logger.debug(f"Preprocess Prompt: {prompt}")
        messages = [
            Message(role='user', content=prompt)
        ]
        message = await self._llm.acomplete(messages)
        text = message.content
        named_entities = parse_json(text)

        return named_entities
    
    async def _augment_company_name(self, name):
        augmented_company_name_list = []

        # 合并相邻重复字符
        new_company_name = merge_adjacent_chars(name)
        augmented_company_name_list.append(new_company_name)

        # 处理「航天机电公司」这种在公司名称后面又加了一个「公司」的情况
        if len(name) > 2 and name[-2:] == '公司':
            new_company_name = name[:-2]
            augmented_company_name_list.append(new_company_name)
        
        # 处理 「北京市三元食品股份有限公司」 => 「北京三元食品股份有限公司」
        # TODO 利用大模型进行增强
        new_company_name = name.replace('省', '')
        augmented_company_name_list.append(new_company_name)

        new_company_name = name.replace('市', '')
        augmented_company_name_list.append(new_company_name)

        augmented_company_name_list = list(set(augmented_company_name_list))
        return augmented_company_name_list
    
    async def _post(self, url, data):
        team_token = os.getenv('TEAM_TOKEN')
        headers = {
            'Content-Type': 'application/json',
            'Authorization': 'Bearer ' + team_token
        }

        async with aiohttp.ClientSession() as session:
            timeout = aiohttp.ClientTimeout()
            async with session.post(url, headers=headers, json=data, timeout=timeout) as response:
                return await response.json()

    def augment_company_name_by_python(self, company_name_list: list[str]):
        augmented_company_name_list = []
        for company_name in company_name_list:
            new_company_name = company_name.replace('市', '', 1)
            if new_company_name != company_name:
                augmented_company_name_list.append(new_company_name)
            
            new_company_name = company_name.replace('省', '', 1)
            if new_company_name != company_name:
                augmented_company_name_list.append(new_company_name)

        company_name_list.extend(augmented_company_name_list)
        augmented_company_name_list = list(set(company_name_list))
        return augmented_company_name_list
    
    async def augment_name_by_llm(self, name):
        prompt = AUGMENT_NAME_PROMPT_TEMPLATE.format(name=name)
        messages = [
            Message(role='user', content=prompt)
        ]
        message = await self._llm.acomplete(messages)
        text = message.content
        augmented_name_list = parse_json(text)
        return augmented_name_list

    async def query_company_by_name(self, named_entity):
        if named_entity['type'] == '公司名称' and len(named_entity['content']) <= 4:
            named_entity['type'] = '公司简称'

        name = named_entity['content']

        # 公司简称只能查询上市公司表
        if named_entity['type'] == '公司简称':
            url = f"{url_prefix}/get_company_info"
            data = {
                "query_conds": { "公司简称": name },
                "need_fields": []
            }
            res_json = await self._post(url, data)
            if not is_empty(res_json):
                named_entity['standardized'] = res_json['公司简称']
                named_entity['found'] = True
                return
        
            # 第一步用大模型扩写增强，第二步对增强后的名称做一些处理
            augmented_company_name_list = await self.augment_name_by_llm(name)           
            augmented_company_name_list = self.augment_company_name_by_python(augmented_company_name_list)
            for augmented_company_name in augmented_company_name_list:
                data = {
                    "query_conds": { "公司简称": augmented_company_name },
                    "need_fields": []
                }
                res_json = await self._post(url, data)
                if not is_empty(res_json):
                    named_entity['standardized'] = res_json['公司简称']
                    named_entity['found'] = True
                    return
            return

        # 先查工商照面表
        url = f"{url_prefix}/get_company_register"
        data = {
            "query_conds": { "公司名称": name },
            "need_fields": []
        }
        res_json = await self._post(url, data)
        if not is_empty(res_json):
            named_entity['standardized'] = res_json['公司名称']
            named_entity['found'] = True
            return
        
        # 第一步用大模型扩写增强，第二步对增强后的名称做一些处理
        augmented_company_name_list = await self.augment_name_by_llm(name)

        # 合并相邻重复字符
        new_company_name = merge_adjacent_chars(name)
        if new_company_name != name:
            augmented_company_name_list.append(new_company_name)

        # 处理「航天机电公司」这种在公司名称后面又加了一个「公司」的情况
        if len(name) > 2 and name[-2:] == '公司':
            new_company_name = name[:-2]
            augmented_company_name_list.append(new_company_name)

        # 信息产业电子第十一设计研究院科技工程有限公司
        # 信息产业电子第十一设计研究院科技工程股份有限公司
        if len(name) > 4 and name.endswith('有限公司'):
            new_company_name = name[:-4] + '股份有限公司'
            augmented_company_name_list.append(new_company_name)

        augmented_company_name_list = self.augment_company_name_by_python(augmented_company_name_list)
        for augmented_company_name in augmented_company_name_list:
            data = {
                "query_conds": { "公司名称": augmented_company_name },
                "need_fields": []
            }
            res_json = await self._post(url, data)
            if not is_empty(res_json):
                named_entity['standardized'] = res_json['公司名称']
                named_entity['found'] = True
                return

        # 如果工商照面表查不到，再查上市公司表
        url = f"{url_prefix}/get_company_info"
        name = named_entity['content']
        data = {
            "query_conds": { "公司名称": name },
            "need_fields": []
        }
        res_json = await self._post(url, data)
        if not is_empty(res_json):
            named_entity['standardized'] = res_json['公司名称']
            named_entity['found'] = True
            return
        
        # 第一步用大模型扩写增强，第二步对增强后的名称做一些处理
        for augmented_company_name in augmented_company_name_list:
            data = {
                "query_conds": { "公司名称": augmented_company_name },
                "need_fields": []
            }
            res_json = await self._post(url, data)
            if not is_empty(res_json):
                named_entity['standardized'] = res_json['公司名称']
                named_entity['found'] = True
                return
        
        # 如果再查不到，可能是公司简称被识别成了公司名称
        # 比如: 航天机电公司
        url = f"{url_prefix}/get_company_info"
        data = {
            "query_conds": { "公司简称": name },
            "need_fields": []
        }
        res_json = await self._post(url, data)
        if not is_empty(res_json):
            named_entity['standardized'] = res_json['公司简称']
            named_entity['found'] = True
            return

        # 太长的名字就不请求了
        augmented_company_name_list = [augmented_company_name for augmented_company_name in augmented_company_name_list if len(augmented_company_name) <= 5]
        for augmented_company_name in augmented_company_name_list:
            data = {
                "query_conds": { "公司简称": augmented_company_name },
                "need_fields": []
            }
            res_json = await self._post(url, data)
            if not is_empty(res_json):
                named_entity['standardized'] = res_json['公司简称']
                named_entity['found'] = True
                return
    
    async def query_company_by_code(self, named_entity):
        if named_entity['type'] == '公司代码' and len(named_entity['content']) > 10:
            named_entity['type'] = '统一社会信用代码'


        if named_entity['type'] == '统一社会信用代码':
            unified_social_credit_code = named_entity['content']

            url = f"{url_prefix}/get_company_register_name"
            data = {
                "query_conds": {
                    "统一社会信用代码": unified_social_credit_code
                },
                "need_fields": []
            }
            res_json = await self._post(url, data)
            if not is_empty(res_json):
                named_entity['standardized'] = unified_social_credit_code
                named_entity['found'] = True
                return
        elif named_entity['type'] == '公司代码':
            stock_code = named_entity['content']

            url = f"{url_prefix}/get_company_info"
            data = {
                "query_conds": {
                    "公司代码": stock_code
                },
                "need_fields": []
            }
            res_json = await self._post(url, data)
            if not is_empty(res_json):
                named_entity['standardized'] = stock_code
                named_entity['found'] = True
                return


    async def query_case_num(self, named_entity):
        case_num = named_entity['content']
        case_num = preprocess_case_num(case_num)
        case_num = correct_case_num(case_num)

        async def _query(v):
            url = f"{url_prefix}/get_legal_document"
            data = {
                "query_conds": { "案号": v },
                "need_fields": []
            }
            res_json = await self._post(url, data)
            return res_json
        
        async def _query2(v):
            url = f"{url_prefix}/get_legal_abstract"
            data = {
                "query_conds": { "案号": v },
                "need_fields": []
            }
            res_json = await self._post(url, data)
            return res_json
        
        async def _query3(v):
            url = f"{url_prefix}/get_xzgxf_info"
            data = {
                "query_conds": { "案号": v },
                "need_fields": []
            }
            res_json = await self._post(url, data)
            return res_json
        
        res_json = await _query(case_num)
        if not is_empty(res_json):
            named_entity['type'] = 'LegalDoc案号'
            named_entity['standardized'] = res_json['案号']
            named_entity['found'] = True
            return
        
        # 从问题中直接提取的案号查询不到法律文书
        # 就对案号进行增强，增加一些可能性的尝试
        augmented_case_num_list = augment_case_num(case_num)
        for augmented_case_num in augmented_case_num_list:
            res_json = await _query(augmented_case_num)
            if not is_empty(res_json):
                named_entity['type'] = 'LegalDoc案号'
                named_entity['standardized'] = res_json['案号']
                named_entity['found'] = True
                return
        
        # 如果不是 LegalDoc，可能是 LegalAbstract
        case_num = case_num.replace('(', '（').replace(')', '）')
        res_json = await _query2(case_num)
        if not is_empty(res_json):
            named_entity['type'] = 'LegalAbstract案号'
            named_entity['standardized'] = res_json['案号']
            named_entity['found'] = True
            return
        
        for augmented_case_num in augmented_case_num_list:
            case_num = augmented_case_num.replace('(', '（').replace(')', '）')
            res_json = await _query(case_num)
            if not is_empty(res_json):
                named_entity['type'] = 'LegalAbstract案号'
                named_entity['standardized'] = res_json['案号']
                named_entity['found'] = True
                return

        # 如果不是 LegalDoc 或者 LegalAbstract，可能是限高案号
        case_num = preprocess_xzgxf_case_num(case_num)
        res_json = await _query3(case_num)
        if not is_empty(res_json):
            named_entity['type'] = 'XzgxfInfo案号'
            named_entity['standardized'] = res_json['案号']
            named_entity['found'] = True
            return
        
        for augmented_case_num in augmented_case_num_list:
            case_num = preprocess_xzgxf_case_num(augmented_case_num)
            res_json = await _query3(case_num)
            if not is_empty(res_json):
                named_entity['type'] = 'XzgxfInfo案号'
                named_entity['standardized'] = res_json['案号']
                named_entity['found'] = True
                return


    def augment_lawfirm_name(self, lawfirm_name_list: str) -> list[str]:
        augmented_lawfirm_name_list = []

        for lawfirm_name in lawfirm_name_list:
            pattern = r'^(.*?)(事务所)$'
            match = re.match(pattern, lawfirm_name)
            if match:
                prefix = match.group(1)
                if "律师" not in prefix:
                    augmented_lawfirm_name_list.append(f"{prefix}律师事务所")

        lawfirm_name_list.extend(augmented_lawfirm_name_list)
        augmented_lawfirm_name_list = list(set(lawfirm_name_list))
        return augmented_lawfirm_name_list

    async def query_lawfirm(self, named_entity):
        lawfirm_name = named_entity['content']

        async def _query(v):
            url = f"{url_prefix}/get_lawfirm_info"
            data = {
                "query_conds": { "律师事务所名称": v },
                "need_fields": []
            }
            res_json = await self._post(url, data)
            return res_json

        res_json = await _query(lawfirm_name)
        if not is_empty(res_json):
            named_entity['standardized'] = res_json['律师事务所名称']
            named_entity['found'] = True
            return
        
        augmented_lawfirm_name_list = await self.augment_name_by_llm(lawfirm_name)

        # 特殊处理一下，有的时候大模型没有增加律师事务所后缀
        pattern = r'^(.*?)(事务所)$'
        match = re.match(pattern, lawfirm_name)
        if match:
            prefix = match.group(1)
            if "律师" not in prefix:
                augmented_lawfirm_name_list.append(f"{prefix}律师事务所")

        augmented_lawfirm_name_list = self.augment_lawfirm_name(augmented_lawfirm_name_list)
        for augmented_lawfirm_name in augmented_lawfirm_name_list:
            res_json = await _query(augmented_lawfirm_name)
            if not is_empty(res_json):
                named_entity['standardized'] = res_json['律师事务所名称']
                named_entity['found'] = True
                return

    async def query_court(self, named_entity):
        court_name = named_entity['content']

        async def _query(v):
            url = f"{url_prefix}/get_court_info"        
            data = {
                "query_conds": { "法院名称": v },
                "need_fields": []
            }
            res_json = await self._post(url, data)
            return res_json

        res_json = await _query(court_name)
        if not is_empty(res_json):
            named_entity['standardized'] = res_json['法院名称']
            named_entity['found'] = True
            return

        augmented_court_name_list = await self.augment_name_by_llm(court_name)
        for augmented_court_name in augmented_court_name_list:
            res_json = await _query(augmented_court_name)
            if not is_empty(res_json):
                named_entity['standardized'] = res_json['法院名称']
                named_entity['found'] = True
                return

    async def query_named_entity(self, named_entity):
        # 类型不对要修正
        if len(named_entity['content']) == 6 and all_digits(named_entity['content']):
            named_entity['type'] = '公司代码'

        if named_entity['type'] == '公司名称' \
            or named_entity['type'] == '公司简称':
            await self.query_company_by_name(named_entity)
            return

        if named_entity['type'] == '公司代码' \
            or named_entity['type'] == '统一社会信用代码':
            await self.query_company_by_code(named_entity)
            return

        if named_entity['type'] == '案号':
            await self.query_case_num(named_entity)
            return
        
        if named_entity['type'] == '律师事务所名称':
            await self.query_lawfirm(named_entity)
            return

        if named_entity['type'] == '法院名称':
            await self.query_court(named_entity)
            return

    async def run(self, pipeline_data: PipelineData) -> PipelineData:
        question = pipeline_data.get('rewriter.question')

        # TODO 还是需要运行两次，有的时候一次识别不出来
        preprocessed_question = question
        for i in range(1):
            preprocessed_question = await self._run_once(question)
            if preprocessed_question != question:
                break

        pipeline_data.set('preprocessor.question', preprocessed_question)
        return pipeline_data

    def filter_entities(self, named_entities):
        named_entities = [named_entity for named_entity in named_entities if 'content' in named_entity]
        named_entities = [named_entity for named_entity in named_entities if 'type' in named_entity]
        named_entities = [named_entity for named_entity in named_entities if named_entity['type'] in NAMED_ENTITY_TYPE_SET]
        # 识别出其他字段的命名实体，目前看都是问题，不包含具体名称
        named_entities = [named_entity for named_entity in named_entities if len(named_entity.keys()) == 2]

        filtered_entities = []

        for named_entity in named_entities:
            if named_entity['content'] == '':
                continue
            # 过滤掉大模型识别出的不合理的内容
            if '未提供' in named_entity['content'] \
                or '未知' in named_entity['content']:
                continue
            if '公司' == named_entity['content'] \
                or '子公司' == named_entity['content'] \
                or '子公司列表' == named_entity['content'] \
                or '全资子公司' == named_entity['content'] \
                or '法院' == named_entity['content'] \
                or '法院名称' == named_entity['content'] \
                or '人民法院' == named_entity['content'] \
                or '中级人民法院' == named_entity['content']:
                continue
            if named_entity['type'] == '律师事务所名称':
                if '原告' in named_entity['content']:
                    continue
                if '被告' in named_entity['content']:
                    continue
            elif named_entity['type'] == '法院名称':
                if '哪几家' in named_entity['content'] \
                    or '最基层的' in named_entity['content'] \
                    or '审理法院' in named_entity['content']:
                    continue
                if '法院' not in named_entity['content']: 
                    continue
                # 避免把法院代字「皖01」替换成法院名称
                if has_digits(named_entity['content']):
                    continue
                if len(named_entity['content']) < 4:
                    continue
            elif named_entity['type'] == '案号':
                if no_digits(named_entity['content']):
                    continue
                # (2019)年湖北襄阳市中级人民法院民初1613号案 这种情况在后面处理
                if '法院' in named_entity['content']:
                    continue
                if len(named_entity['content']) < 4:
                    continue
            elif named_entity['type'] == '统一社会信用代码':
                if no_digits(named_entity['content']):
                    continue
            elif named_entity['type'] == '公司代码':
                # TODO 公司代码不会用中文数字吧？
                if no_digits(named_entity['content']):
                    continue

            filtered_entities.append(named_entity)

        # 把 type 和 content 都相同的过滤掉
        filtered_entities = remove_duplicates(filtered_entities)

        return filtered_entities

    @retry(stop=stop_after_attempt(3), retry=retry_if_exception(should_retry))
    async def _run_once(self, question: str):
        named_entities = await self.recognize_named_entity(question)
        named_entities = self.filter_entities(named_entities)

        # print(named_entities)
        queried_set = set()
        for named_entity in named_entities:
            # 把 standardized 字段初始化为它原内容，方便后续做字符串替换
            if named_entity['content'] in queried_set:
                continue
            # 已查询的内容跳过查询
            queried_set.add(named_entity['content'])

            named_entity['standardized'] = named_entity['content']
            await self.query_named_entity(named_entity)
        # print(named_entities)

        # 将原问题中非标准化的命名实体替换或补充标准化的命名实体
        NER: dict[str, List] = {}
        for named_entity in named_entities:
            if 'standardized' not in named_entity:
                continue

            # 如果命中记录，则做类型标识
            standardized = named_entity['standardized']
            if 'found' in named_entity:        
                NER[named_entity['type']] = named_entity['standardized']

            question = question.replace(
                named_entity['content'], standardized, 1
            )

        preprocessed_question = f"QUERY: {question}\nNER: {NER}"
        return preprocessed_question
