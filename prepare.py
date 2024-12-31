import sys
import json


if __name__ == '__main__':
    if len(sys.argv) != 3:
        print("Usage: python3 prepare.py <input_file> <output_file>")
        sys.exit(1)

    input_file = sys.argv[1]
    output_file = sys.argv[2]

    # 处理每一行并写入新文件
    with open(input_file, 'r', encoding='utf-8') as infile, open(output_file, 'w', encoding='utf-8') as outfile:
        for line in infile:
            data = json.loads(line.strip())
            data['answer'] = ""
            
            json.dump(data, outfile, ensure_ascii=False)
            outfile.write('\n')
