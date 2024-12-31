import time
import asyncio
from typing import List

from qwergpt.pipelines import (
    Pipeline, 
    PipelineData,
    PipelineStatus
)
from qwergpt.schema import Question

from app.settings import WORKFLOW_PER_REST_TIME
from app.rewriter import Rewriter
from app.preprocessor import Preprocessor
from app.filter import Filter
from app.planner import Planner
from app.executor import Executor
from app.combiner import Combiner
from app.postprocessor import Postprocessor
from app.law.tools import generate_tools_desc
from app.law.schema import generate_database_schema


class QAPipeline(Pipeline):
    def __init__(self, question_id: int, question: str, coder, solution_space):
        super().__init__(pipeline_id=str(question_id))
        self.question_id = question_id
        self.question = question
        self.coder = coder
        self.solution_space = solution_space

    async def _time_execution(self, func, component_name: str, *args, **kwargs):
        if self.status == PipelineStatus.PAUSED:
            while self.status == PipelineStatus.PAUSED:
                await asyncio.sleep(1)

        start_time = time.time()
        result = await func(*args, **kwargs)
        elapsed_time = time.time() - start_time
        
        self.log_component_metrics(
            component_name=component_name,
            execution_time=elapsed_time
        )
        self.notify_observers()
        return result

    async def run(self) -> str:
        model = 'qwen-plus'
        rewriter = Rewriter(model=model)
        preprocessor = Preprocessor(model=model)
        filter = Filter(model=model)
        planner = Planner(model=model)
        executor = Executor(question_id=self.question_id, coder=self.coder, solution_space=self.solution_space)
        combiner = Combiner(model=model)
        postprocessor = Postprocessor()

        pipeline_data: PipelineData = PipelineData(data={})
        pipeline_data.set('question', self.question)

        pipeline_data = await self._time_execution(rewriter.run, 
            component_name='rewriter', 
            pipeline_data=pipeline_data
        )
        await asyncio.sleep(WORKFLOW_PER_REST_TIME)
        # pipeline_data.set('rewritten_question', '公司全称是什么，对于91310000677833266F？该公司在2020年的涉案次数为多少？作为被起诉人的次数及总金额分别是多少？')

        pipeline_data = await self._time_execution(preprocessor.run, 
            component_name='preprocessor', 
            pipeline_data=pipeline_data
        )
        await asyncio.sleep(WORKFLOW_PER_REST_TIME)
        # pipeline_data.set('preprocessed_question', "QUERY: 公司全称是什么，对于91310000677833266F？该公司在2020年的涉案次数为多少？作为被起诉人的次数及总金额分别是多少？\nNER: {'统一社会信用代码': '91310000677833266F'}")

        pipeline_data = await self._time_execution(filter.run, 
            component_name='filter', 
            pipeline_data=pipeline_data
        )
        await asyncio.sleep(WORKFLOW_PER_REST_TIME)
        # pipeline_data.set('filtered_tables', [{'table_name': 'CompanyRegister', 'fields': '公司名称,统一社会信用代码'}, {'table_name': 'LegalDoc', 'fields': '关联公司,原告,日期,案号,涉案金额'}])
        # pipeline_data.set('filtered_tool_list', ['get_legal_abstract', 'get_legal_document_list', 'get_company_register_name', 'extract_code_from_case_num', 'get_legal_document', 'extract_year_from_case_num', 'get_company_register', 'convert_amount_unit', 'convert_to_float', 'rank'])

        question = pipeline_data.get('preprocessor.question')
        filtered_tables = pipeline_data.get('filtered_tables')
        filtered_tool_list = pipeline_data.get('filtered_tool_list')

        filtered_database_schema = generate_database_schema([t['table_name'] for t in filtered_tables])
        filtered_tools_desc = generate_tools_desc(filtered_tool_list)

        pipeline_data.set('database_schema', filtered_database_schema)
        pipeline_data.set('tools_desc', filtered_tools_desc)

        sub_questions = [{'question_id': '1', 'question': question}]
        sub_question_result_list: List[Question] = []
        executed_code = ''

        for sub_question in sub_questions:
            pipeline_data = await self._time_execution(planner.run, 
                component_name='planner',
                pipeline_data=pipeline_data
            )
            await asyncio.sleep(WORKFLOW_PER_REST_TIME)

            pipeline_data = await self._time_execution(executor.run,
                component_name='executor',
                pipeline_data=pipeline_data
            )
            await asyncio.sleep(WORKFLOW_PER_REST_TIME)

            print(pipeline_data.get('sub_question'))

            sub_question_result = pipeline_data.get('sub_question')
            executed_code = pipeline_data.get('code')
            sub_question_result_list.append(sub_question_result)
        
        pipeline_data.set('sub_question_result', sub_question_result_list)

        print(pipeline_data)

        pipeline_data = await self._time_execution(combiner.run,
            component_name='combiner',
            pipeline_data=pipeline_data
        )
        await asyncio.sleep(WORKFLOW_PER_REST_TIME)

        pipeline_data = await self._time_execution(postprocessor.run, 
            component_name='postprocessor',
            pipeline_data=pipeline_data
        )

        answer = pipeline_data.get('answer')
        return answer
