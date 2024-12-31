# -*- coding: utf-8 -*-
import os
from dotenv import load_dotenv

env_path = os.path.join(os.path.dirname(__file__), '.env')
load_dotenv(env_path)

import sys
import time
import json
import asyncio
import traceback
from asyncio import Semaphore
from asyncio import TimeoutError

from tenacity import RetryError

from qwergpt.schema import Question
from qwergpt.solution_space import SolutionSpace
from qwergpt.llms.errors import LLMBalanceDepletionError
from qwergpt.logs import logger

logger.remove()
logger.add(sys.stdout, level="INFO")
logger.add("app.log", level="DEBUG")

from app.config import (
    BALANCE_DEPLETION_EXIT_CODE,
    TASK_MAX_TIME_LIMIT
)
from app.coder import Coder
from app.combiner import Combiner
from app.postprocessor import Postprocessor
from app.pipeline.qa import QAPipeline
from app.pipeline.sue import SuePipeline


async def pipeline_qa(question_id: int, question: str, coder: Coder, solution_space: SolutionSpace) -> str:
    qa_pipeline = QAPipeline(question_id, question, coder, solution_space)
    return await qa_pipeline.run()


async def pipeline_sue(question: str) -> str:
    sue_pipeline = SuePipeline()
    return await sue_pipeline.run(question)


async def pipeline(question_id: int, question: str, coder: Coder, solution_space: SolutionSpace) -> str:
    # TODO 意图识别
    logger.info(f'{question_id}: {question}')

    if '民事起诉状' in question:
        return await pipeline_sue(question)

    return await pipeline_qa(question_id, question, coder, solution_space)


async def pipeline_timeout(question_id: int, question: str, coder: Coder, solution_space: SolutionSpace) -> str:
    answer = solution_space.get_result()
    sub_question_result_list = [Question(question=question, answer=answer)]
    executed_code = solution_space.get_executed_code()

    combiner = Combiner()
    question_result = await combiner.run(
        question=question,
        sub_questions_result=sub_question_result_list,
        executed_code=executed_code,
    )

    postprocessor = Postprocessor()
    return await postprocessor.run(question, question_result.answer)


async def handle_question(question_id: str, question: str, semaphore: Semaphore, output_file: str):
    async with semaphore:
        coder = Coder(question_id)
        solution_space = SolutionSpace(question_id)
        try:
            answer = await asyncio.wait_for(
                pipeline(question_id, question, coder, solution_space), 
                timeout=TASK_MAX_TIME_LIMIT
            )
            await update_result_in_file(question_id, question, answer, output_file)
            return question_id, question, answer
        except TimeoutError as e:
            try:
                # 超时拿步骤分
                answer = await asyncio.wait_for(
                    pipeline_timeout(question_id, question, coder, solution_space), 
                    timeout=TASK_MAX_TIME_LIMIT
                )
                logger.error(f"问题 {question_id} {question} 处理出错: 超时 {str(e)}")
                await update_result_in_file(question_id, question, f"处理出错: 超时 {answer}", output_file)
                return question_id, question, "处理出错: 超时"
            except:
                logger.error(f"问题 {question_id} {question} 处理出错: 超时 {str(e)}")
                await update_result_in_file(question_id, question, f"处理出错: 超时", output_file)
                return question_id, question, "处理出错: 超时"
        except LLMBalanceDepletionError:
            logger.error(f"账户已欠费，问题 {question_id} 处理失败")
            raise LLMBalanceDepletionError("账户已欠费，退出运行")
        except RetryError as e:
            original_exception = e.last_attempt.exception()
            traceback.print_exception(type(original_exception), original_exception, original_exception.__traceback__)
            logger.error(f"处理问题 {question_id} 时发生错误: RetryError {str(original_exception)}")
            await update_result_in_file(question_id, question, f"处理出错: RetryError", output_file)
            return question_id, question, f"处理出错: {str(e)}"
        except Exception as e:
            traceback.print_exception(type(e), e, e.__traceback__)
            logger.error(f"处理问题 {question_id} 时发生错误: {type(e)}")
            await update_result_in_file(question_id, question, f"处理出错: {str(e)}", output_file)
            return question_id, question, f"处理出错: {str(e)}"
        finally:
            # 确保关闭 Coder 实例
            coder.shutdown()


async def update_result_in_file(question_id: str, question: str, answer: str, filename: str):
    async with asyncio.Lock():
        with open(filename, 'r+', encoding='utf-8') as file:
            lines = file.readlines()
            file.seek(0)
            for line in lines:
                data = json.loads(line)
                if data['id'] == question_id:
                    data['answer'] = answer
                json.dump(data, file, ensure_ascii=False)
                file.write('\n')
            file.truncate()


async def process_questions(output_file: str, semaphore: Semaphore):
    tasks = []
    with open(output_file, 'r') as file:
        for line in file:
            data = json.loads(line)
            if data['answer'] == "" \
                or (data['answer'] and data['answer'].startswith("处理出错")):
                task = asyncio.create_task(handle_question(data['id'], data['question'], semaphore, output_file))
                tasks.append(task)
    
    results = await asyncio.gather(*tasks, return_exceptions=True)

    if any(isinstance(result, LLMBalanceDepletionError) for result in results):
        raise LLMBalanceDepletionError("账户已欠费，退出运行")


async def main(max_concurrency: int, output_file: str):
    semaphore = Semaphore(max_concurrency)
    await process_questions(output_file, semaphore)


if __name__ == '__main__':
    if not os.path.exists('notebooks'):
        os.makedirs('notebooks')

    if len(sys.argv) != 3:
        print("Usage: python3 run.py <max_concurrency> <output_file>")
        sys.exit(1)
    
    max_concurrency = int(sys.argv[1])
    output_file = sys.argv[2]

    start_time = time.time()

    try:
        asyncio.run(main(max_concurrency, output_file))
    except LLMBalanceDepletionError:
        sys.exit(BALANCE_DEPLETION_EXIT_CODE)

    end_time = time.time()

    run_time = end_time - start_time
    logger.info(f"总运行时间: {run_time:.6f} 秒")
