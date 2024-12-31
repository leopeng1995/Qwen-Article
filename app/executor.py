from abc import ABC

from tenacity import (
    retry, 
    stop_after_attempt, 
    retry_if_exception
)

from app.planner import Plan
from app.coder import Coder
from qwergpt.schema import Task, Message, Question
from qwergpt.llms import (
    TongyiLLM,
)
from qwergpt.solution_space import SolutionSpace
from qwergpt.utils import (
    should_retry,
    parse_python,
    format_filtered_tables
)
from qwergpt.logs import logger
from qwergpt.pipelines import PipelineData, PipelineComponent

from app.rule import RULE_PROMPT


TASK_PROMPT_TEMPLATE: str = """
[数据表定义]
{database_schema}

[工具列表]
{tools_desc}

[参考代码]
```python
from app.law.tools import *

# 查询: **示例公司名称** 作为被告的案件有哪些？
company_name = "示例公司名称"
# 1. 查询该公司所有的案件
legal_doc_list = get_legal_document_list(company_name)
for legal_doc in legal_doc_list:
    # 2. 判断案件的被告包含该公司名称
    defendant = legal_doc.get("被告", "")
    if company_name in defendant:
        print(legal_doc.get("案号"))
```

```python
from app.law.tools import *

# 查询: **示例统一社会信用代码** 在 yyyy 年作为被告的次数和总金额？
company_info = get_company_register_name("示例统一社会信用代码")
company_name = company_info.get("公司名称")
legal_doc_list = get_legal_document_list(company_name)

# 筛选起诉日期在 yyyy 年被起诉的案件，并记录案号、涉案金额
cases_yyyy = []
for legal_doc in legal_doc_list:
    case_number = legal_doc.get("案号", "")
    defendant = legal_doc.get("被告", "")
    if "yyyy" in case_number and company_name in defendant:
        amount_involved = legal_doc.get("涉案金额", "")
        cases_yyyy.append((case_number, amount_involved))
print(cases_yyyy)
 
# 对筛选出的案件进行汇总，统计被起诉次数及总金额
number_of_cases_yyyy = len(cases_yyyy)
total_amount_involved_yyyy = sum([convert_to_float(amount) for _, amount in cases_yyyy])
```

```python
# 查询: **示例公司名称** 投资金额最大的子公司是哪一家？投资金额是多少？ 
# 使用 get_sub_company_info_list 工具获取 **示例公司名称** 旗下的子公司列表
sub_company_info_list = get_sub_company_info_list("示例公司名称")
sub_company_info_investment = [convert_to_float(sub_company['上市公司投资金额']) for sub_company in sub_company_info_list]

# 使用 rank 工具子公司列表按照 上市公司投资金额 从大到小排序
sorted_sub_company_info_list = rank(keys=sub_company_info_list, values=sub_company_info_investment, is_desc=True)

# 排序后的子公司列表第一个就是 **示例公司名称** 投资金额最大的子公司
max_investment_sub_company_info = sorted_sub_company_info_list[0]
max_investment_amount = max(sub_company_info_investment)
```

[字段筛选]
{filtered_fields}

{rule}

[问题]
{question}

[计划]
{instruction}
    
[任务]
根据 **计划**，写出 Python 代码，以实现目标。
工具已经定义好，第一步引入全部工具:

```python
from app.law.tools import *

# 写出你的代码
```

工具的使用方式参考 **工具列表** 部分内容。
严格按照 **计划** 中的步骤进行编码。
使用 **问题** 的参数值。
完成每一个步骤，立即使用 print 函数输出该步骤的 output 变量值。格式如下：
print(f"Step {{步骤编号}} output - {{output变量名}}:", output变量值)
确保每个步骤的结果都被打印出来，以便跟踪代码执行过程。
"""

DEBUG_REFLECTION_SYSTEM_PROMPT = """
你是一名精通 Python 的软件工程师。请你根据之前任务的代码、运行错误结果修改代码。
"""

DEBUG_REFLECTION_EXAMPLE = '''
code:
```python
company_register_name = get_company_register_name("示例统一社会信用代码")
company_register = get_company_register(company_register_name)
legal_representative = company_register.get('法定代表人')
```

error:
AttributeError: 'str' object has no attribute 'get'

reflection:
get_company_register_name 工具返回类型是 dict，需要获取 **公司名称** 字段值，作为 get_company_register 工具的参数。

revised:
```python
company_register_name = get_company_register_name("示例统一社会信用代码")
company_name = company_register_name.get("公司名称") 
company_register = get_company_register(company_name)
legal_representative = company_register.get('法定代表人')
```
'''

# 代码反思，修复代码异常
DEBUG_REFLECTION_PROMPT_TEMPLATE = """
[数据表定义]
{database_schema}

[工具列表]
{tools_desc}

[字段筛选]
{filtered_fields}

[参考调试]
{debug_example}

{rule}

[问题]    
{question}

[当前任务指令]
{instruction}

[原先实现]:
{previous_impl}

[运行报错]
{error_desc}

[指令]
**问题** 描述了需要编写代码解决的问题。
**当前任务指令** 描述了解决问题的步骤。
**字段映射** 描述了查询字段对应数据表。
**工具列表** 描述了如何使用相关的工具。
**常见错误** 描述了常见的运行报错原因。
根据 **运行报错**，修改 **原先实现** 中的代码，
使用 **问题** 的参数，遵守 **答题思路** 。
完成每一个步骤，立即使用 print 函数输出该步骤的 output 变量值。格式如下：
print(f"Step {{步骤编号}} output - {{output变量名}}:", output变量值)
确保每个步骤的结果都被打印出来，以便跟踪代码执行过程。

输出格式如下:
```python
# 你修改后的 Python 代码
```
"""

ERROR_DESC_TEMPLATE: str = """
Error Name: {ename}
Error Value: {evalue}
Traceback:
{traceback}
"""

EXECUTOR_SYSTEM_PROMPT: str = """你是一个精通 Python 的软件工程师，你擅长根据计划和任务指令编写 Python 代码。"""


class IndentationError(Exception):
    pass


class Executor(PipelineComponent):

    _llm: TongyiLLM
    _plan: Plan
    _coder: Coder
    _question_id: int
    _latest_output: str
    _solution_space: SolutionSpace

    def __init__(self, question_id: int, coder: Coder, solution_space: SolutionSpace):
        self._llm = TongyiLLM()
        self._question_id = question_id
        self._coder = coder
        self._solution_space = solution_space

        self._latest_output = ''

    @retry(stop=stop_after_attempt(3), retry=retry_if_exception(should_retry))
    async def exec_task(self, question: str, task: Task, database_schema: str, tools_desc: str, filtered_tables: list):
        # 计划
        plan_desc = ''
        for t in self._plan.tasks:
            data = t.model_dump()
            task_desc = f"task_id: {data['task_id']}, instruction: {data['instruction']}, dependent_task_ids: {data['dependent_task_ids']}"
            plan_desc += task_desc + '\n\n'

        task_prompt = TASK_PROMPT_TEMPLATE.format(
            database_schema=database_schema,
            tools_desc=tools_desc,
            filtered_fields=format_filtered_tables(filtered_tables),
            question=question,
            rule=RULE_PROMPT,
            instruction=self._plan.current_task.instruction,
        )
        logger.debug(f"Task Prompt: {task_prompt}")
        messages = [
            Message(role='system', content=EXECUTOR_SYSTEM_PROMPT),
            Message(role='user', content=task_prompt),
        ]
        message = await self._llm.acomplete(messages, max_tokens=3072)

        for _ in range(4):
            code = parse_python(text=message.content, lang='python')
            run_result = await self._coder.run_code(code, preserve_context=False)

            if run_result['ename'] == 'RunCodeException' and 'IndentationError' in run_result['evalue']:
                raise IndentationError('缩进异常，重新生成代码')

            # 为了保证步骤分
            if len(run_result['result']) > len(self._latest_output):
                self._latest_output = run_result['result']
                self._solution_space.set_result(self._latest_output)
                self._solution_space.set_executed_code(code)

            if run_result['success']:
                task.result = run_result['result']
                task.code = code
                # 执行成功则跳出循环
                break
            else:
                error_desc = ERROR_DESC_TEMPLATE.format(
                    ename=run_result['ename'],
                    evalue=run_result['evalue'],
                    traceback=run_result['traceback'],
                )
                debug_prompt = DEBUG_REFLECTION_PROMPT_TEMPLATE.format(           
                    database_schema=database_schema,
                    tools_desc=tools_desc,
                    filtered_fields=format_filtered_tables(filtered_tables),
                    rule=RULE_PROMPT,
                    debug_example=DEBUG_REFLECTION_EXAMPLE,
                    question=question,
                    instruction=self._plan.current_task.instruction,
                    previous_impl=code,
                    error_desc=error_desc
                )
                logger.debug(f"Debug Prompt: {debug_prompt}")
                messages = [
                    Message(role='system', content=DEBUG_REFLECTION_SYSTEM_PROMPT),
                    Message(role='user', content=debug_prompt),
                ]
                message = await self._llm.acomplete(messages, max_tokens=3072)

        self._plan.finish_task(task)
    
    async def run(self, pipeline_data: PipelineData) -> PipelineData:
        question = pipeline_data.get('preprocessor.question')
        plan = pipeline_data.get('plan')
        database_schema = pipeline_data.get('database_schema')
        tools_desc = pipeline_data.get('tools_desc')
        filtered_tables = pipeline_data.get('filtered_tables')

        self._plan = plan
        tasks = self._plan.tasks

        for task in tasks:
            await self.exec_task(question, task, database_schema, tools_desc, filtered_tables)

        answer = self._latest_output
        sub_question = Question(
            question=plan.question,
            answer=answer,
        )
        code = self._coder.get_executed_code()
        pipeline_data.set('sub_question', sub_question)
        pipeline_data.set('code', code)
        return pipeline_data

    def shutdown(self):
        self._coder.shutdown()
