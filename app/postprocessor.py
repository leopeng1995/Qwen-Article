import re
import asyncio
from abc import ABC

from qwergpt.pipelines import (
    PipelineData,
    PipelineComponent
)

from app.law.tools import (
    get_legal_document,
    get_legal_abstract
)


def format_date(text):
    def add_zero(match: re.Match):
        year, month, day = match.groups()

        old = f"{year}年{month}月{day}日"

        if len(month) == 1:
            month = '0' + month
        if len(day) == 1:
            day = '0' + day

        new = f"{year}年{month}月{day}日"
        return new

    pattern = r'(\d{4})年(\d{1,2})月(\d{1,2})日'
    return re.sub(pattern, add_zero, text)


def format_date_abstract(text):
    def add_zero(match: re.Match):
        year, month, day = match.groups()

        old = f"{year}年{month}月{day}日"

        if len(month) == 1:
            month = '0' + month
        if len(day) == 1:
            day = '0' + day

        new = f"{year}年{month}月{day}日"
        return new

    pattern = r'(\d{4})年(\d{1,2})月(\d{1,2})日'
    return re.sub(pattern, add_zero, text)


def replace_amount(match):
    amount = match.group(1)
    unit = match.group(2)
    return amount + unit


def replace_date_format(match):
    year, month, day = match.groups()
    return f"{year}年{month}月{day}日"


class Postprocessor(PipelineComponent):

    async def run(self, pipeline_data: PipelineData) -> PipelineData:
        question = pipeline_data.get('question')
        answer = pipeline_data.get('answer')

        # 答案全部把全角括号替换成半角
        answer = answer.replace('（', '(')
        answer = answer.replace('）', ')')

        answer = answer.replace('【', '(')
        answer = answer.replace('】', ')')

        if '金额' in question or '元' in answer:
            # 把数字中的半角逗号去掉
            # TODO 应该用正则的，先用最简单的替换方法
            answer = answer.replace(',', '')

        answer = answer.replace('℃', '度')
        if '摄氏度' in answer:
            answer = answer.replace('摄氏度', '度')
        
        # 1.1 元 => 1.1元
        pattern = r'(\d+(?:\.\d+)?)\s*(元|万元?|亿元?)'
        answer = re.sub(pattern, replace_amount, answer)

        # (0.500)亿元 => 0.500亿元
        pattern = r'\((\d+(?:\.\d+)?)\)(元|万元?|亿元?)'
        answer = re.sub(pattern, r'\1\2', answer)

        # 2003年5月15日 => 2003年05月15日
        answer = format_date(answer)

        # yyyy-MM-DD => yyyy年MM月DD日
        date_pattern = r'(\d{4})-(\d{2})-(\d{2})'
        answer = re.sub(date_pattern, replace_date_format, answer)

        # 把问题中的统一社会信用代码补充到答案
        pattern = r'[0-9A-HJ-NPQRTUWXY]{2}\d{6}[0-9A-HJ-NPQRTUWXY]{10}'
        matches = re.findall(pattern, question)
        if matches:
            unified_social_credit_code = matches[0]
            if unified_social_credit_code not in answer:
                answer = f"{unified_social_credit_code}，{answer}"
        
        if '判决结果' in question:
            pattern = r'\((\d+)\)([\u4e00-\u9fa5\d]+?)([\u4e00-\u9fa5]{1,4})(\d+)号'
            match = re.search(pattern, answer)
            if match:
                case_num = '({}){}{}{}号'.format(*match.groups())
                legal_doc = get_legal_document(case_num)
                if legal_doc:
                    answer = f"{answer}\n{legal_doc.get('判决结果')}"
        
        if '摘要' in question:
            pattern = r'\((\d+)\)([\u4e00-\u9fa5\d]+?)([\u4e00-\u9fa5]{1,4})(\d+)号'
            match = re.search(pattern, answer)
            if match:
                case_num = '（{}）{}{}{}号'.format(*match.groups())
                legal_abstract = get_legal_abstract(case_num)
                if legal_abstract:
                    lines = answer.split('\n')
                    lines = [line for line in lines if '摘要' not in line]
                    answer = '\n'.join(lines)

                    answer = f"{answer}\n摘要: {legal_abstract.get('文本摘要')}"

        if '整合报告' in question:
            pattern = r'Word_[^\n]+'
            match = re.search(pattern, answer)
            if match:
                answer = match.group()

        pipeline_data.set('answer', answer)
        return pipeline_data


async def main():
    # 创建Postprocessor实例
    postprocessor = Postprocessor()

    question = '利亚德光电股份有限公司关于工商信息及投资金额过亿的全资子公司，所有公司的立案时间在19年涉案金额不为0的裁判文书（不需要判决结果）整合报告。'
    answer = '2019年涉案金额不为0的裁判文书信息如下(仅提供案号和涉案公司名称)：\n- 案号：未提供具体案号信息\n- 涉案公司名称：利亚德光电股份有限公司\n\n整合报告名称：Word_利亚德光电股份有限公司_companyregister1_28_subcompanyinfo8_5_legallist12_13_xzgxflist0_0\n\n请注意，由于运行结果中未提供具体的裁判文书案号，故无法提供详细的案号信息。'

    answer = await postprocessor.run(question, answer)
    print(answer)


if __name__ == '__main__':
    asyncio.run(main())
