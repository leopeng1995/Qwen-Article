from typing import Dict, List, Any

from tenacity import (
    retry, 
    stop_after_attempt, 
    retry_if_exception
)

from qwergpt.llms import TongyiLLM
from qwergpt.schema import Message
from qwergpt.logs import logger
from qwergpt.utils import (
    should_retry,
    format_filtered_tables
)
from qwergpt.roles.planner import (
    Plan,
    BasePlanner,
)
from qwergpt.pipelines import PipelineData

from app.rule import RULE_PROMPT


PLANNING_SYSTEM_PROMPT: str = """你是一个精通任务规划的专家。"""

PLANNING_PROMPT_TEMPLATE: str = """
[数据表定义]
{database_schema}

[字段筛选]
{filtered_fields}

[工具列表]
{tools_desc}

[参考示例]
查询: **示例公司名称** 注册地址的城市区划代码是多少
<BOS>
步骤1:
使用 get_company_info 工具获取 **注册地址**，判断结果是否为空列表，不是上市公司则使用 get_company_register 工具获取 **企业地址**
输出公司名称、注册地址（上市公司）或企业地址（非上市公司）

步骤2:
使用 get_address_info 工具查询 __步骤1结果__ 的省份、城市、区县
输出省份、城市或区县

步骤3:
使用 get_address_code 工具查询 **城市区划代码**
输出城市区划代码
<EOS>

查询: **示例律师事务所名称** 分布在哪个城市
<BOS>
步骤1:
使用 get_lawfirm_info 工具获取 **律师事务所地址**
输出律师事务所名称、律师事务所地址

步骤2:
使用 get_address_info 工具查询 **律师事务所地址** 所在的 **城市**
输出省份、城市、区县
<EOS>

查询: **示例统一社会信用代码** 的控股公司的子公司有哪些？
<BOS>
步骤1:
使用 get_company_register_name 工具获取 **示例统一社会信用代码** 对应的公司名称

步骤2:
使用 get_parent_company_info 工具查询 __步骤1结果__ 获取该公司的控股公司名称

步骤3:
使用 get_sub_company_info_list 查询 __步骤2结果__ 获取控股公司的子公司列表
<EOS>

{rule}

[问题]
{question}

[任务]
**数据表定义** 描述了数据表的字段信息。
**参考示例** 描述了相对复杂的计划步骤。
**工具列表** 描述了如何使用相关的工具。
**答题思路** 描述了常用的答题思路。
根据 **字段映射**，和 **字段筛选**，确定需要查询的数据表和字段名。
在使用工具之前，仔细检查需要查询的字段属于哪个数据表，确保使用正确的工具查询正确的表。
仔细阅读 **工具列表** 的工具描述，针对 **问题** 编写一个计划，以解决问题。
按照以下格式输出:
```json
{{
    "plan": str = "计划的总体描述，包括主要步骤和最终目标",
    "steps": [
        {{
            "id": int = "步骤序号",
            "description": str = "详细描述该步骤的操作，包括使用的工具名称和目的",
            "tool": str = "使用的工具名称，只能使用 **工具列表** 的工具",
            "params": dict = "工具所需的参数",
            "output": str = "描述该步骤的输出结果和变量名"
        }},
        ...
    ]
}}
```
"""

REPLANNING_SYSTEM_PROMPT: str = """你是一个精通任务规划的专家。"""

REPLANNING_PROMPT_TEMPLATE: str = """
[数据表定义]
{database_schema}

[字段筛选]
{filtered_fields}

[工具列表]
{tools_desc}

{rule}

[问题]
{question}

[原先计划]
{plan_desc}

[任务]
**数据表定义** 描述了数据表的字段信息。
**字段映射** 描述了问题的字段对应关系。
**工具列表** 描述了如何使用相关的工具。
**答题思路** 描述了常用的答题思路。
**原先计划** 描述了上一轮为了回答问题制定的计划。

修改 **原先计划**，以解决 **问题**。
按照以下格式输出:
```json
{{
    "plan": str = "修改后计划的总体描述，包括主要步骤和最终目标",
    "steps": [
        {{
            "id": int = "步骤序号",
            "description": str = "详细描述该步骤的操作，包括使用的工具名称和目的",
            "tool": str = "使用的工具名称，只能使用 **工具列表** 的工具",
            "params": dict = "工具所需的参数",
            "output": str = "描述该步骤的输出结果和变量名"
        }},
        ...
    ]
}}
```
"""


class Planner(BasePlanner):

    def __init__(self, model: str):
        self._llm = TongyiLLM()

    @retry(stop=stop_after_attempt(3), retry=retry_if_exception(should_retry))
    async def run(self, pipeline_data: PipelineData) -> PipelineData:
        question = pipeline_data.get('preprocessor.question')
        database_schema = pipeline_data.get('database_schema')
        filtered_tables = pipeline_data.get('filtered_tables')
        tools_desc = pipeline_data.get('tools_desc')

        plan = await self._execute_plan(question, database_schema, filtered_tables, tools_desc, PLANNING_PROMPT_TEMPLATE)
        pipeline_data.set('plan', plan)
        return pipeline_data

    async def _execute_plan(self, question: str, database_schema: str, filtered_tables: List[Dict[str, Any]], tools_desc: str, prompt_template: str, plan_desc: str = "") -> Plan:
        prompt = prompt_template.format(
            database_schema=database_schema,
            filtered_fields=format_filtered_tables(filtered_tables),
            tools_desc=tools_desc,
            rule=RULE_PROMPT,
            question=question,
            plan_desc=plan_desc
        )
        messages = [
            Message(role='system', content=PLANNING_SYSTEM_PROMPT),
            Message(role='user', content=prompt),
        ]
        instruction = await self._get_instruction(messages)
        return Plan(question=question, tasks=[{'task_id': '1', 'instruction': instruction, 'dependent_task_ids': []}])
