from abc import ABC

from tenacity import (
    retry, 
    stop_after_attempt, 
    retry_if_exception
)

from qwergpt.llms import TongyiLLM
from qwergpt.schema import Message
from qwergpt.utils import (
    parse_json,
    should_retry,
    format_filtered_tables, 
    group_api_calls2,
    count_api_calls,
    count_unique_api_tools,
    count_serial_api_calls, 
    count_unique_serial_api_calls,
)
from qwergpt.logs import logger

from app.rule import RULE_PROMPT
from app.law.tools import generate_tools_desc

SUMMARIZE_PROMPT_TEMPLATE: str = """
[数据表定义]
{database_schema}

[工具列表]
{tools_desc}

[参考示例]
查询: **示例案号** 的法院在哪个区县？
任务1: 根据案号的 **法院代字**，使用 get_court_code 工具查询 **法院名称**
任务2: 根据 __任务1结果__，使用 get_court_info 工具查询 **法院地址**
任务3: 根据 __任务2结果__，使用 get_address_info 查询 **省份**、**城市**、**区县**
----------

查询: **示例公司简称** 的参保人数有多少人？
任务1: 根据 **公司简称**，使用 get_company_info 工具查询 **公司名称**
任务2: 根据 __任务1结果__，使用 get_company_register 工具查询 **参保人数**
----------

[字段筛选]
{filtered_fields}

{rule}

[问题]
{question}

[任务]
**数据表定义** 描述了数据表的字段信息。
**字段映射** 描述了问题的字段对应关系。
**工具列表** 描述了如何使用相关的工具。
**答题思路** 描述了常用的答题思路。
参考 **参考示例**，根据 **字段筛选**，确定需要哪些工具查询对应的数据表，
仔细阅读 **工具列表** 的工具描述，针对 **问题** 编写一个计划，以解决问题。

按照以下格式输出一个json列表:
```json
[
    {{
        "task_id": str = "计划中任务的唯一标识符，可以是序号",
        "dependent_task_ids": list[str] = "此任务先决条件的任务ids",
        "used_tool": str = "使用的工具名称",
        "instruction": "在此任务中应执行的操作，一个简短的短语或句子，描述使用的工具名称，包括 **问题** 中的参数",
    }},
    ...
]
```
"""


# 以下是自己定义的工具，需要排除
FILTERED_TOOL_SET = set()
FILTERED_TOOL_SET.add('convert_amount_unit')
FILTERED_TOOL_SET.add('convert_to_float')
FILTERED_TOOL_SET.add('rank')


class Summarizer(ABC):
    _llm: TongyiLLM

    def __init__(self):
        self._llm = TongyiLLM()

    @retry(stop=stop_after_attempt(3), retry=retry_if_exception(should_retry))
    async def run(self, question: str, database_schema: str = "", filtered_tables: list = [], tool_list: list = []):
        filtered_tool_list = [tool for tool in tool_list if tool not in FILTERED_TOOL_SET]
        tools_desc = generate_tools_desc(filtered_tool_list)

        prompt = SUMMARIZE_PROMPT_TEMPLATE.format(
            database_schema=database_schema,
            filtered_fields=format_filtered_tables(filtered_tables),
            rule=RULE_PROMPT,
            tools_desc=tools_desc,
            question=question
        )
        messages = [
            Message(role='user', content=prompt)
        ]
        message = await self._llm.acomplete(messages)

        text = message.content
        summary = parse_json(text)

        # 以下会报 KeyError，所以放在这里做重试。
        grouped_summary = group_api_calls2(summary)
        api_summary = {
            'API（接口）串行调用次数': f"{count_serial_api_calls(grouped_summary)}次",
            'API（接口）串行调用个数': f"{count_unique_serial_api_calls(grouped_summary)}个",
            'API（接口）总共调用类数': f"{count_unique_api_tools(grouped_summary)}类",
            'API（接口）总共调用次数': f"{count_api_calls(summary)}次"
        }
        
        return api_summary
