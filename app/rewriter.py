from qwergpt.roles.rewriter import BaseRewriter

from tenacity import (
    retry, 
    wait_fixed,
    stop_after_attempt, 
    retry_if_exception
)

from qwergpt.utils import should_retry
from qwergpt.schema import Message
from qwergpt.llms import TongyiLLM
from qwergpt.pipelines import PipelineData


SYSTEM_PROMPT: str = """
你是专业查询纠错系统，请严格按照给定规则纠正用户提供的查询，保持核心含义和关键信息不变，仅修正错误，并以指定格式输出结果。
"""

USER_PROMPT_TEMPLATE: str = """
作为一个专业的查询纠错系统，你的任务是纠正以下查询中的错误，以提高检索系统的准确性。请基于给定的数据表定义，遵循以下规则：

1. 保留原始查询的核心含义和意图。
2. 保持关键信息的原始格式完全不变，包括但不限于括号内的内容、数字、日期等。这些信息非常重要，不得以任何方式修改、省略或删除。
3. 纠正原始查询中的错别字、拼音错误、标点符号错误和语法错误。
4. 确保查询使用正确的术语和表达方式。
5. 不要添加、删除或重新组织查询的内容，除非是为了纠正明显的错误。
6. 在重写过程中，特别注意保留原始查询中的所有限定条件和时间范围。

原始查询: {question}

请使用以下固定格式提供纠正后的查询：

查询：[在此处提供重写后的查询，不需要解释]
"""


class Rewriter(BaseRewriter):

    def __init__(self, model: str):
        self._llm = TongyiLLM(model=model)

    def get_system_prompt(self) -> str:
        return SYSTEM_PROMPT

    def get_user_prompt_template(self) -> str:
        return USER_PROMPT_TEMPLATE

    @retry(
        stop=stop_after_attempt(3), 
        retry=retry_if_exception(should_retry),
        wait=wait_fixed(1)
    )
    async def run(self, pipeline_data: PipelineData) -> PipelineData:
        question = pipeline_data.get('question')

        replacements = {
            '母公司': '控股公司',
            '审理当天': '判决当天',
            '审理日期': '判决当天',
            '审理时间': '判决当天',
            '圈资公司': '全资子公司'
        }
        for pattern, replacement in replacements.items():
            question = question.replace(pattern, replacement)

        # Query Rewrite
        prompt = self.get_user_prompt_template().format(
            question=question,
        )
        messages = [
            Message(role='system', content=self.get_system_prompt()),
            Message(role='user', content=prompt)
        ]
        message = await self._llm.acomplete(messages)
        question = message.content

        if question.startswith('查询：') or question.startswith('查询:'):
            question = question[3:]
       
        pipeline_data.set('rewriter.question', question)
        return pipeline_data
