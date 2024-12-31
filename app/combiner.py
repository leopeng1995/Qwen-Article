from abc import ABC

from tenacity import (
    retry, 
    stop_after_attempt, 
    retry_if_exception
)

from qwergpt.llms import TongyiLLM
from qwergpt.schema import Message, Question
from qwergpt.utils import should_retry
from qwergpt.pipelines import PipelineComponent, PipelineData
from qwergpt.logs import logger


COMBINE_ANSWER_PROMPT_TEMPLATE: str = """
[问题]
{question}

[运行代码]
```python
{executed_code}
```

[运行结果]
{sub_questions_result_desc}

[注意事项]
* **问题** 可能使用了错误的名称，请以 **运行结果** 为准。
* 日期输出格式: yyyy年MM月dd日
* 保留 **问题** 度量单位:
    1. 「多少家」，回答使用「XX家」
    2. 「多少次」，回答使用「XX次」
    3. 「多少起」，回答使用「XX起」
    4. 「第几名」，回答使用「第XX名」
* 严格按照问题的保留几位小数点回答
* 使用 **运行结果** 原文回答:
    a. 使用阿拉伯数字，数字不要加逗号
    b. 如果字段值是短横线-，回答输出短横线-
    c. 如果金额没有单位，请加上 **元** 作为单位
    d. 温度需要输出单位，「度」，数值使用整数
    e. 案件信息:
        1. 如果 **问题** 没有说明，只需要输出案号、原告、被告
        2. 如果 **问题** 有说明，输出补充提问要求字段
* 对于地址所在地区、位于什么地方、分布哪个城市这类问题，回答中应包含相应的地址
* 除了直接回答问题外，还应提供与问题相关的重要信息，特别是运行结果中的关键数据（如法院名称、案号、涉案金额、注册地址等）。

[提取规则]
* 案件（限高、限制高消费XzgxfInfo），提取案号
* 涉案金额，提取涉案金额
* 公司，提取公司名称
* 法院，提取法院名称
* 律师事务所，提取律师事务所名称
* 地址，提取相应的法院地址、律师事务所地址、公司地址（办公地址、注册地址或企业地址）
* 地区、地方，提取省份、城市、区县
* 申请人、被申请人，提取案件的原告、被告、申请人

[任务]
1. 按照 **运行代码** 的步骤，提取 **运行结果** 中所有有结果的步骤输出到答案。
2. 识别并提取与问题相关的关键信息，如案号、涉案金额、公司名称等。
3. 根据提取的信息，直接组织答案。
4. 遵守 **注意事项**。
5. 答案应完整重复 **问题** 中的关键信息（如公司名称、公司代码、案号等等），省略无关内容。
6. 只输出最终的答案，不要显示运行代码、提取过程或中间步骤。
"""


class Combiner(PipelineComponent):

    def __init__(self, model: str = 'glm-4-air'):
        self._llm = TongyiLLM(model=model)

    @retry(stop=stop_after_attempt(3), retry=retry_if_exception(should_retry))
    async def run(self, pipeline_data: PipelineData) -> PipelineData:
        question = pipeline_data.get('preprocessor.question')
        sub_questions_result = pipeline_data.get('sub_question_result')
        executed_code = pipeline_data.get('code')

        # TODO 需要 database_schema，因为如果信息来源于多表的时候，需要在这里处理。
        if len(sub_questions_result) == 1:
            sub_questions_result_desc = sub_questions_result[0].answer
        else:
            sub_questions_result_desc = '\n'.join([f"子问题: {q.question}\n子问题答案:\n{q.answer}\n" for q in sub_questions_result])

        prompt = COMBINE_ANSWER_PROMPT_TEMPLATE.format(
            question=question,
            executed_code=executed_code,
            sub_questions_result_desc=sub_questions_result_desc,
        )
        messages = [
            Message(role='user', content=prompt)
        ]
        message = await self._llm.acomplete(messages)
        answer = message.content

        # 减少多余的字数
        if answer.strip().startswith('根据运行结果，'):
            answer = answer[7:]
        elif answer.strip().startswith('根据运行结果'):
            answer = answer[6:]

        pipeline_data.set('answer', answer)
        return pipeline_data
