import json


def read_input_file(file_path: str, last_position: int = 0):
    with open(file_path, 'r', encoding='utf-8') as f:
        return f.readlines()[last_position:]


def print_data(data, is_answer: bool=False):
    print(data['id'])
    print(data['question'])
    if is_answer:
        print(data['answer'])
    print()


def main():
    lines = read_input_file('result_1.json')
    for line in lines:
        data = json.loads(line)
        print_data(data, is_answer=True)


if __name__ == '__main__':
    main()
