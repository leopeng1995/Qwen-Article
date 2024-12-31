#!/bin/bash

set -e  # 遇到错误立即退出

export PYTHONPATH=$PYTHONPATH:$PWD

# 移除日志文件（如果存在）
rm -f app.log

# 读取配置文件
source config.sh

# 根据 mode 设置环境变量
case $mode in
    development)
        INPUT_FILE="question_c_1.json"
        OUTPUT_FILE="result_1.json"
        ;;
    staging)
        INPUT_FILE="question_c.json"
        OUTPUT_FILE="result.json"
        ;;
    production)
        INPUT_FILE="/tcdata/question_d.json"
        OUTPUT_FILE="/app/result.json"
        ;;
    *)
        echo "无效的模式. 请使用 development, staging, 或 production" >> app.log
        exit 1
        ;;
esac

# 准备结果文件
if ! python3 prepare.py "$INPUT_FILE" "$OUTPUT_FILE"; then
    echo "prepare.py 执行失败" >> app.log
    exit 1
fi

# 避免异常退出，反复运行
retry_count=0
while [ $retry_count -lt $MAX_RETRIES ]; do
    if python3 run.py "$MAX_CONCURRENCY" "$OUTPUT_FILE"; then
        exit 0
    fi
    
    exit_code=$?
    case $exit_code in
        2)
            echo "账户已欠费. Exiting..." >> app.log
            exit 1
            ;;
        3)
            echo "程序运行超时. Exiting..." >> app.log
            exit 1
            ;;
        *)
            echo "run.py 以代码 $exit_code 退出. 重试中..." >> app.log
            ((retry_count++))
            sleep 1
            ;;
    esac
done

echo "达到最大重试次数. Exiting..." >> app.log
exit 1
