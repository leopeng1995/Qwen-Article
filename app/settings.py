import os
from dotenv import load_dotenv

# 加载环境变量
env_path = os.path.join(os.path.dirname(__file__), '../../.env')
load_dotenv(env_path)

# 退出代码
BALANCE_DEPLETION_EXIT_CODE = 2
TIME_LIMIT_EXIT_CODE = 3

# 时间限制
TIME_LIMIT_SECONDS = 55 * 60  # 55分钟
TASK_MAX_TIME_LIMIT = 280
WORKFLOW_PER_REST_TIME = 3
