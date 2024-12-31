from abc import ABC
from typing import Dict, Any

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
    should_retry
)

from app.law.tools import (
    get_company_sue_company,
    get_citizens_sue_citizens,
    get_company_sue_citizens,
    get_citizens_sue_company,
)


EXTRACT_SYSTEM_PROMPT: str = """你是一名信息提取的专家。"""

EXTRACT_PROMPT_TEMPLATE: str = """
[民事起诉状类型]
1. 公民起诉公民
**示例公司名称A法人** 与 **示例公司名称B** 发生了买卖合同纠纷
-------------------

2. 公司起诉公民
**示例公司名称A** 与 **示例公司名称B法人** 发生了买卖合同纠纷
-------------------

3. 公民起诉公司
**示例公司名称A法人** 与 **示例公司名称B** 发生了买卖合同纠纷
-------------------

4. 公司起诉公司
**示例公司名称A** 与 **示例公司名称B** 发生了买卖合同纠纷
-------------------

[参考示例]
问题: **示例公司名称A法人**与 **示例公司名称B** 发生了买卖合同纠纷，**示例公司名称A** 委托给了 **示例律师事务所名称A**，**示例公司名称B** 委托给了 **示例律师事务所名称B**，请写一份民事起诉状给 **示例法院名称** 时间是 **yyyy-MM-dd**
解释: 问题中出现"法人"，代表的是公民。当原告或被告名称后面直接跟"法人"时，应将其视为公民。如果没有"法人"，则视为公司。
输出:
```json
{{
    "plaintiff_name": str = "示例公司名称A法人",
    "defendant_name": str = "示例公司名称B",
    "cause": str = "买卖合同纠纷",
    "plaintiff_lawfirm": str = "示例律师事务所名称A",
    "defendant_lawfirm": str = "示例律师事务所名称B",
    "court_name": str = "示例法院名称",
    "date": str = "yyyy-MM-dd"
    "type": str = "公民起诉公司"
}}
```

[问题]
{question}

[任务]
根据 **参考示例**，针对 **问题** 提取信息。
注意：当原告或被告名称后面直接跟"法人"时，应将其视为公民，保留"法人"在名称中。如果名称后没有"法人"，则视为公司。

输出以下json对象:
```json
{{
    "plaintiff_name": str = "原告名称",
    "defendant_name": str = "被告名称",
    "cause": str = "案由",
    "plaintiff_lawfirm_name": str = "原告律师事务所名称",
    "defendant_lawfirm_name": str = "被告律师事务所名称",
    "court_name": str = "受理法院名称",
    "date": str = "yyyy-MM-dd"
    "type": str = "民事起诉状类型"
}}
```
"""


class LawSue(ABC):

    _llm: TongyiLLM

    def __init__(self):
        self._llm = TongyiLLM()

    def _augment(self, question: str, obj: Dict[str, Any]) -> Dict[str, Any]:
        if '法人' in obj['plaintiff_name']:
            obj['type'] = '公民' + obj['type'][2:]
        elif '法人' in obj['defendant_name']:
            obj['type'] = obj['type'][:4] + '公民'
        
        # 处理问题中可能出现的"的法人"情况
        if f"{obj['plaintiff_name']}的法人" in question:
            obj['plaintiff_name'] += '法人'
            obj['type'] = '公民' + obj['type'][2:]
        if f"{obj['defendant_name']}的法人" in question:
            obj['defendant_name'] += '法人'
            obj['type'] = obj['type'][:4] + '公民'
        
        return obj

    @retry(stop=stop_after_attempt(3), retry=retry_if_exception(should_retry))
    async def run(self, question):
        prompt = EXTRACT_PROMPT_TEMPLATE.format(
            question=question
        )
        messages = [
            Message(role='system', content=EXTRACT_SYSTEM_PROMPT),
            Message(role='user', content=prompt),
        ]
        message = await self._llm.acomplete(messages)

        obj = parse_json(message.content)
        if 'type' not in obj or obj['type'] not in [
            '公司起诉公司', '公民起诉公民', '公司起诉公民', '公民起诉公司'
        ]:
            raise ValueError('Invalid LawSue type')

        obj = self._augment(question, obj)

        if obj['plaintiff_name'] and '法人' in obj['plaintiff_name']:
            obj['type'] = f"公民{obj['type'][2:]}"

        if obj['defendant_name'] and '法人' in obj['defendant_name']:
            obj['type'] = f"{obj['type'][0:4]}公民"

        sue_functions = {
            '公司起诉公司': get_company_sue_company,
            '公民起诉公民': get_citizens_sue_citizens,
            '公司起诉公民': get_company_sue_citizens,
            '公民起诉公司': get_citizens_sue_company,
        }

        return sue_functions[obj['type']](
            plaintiff_name=obj['plaintiff_name'],
            defendant_name=obj['defendant_name'],
            cause=obj['cause'],
            plaintiff_lawfirm_name=obj['plaintiff_lawfirm_name'],
            defendant_lawfirm_name=obj['defendant_lawfirm_name'],
            court_name=obj['court_name'],
            date=obj['date']
        )
