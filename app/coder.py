import re
import textwrap

from qwergpt.roles.coder import BaseCoder


CODE_TEMPLATE: str = """
from app.law.tools import *

{code}
"""

def replace_print_with_pass(text):
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'print(legal_doc_list)' in line:
            lines[i] = line.replace('print(legal_doc_list)', 'pass')
        if 'print' in line and 'legal_doc_list' in line:
            pattern = r'print\(.*legal_doc_list.*\)'
            lines[i] = re.sub(pattern, 'pass', line)
        if 'print' in line and '案件列表' in line:
            pattern = r'print\(.*案件列表.*\)'
            lines[i] = re.sub(pattern, 'pass', line)
        if 'print' in line and 'legal_docs' in line:
            pattern = r'print\(.*legal_docs.*\)'
            lines[i] = re.sub(pattern, 'pass', line)
        if 'print' in line and '列表' in line:
            if '公司' in line:
                continue

            pattern = r'print\(.*列表.*\)'
            lines[i] = re.sub(pattern, 'pass', line)

    return '\n'.join(lines)


class Coder(BaseCoder):

    async def run_code(self, code: str, preserve_context=True):
        if not code.strip().startswith('from app.law.tools import *'):
            code = CODE_TEMPLATE.format(code=code)
        
        # 避免打印裁判文书列表，导致答案太长
        code = replace_print_with_pass(code)
        code = textwrap.dedent(code)
        self.executed_code[:1] = [code]

        async with self.lock:
            run_result = await self._execute_code(code, preserve_context)

        self.latest_output = run_result['result']
        return run_result
