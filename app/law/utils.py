import re
from itertools import product

import cpca


# 预处理法律文书案号
def preprocess_case_num(case_num: str):
    # 移除所有空白字符
    case_num = case_num.replace(' ', '')

    # 移除常见的无关字符
    case_num = case_num.replace('，', '').replace(',', '')
    case_num = case_num.replace('判决', '').replace('判', '')
    case_num = case_num.replace('年', '')

    # 将各种括号替换成半角小括号
    brackets = ['[', ']', '【', '】', '（', '）', '{', '}']
    for bracket in brackets:
        case_num = case_num.replace(bracket, '')

    # 移除连续的左括号或右括号
    case_num = re.sub(r'\(+', '(', case_num)
    case_num = re.sub(r'\)+', ')', case_num)

    # 确保只有一对括号
    if '(' in case_num and ')' in case_num:
        first_open = case_num.index('(')
        last_close = case_num.rindex(')')
        case_num = case_num[:first_open] + '(' + case_num[first_open+1:last_close] + ')' + case_num[last_close+1:]
    elif '(' in case_num:
        case_num = case_num.replace('(', '')
    elif ')' in case_num:
        case_num = case_num.replace(')', '')

    return case_num


def correct_case_num(case_num: str) -> str:
    """
    使用正则表达式匹配年份并添加括号
    """
    # 这是为了解决年份只有两位的情况，但是不确定是否稳定
    pattern = r'^[\(]?(\d+)[\)]?'
    match = re.search(pattern, case_num)

    if match:
        year = match.group(1)
        if len(year) == 2:
            # 如果是2位数年份，添加"20"前缀
            case_num = re.sub(pattern, f'(20{year})', case_num)
        elif len(year) == 4:
            # 如果是4位数年份，只需确保有括号
            case_num = re.sub(pattern, f'({year})', case_num)
    
    # 如果缺少左括号，添加左括号
    if not case_num.startswith('('):
        case_num = '(' + case_num
    
    # 如果缺少右括号，在第5个字符后添加右括号
    if ')' not in case_num:
        case_num = case_num[:5] + ')' + case_num[5:]
    
    if case_num[-1] == '案':
        case_num = case_num[:-1]
    
    # 确保案号以"号"结尾
    if not case_num.endswith('号'):
        case_num += '号'

    return case_num


# 预处理限制高消费案号
def preprocess_xzgxf_case_num(case_num: str):
    # 移除所有空白字符
    case_num = case_num.replace(' ', '')

    # 将半角中括号替换成全角括号
    case_num = case_num.replace('[', '（').replace(']', '）')
    # 将全角中括号替换成全角括号
    case_num = case_num.replace('【', '（').replace('】', '）')
    # 将半角括号替换成全角括号
    case_num = case_num.replace('(', '（').replace(')', '）')

    return case_num


def correct_xzgxf_case_num(case_num: str) -> str:
    # 这是为了解决年份只有两位的情况，但是不确定是否稳定
    pattern = r'^[\（\(]?(\d+)[\）\)]?[\u4e00-\u9fff]'
    match = re.search(pattern, case_num)
    if match and len(match.group(1)) == 2:
        pattern = r'^(\d{2})'
        case_num = re.sub(pattern, r'20\1', case_num)

    # 如果缺少左括号，添加左括号
    if not case_num.startswith('（'):
        case_num = '（' + case_num
    
    # 如果缺少右括号，在第5个字符后添加右括号
    if '）' not in case_num:
        case_num = case_num[:5] + '）' + case_num[5:]

    if case_num[-1] == '案':
        case_num = case_num[:-1]

    return case_num


# 检查返回值是否为空
def is_empty(item):
    if item is None:
        return True
    elif isinstance(item, (list, dict, str)):
        return len(item) == 0
    else:
        return False


def extract_case_num(case_num: str):
    pattern = r'\((\d+)\)([\u4e00-\u9fa5\d]+?)([\u4e00-\u9fa5]{1,4})(\d+)号'
    match = re.match(pattern, case_num)
    
    if match:
        year, court, case_type, number = match.groups()
        return {
            'year': year,
            'court_code': court,
            'case_type': case_type,
            'number': number
        }
    else:
        return None


def extract_case_num_str(text: str):
    pattern = r'\(.*?号'
    match = re.search(pattern, text)
    if match:
        case_number = match.group()
        return case_number
    return None


def merge_adjacent_chars(s):
    """
    合并相邻重复字符，数字也会被合并

    22002200 => 2020, 粤粤03 => 粤03, 民民终终 => 民终
    """
    return re.sub(r'(.)\1+', r'\1', s)


def augment_case_num(case_num: str) -> list[str]:
    """
    对案号进行增强
    """
    augmented_case_num_list = []
    case_num = preprocess_case_num(case_num)
    case_num = correct_case_num(case_num)
    augmented_case_num_list.append(case_num)

    case_num_element = extract_case_num(case_num)
    if case_num_element is None:
        return augmented_case_num_list

    merged_year = merge_adjacent_chars(case_num_element['year'])
    merged_court_code = merge_adjacent_chars(case_num_element['court_code'])
    merged_case_type = merge_adjacent_chars(case_num_element['case_type'])

    # 年份长度不等于4的过滤掉
    year_variations = [merged_year, case_num_element['year']]
    year_variations = list(set(year_variations))
    year_variations = [year for year in year_variations if len(year) == 4]

    # 法院代字不好过滤
    court_code_variations = [merged_court_code, case_num_element['court_code']]
    court_code_variations = list(set(court_code_variations))

    # 案件类型超过3的过滤掉，目前没有看到有4位以上的案件类型
    # https://mp.weixin.qq.com/s/Ph7Yfu70qdi6cmizHSPPtQ
    case_type_variations = [merged_case_type, case_num_element['case_type']]
    case_type_variations = list(set(case_type_variations))
    case_type_variations = [case_type for case_type in case_type_variations if len(case_type) <= 3]

    # 使用笛卡尔积生成所有可能的组合
    all_combinations = product(year_variations, court_code_variations, case_type_variations)
    for year, court_code, case_type in all_combinations:
        new_case_num = f"({year}){court_code}{case_type}{case_num_element['number']}号"
        augmented_case_num_list.append(new_case_num)

    augmented_case_num_list = list(set(augmented_case_num_list))
    return augmented_case_num_list


def augment_lawfirm_name(lawfirm_name: str) -> list[str]:
    """
    对律师事务所名称进行增强
    """

    augmented_lawfirm_name_list = []

    pattern = r'^(.*?)(事务所)$'
    match = re.match(pattern, lawfirm_name)
    if match:
        prefix = match.group(1)
        if "律师" not in prefix:
            augmented_lawfirm_name_list.append(f"{prefix}律师事务所")

    return augmented_lawfirm_name_list


def replace_case_num_parentheses(text):
    """
    将案号里的全角括号替换成半角括号
    """
    pattern = r'\（(\d{4})\）([\u4e00-\u9fa5\d]+?)([\u4e00-\u9fa5]{1,4})(\d+)号'

    def replace_parentheses(match):
        year, court, case_type, number = match.groups()
        return f'({year}){court}{case_type}{number}号'
    
    return re.sub(pattern, replace_parentheses, text)


def augment_province(province):
    df = cpca.transform([province])

    if df['省'][0]: 
        province = df['省'][0]
    return province

def augment_city(city):
    def _easy(df):
        new_city = ''
        if df['市'][0] == '市辖区':
            new_city = df['省'][0]
        else:
            # 可能为 None，所以要用 is_empty 判断
            new_city = df['市'][0]
        return new_city

    df = cpca.transform([city])
    new_city = _easy(df)
    if not is_empty(new_city):
        return new_city

    df = cpca.transform([f"{city}区"])
    new_city = _easy(df)
    if not is_empty(new_city):
        return new_city
    
    df = cpca.transform([f"{city}市"])
    if is_empty(df['市'][0]) and not is_empty(df['省'][0]):
        new_city = df['省'][0]
        return new_city

    return city


def augment_by_cpca(value):
    df = cpca.transform([f"{value}"])
    if is_empty(df['省'][0]) \
        and is_empty(df['市'][0]) \
        and is_empty(df['区'][0]) \
        and is_empty(df['地址'][0]):
        return ''

    province = df['省'][0]
    city = df['市'][0]
    county = df['区'][0]
    address = df['地址'][0]

    def _combine():
        parts = []
        if province: parts.append(province)
        if city and city != '市辖区': parts.append(city)
        if county: parts.append(county)
        if address: parts.append(address)
        return "".join(parts)

    augmented_name = _combine()
    augmented_name_list = [augmented_name]

    return augmented_name_list


def augment_county(county):
    df = cpca.transform([county])
    new_county = county
    if df['市'][0] == '市辖区':
        new_county = df['区'][0]
        return new_county
    
    df = cpca.transform([f"{county}区"])
    new_county = county
    if df['市'][0] == '市辖区':
        new_county = df['区'][0]
        return new_county
    
    return county
