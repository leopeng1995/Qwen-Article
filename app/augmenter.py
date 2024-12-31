from abc import ABC

from qwergpt.schema import Message
from qwergpt.llms import TongyiLLM
from qwergpt.utils import parse_json
from qwergpt.logs import logger

from app.law.schema import ALL_DATABASE_SCHEMA


AUGMENT_PROMPT_TEMPLATE: str = """
请根据给定的 **问题** 和 **数据表定义** 进行数据增强。
生成多个相关但更加复杂和多样化的问题，满足以下要求:

1. 每个新问题应包含多个步骤的推理过程。
2. 涉及至少2个不同的数据表。
3. 公司名称、法院名称、律师事务所名称可以有轻微变化，如: 使用部分拼音或包含错别字。
4. 原问题中的数值范围可以变化。
5. 身份可以改变,如原问题中的被告可以改为原告,原告可以改为被告。
6. 涉案金额的计算方式可以变化,如总和、平均值、最大值、最小值等。
7. 可以引入跨表的复杂查询,如结合公司信息和法律文书。

每个新问题应该在原始问题的基础上大幅拓展或变化，以获取更全面和深入的信息。

[数据表定义]
{database_schema}

[问题]
{question}

[输出格式]
```json
[
    {{
        "question": "增强后的问题1",
    }},
    {{
        "question": "增强后的问题2",
    }},
    ...
]
```
"""


class Augmenter(ABC):

    def __init__(self):
        self._llm = TongyiLLM()

    async def run(self, question: str):
        prompt = AUGMENT_PROMPT_TEMPLATE.format(
            database_schema=ALL_DATABASE_SCHEMA,
            question=question,
        )
        logger.debug(f"Augment Prompt: {prompt}")
        messages = [
            Message(role='user', content=prompt),
        ]
        message = await self._llm.acomplete(messages)

        augmented_questions = parse_json(message.content)
        augmented_questions = [q['question'] for q in augmented_questions]
        return augmented_questions
