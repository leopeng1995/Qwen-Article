import os
import re
import json
import requests
import functools
from typing import Annotated, List, Union, Any
from datetime import datetime

import cpca

from qwergpt.logs import logger
from qwergpt.utils import (
    no_chinese,
    has_digits,
    no_digits,
    convert_date_format
)

from app.law.utils import (
    is_empty,
    extract_case_num,
    preprocess_case_num, 
    correct_case_num,
    preprocess_xzgxf_case_num,
    correct_xzgxf_case_num,
    augment_province,
    augment_city,
    augment_case_num,
    augment_by_cpca,
)
from app.law.exceptions import ToolException


registered_tools = list()
registered_tools_map = {}

domain = "comm.chatglm.cn"
url_prefix = f"https://{domain}/law_api/s1_b"

team_token = os.getenv('TEAM_TOKEN') or '2C8BAFCF8C64D3156AE196A0F731D6DF7273C408116B5524'
headers = {
    'Content-Type': 'application/json',
    'Authorization': 'Bearer ' + team_token
}


def register_tool(func):
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        return func(*args, **kwargs)

    registered_tools.append(func)
    registered_tools_map[func.__name__] = func
    return wrapper


@register_tool
def get_company_info(
    value: Annotated[str, "字段值"],
):
    """
    根据 **公司名称**、**公司简称** 或 **公司代码** 查找上市公司基本信息
    根据返回结果判断，结果为空说明该公司是非上市公司，请使用 get_company_register 工具查询 CompanyRegister

    Args:
        value (str): 公司名称、公司简称或公司代码
    
    Returns:
        CompanyInfo: dict

    Example:
        >>> company_info = get_company_info("示例公司名称")
        >>> company_info.get('所属行业')
    """
    if is_empty(value):
        raise ToolException(traceback='', ename='get_company_info 参数错误', evalue='value 不能为空')
    if isinstance(value, list) or isinstance(value, dict):
        raise ToolException(traceback='', ename='get_company_info 参数错误', evalue='value 需要字符串类型')
    # 如果 value 没有中文且长度大于 6，应该是统一社会信用代码
    if no_chinese(value) and len(value) > 6:
        raise ToolException(traceback='', ename='get_company_info 参数错误', evalue='value 参数错误')
    if value == '示例公司名称':
        raise ToolException(traceback='', ename='get_company_info 参数错误', evalue='value 参数错误')

    url = f"{url_prefix}/get_company_info"

    # 公司名称
    response = requests.post(url, json={
        "query_conds": {
            "公司名称": value
        },
        "need_fields": []
    }, headers=headers)
    data = response.json()
    if not is_empty(data):
        return data
    
    # 公司简称
    response = requests.post(url, json={
        "query_conds": {
            "公司简称": value
        },
        "need_fields": []
    }, headers=headers)
    data = response.json()
    if not is_empty(data):
        return data
    
    # 公司代码
    response = requests.post(url, json={
        "query_conds": {
            "公司代码": value
        },
        "need_fields": []
    }, headers=headers)
    data = response.json()
    return data


@register_tool
def get_company_register(
    value: Annotated[str, "字段值"],
):
    """
    根据公司名称，查询工商信息

    Args:
        value (str): 公司名称
    
    Returns:
        CompanyRegister: dict

    Example:
        >>> company_register = get_company_register("示例公司名称")
    """
    if is_empty(value):
        raise ToolException(traceback='', ename='get_company_register 参数错误', evalue='value 不能为空')
    if isinstance(value, list):
        raise ToolException(traceback='', ename='get_company_register 参数错误', evalue='value 需要字符串类型')
    if value == '示例公司名称':
        raise ToolException(traceback='', ename='get_company_register 参数错误', evalue='value 不能使用 **示例公司名称**')
    if isinstance(value, str) and len(value) <= 4:
        raise ToolException(traceback='', ename='get_company_register 参数错误', evalue='value 不能使用公司简称，请先根据公司简称使用 get_company_info 工具获取公司名称')
    if isinstance(value, str) and no_chinese(value):
        if len(value) > 6:
            raise ToolException(traceback='', ename='get_company_register 参数错误', evalue='不能使用统一社会信用代码')
        else:
            raise ToolException(traceback='', ename='get_company_register 参数错误', evalue='不能使用公司代码')

    # 这种情况是直接把 get_company_register_name 的返回值传入
    if isinstance(value, dict):
        if '公司名称' not in value:
            raise ToolException(traceback='', ename='get_company_register 参数错误', evalue='value 需要字符串类型')

        value = value['公司名称']
        url = f"{url_prefix}/get_company_register"
        response = requests.post(url, json={
            "query_conds": {
                "公司名称": value
            },
            "need_fields": []
        }, headers=headers)
        data = response.json()
        return data

    url = f"{url_prefix}/get_company_register"
    response = requests.post(url, json={
        "query_conds": {
            "公司名称": value
        },
        "need_fields": []
    }, headers=headers)
    data = response.json()
    return data


@register_tool
def get_company_register_name(
    value: Annotated[str, "字段值"],
):
    """
    根据统一社会信用代码查询公司名称

    Args:
        value (str): 统一社会信用代码
    
    Returns:
        UnifiedSocialCreditCodeName: dict

    Example:
        >>> company_register = get_company_register_name("示例统一社会信用代码")
        >>> company_register.get('公司名称')
    """
    if is_empty(value):
        raise ToolException(traceback='', ename='get_company_register_name 参数错误', evalue='value 不能为空')
    if isinstance(value, list) or isinstance(value, dict):
        raise ToolException(traceback='', ename='get_company_register_name 参数错误', evalue='value 需要字符串类型')
    if value == '示例统一社会信用代码':
        raise ToolException(traceback='', ename='get_company_register_name 参数错误', evalue='value 不能使用 **示例统一社会信用代码**')
    if isinstance(value, str):
        if len(value) == 6:
            raise ToolException(traceback='', ename='get_company_register_name 参数错误', evalue='value 不能使用公司代码，请使用 get_company_info 工具')

    url = f"{url_prefix}/get_company_register_name"
    response = requests.post(url, json={
        "query_conds": {
            "统一社会信用代码": value
        },
        "need_fields": []
    }, headers=headers)
    data = response.json()
    return data


@register_tool
def get_parent_company_info(
    value: Annotated[str, "字段值"],
):
    """
    根据公司名称查询控股公司名称、投资比例、投资金额

    Args:
        value (str): 公司名称
    
    Returns:
        SubCompanyInfo: dict

    Example:
        >>> sub_company_info = get_parent_company_info("示例公司名称")
        >>> sub_company_info.get('关联上市公司全称')
    """
    if is_empty(value):
        raise ToolException(traceback='', ename='get_parent_company_info 参数错误', evalue='value 不能为空')
    if isinstance(value, list) or isinstance(value, dict):
        raise ToolException(traceback='', ename='get_parent_company_info 参数错误', evalue='vaule 需要使用字符串类型')
    if value == '示例公司名称':
        raise ToolException(traceback='', ename='get_parent_company_info 参数错误', evalue='value 不能使用 **示例公司名称**')
    if no_chinese(value):
        if len(value) > 6:
            raise ToolException(traceback='', ename='get_parent_company_info 参数错误', evalue='不能使用统一社会信用代码')
        else:
            raise ToolException(traceback='', ename='get_parent_company_info 参数错误', evalue='不能使用公司代码')
    if len(value) < 5:
        raise ToolException(traceback='', ename='get_parent_company_info 参数错误', evalue='不能使用公司简称，请先试用 get_company_info 工具获取公司名称')

    url = f"{url_prefix}/get_sub_company_info"
    response = requests.post(url, json={
        "query_conds": {
            "公司名称": value
        },
        "need_fields": []
    }, headers=headers)
    data = response.json()
    return data


@register_tool
def get_sub_company_info_list(
    value: Annotated[str, "字段值"],
):
    """
    查询公司的子公司列表

    Args:
        value (str): 公司名称
    
    Returns:
        list[SubCompanyInfo]

    Example:
        >>> sub_company_info_list = get_sub_company_info_list("示例公司名称")
        >>> sub_company_info_list[0].get('上市公司投资金额')
    """
    if is_empty(value):
        raise ToolException(traceback='', ename='get_sub_company_info_list 参数错误', evalue='value 不能为空')
    if isinstance(value, list) or isinstance(value, dict):
        raise ToolException(traceback='', ename='get_sub_company_info_list 参数错误', evalue='value 需要字符串类型')
    if value == '示例公司名称':
        raise ToolException(traceback='', ename='get_sub_company_info_list 参数错误', evalue='value 参数错误')

    url = f"{url_prefix}/get_sub_company_info_list"
    response = requests.post(url, json={
        "query_conds": {
            "关联上市公司全称": value
        },
        "need_fields": []
    }, headers=headers)
    data = response.json()
    if isinstance(data, dict):
        return [data]
    return data


@register_tool
def get_temp_info(
    province: Annotated[str, "省份"],
    city: Annotated[str, "城市"],
    date: Annotated[str, "日期"],
):
    """
    根据日期及省份城市查询天气相关信息

    Args:
        province (str): 省份
        city (str): 城市
        date (str): 日期
    
    Returns:
        TempInfo: dict

    Example:
        >>> temp_info = get_temp_info("示例省份", "示例城市", "示例日期")
        >>> temp_info.get('最高温度')
    """
    if is_empty(province):
        raise ToolException(traceback='', ename='get_temp_info 参数错误', evalue='province 不能为空')
    if is_empty(city):
        raise ToolException(traceback='', ename='get_temp_info 参数错误', evalue='city 不能为空')
    if is_empty(date):
        raise ToolException(traceback='', ename='get_temp_info 参数错误', evalue='date 不能为空')
    if isinstance(province, list) or isinstance(province, dict):
        raise ToolException(traceback='', ename='get_temp_info 参数错误', evalue='province 需要字符串类型')
    if isinstance(city, list) or isinstance(city, dict):
        raise ToolException(traceback='', ename='get_temp_info 参数错误', evalue='city 需要字符串类型')
    if isinstance(date, list) or isinstance(date, dict) or isinstance(date, int):
        raise ToolException(traceback='', ename='get_temp_info 参数错误', evalue='date 需要 yyyy-MM-DD 字符串类型')
    if province.startswith('示例'):
        raise ToolException(traceback='', ename='get_temp_info 参数错误', evalue='province 不能使用 **示例省份**')
    if city.startswith('示例'):
        raise ToolException(traceback='', ename='get_temp_info 参数错误', evalue='city 不能使用 **示例城市**')
    if date.startswith('示例'):
        raise ToolException(traceback='', ename='get_temp_info 参数错误', evalue='date 不能使用 **示例日期**')

    try:
        date = convert_date_format(date)
    except:
        pattern = r'(\d{4})年0?(\d{1,2})月0?(\d{1,2})日'
        match = re.match(pattern, date)
        if match:
            year, month, day = match.groups()
            date = f"{year}年{month}月{day}日"
        else:
            raise ToolException(traceback='', ename='get_temp_info 参数错误', evalue='date 日期不符合要求，请使用 yyyy-MM-DD 格式')

    url = f"{url_prefix}/get_temp_info"
    response = requests.post(url, json={
        "query_conds": {
            "省份": province,
            "城市": city,
            "日期": date,
        },
        "need_fields": []
    }, headers=headers)
    data = response.json()
    if not is_empty(data):
        return data
    
    # 对省份、城市进行增强
    province = augment_province(province)
    city = augment_city(city)

    url = f"{url_prefix}/get_temp_info"
    response = requests.post(url, json={
        "query_conds": {
            "省份": province,
            "城市": city,
            "日期": date,
        },
        "need_fields": []
    }, headers=headers)
    data = response.json()
    return data


@register_tool
def get_legal_abstract(
    value: Annotated[str, "字段值"],
):
    """
    根据案号查询文本摘要

    Args:
        value (str): 案号
    
    Returns:
        LegalAbstract: dict

    Example:
        >>> legal_abstract = get_legal_abstract("示例案号")
        >>> legal_abstract.get('文本摘要')
    """
    if is_empty(value):
        raise ToolException(traceback='', ename='get_legal_abstract 参数错误', evalue='value 不能为空')
    if isinstance(value, list) or isinstance(value, dict):
        raise ToolException(traceback='', ename='get_legal_abstract 参数错误', evalue='value 需要字符串类型')
    if value == '示例案号':
        raise ToolException(traceback='', ename='get_legal_abstract 参数错误', evalue='value 参数错误')

    value = preprocess_case_num(value)
    pattern = r'^[\（\(]?(\d+)[\）\)]?[\u4e00-\u9fff]'
    match = re.search(pattern, value)
    if not match:
        raise ToolException(traceback='', ename='get_legal_abstract 参数错误', evalue='案号缺少年份，请使用问题的年份或案号')
    value: str = correct_case_num(value)
    
    value = value.replace('(', '（')
    value = value.replace(')', '）')

    url = f"{url_prefix}/get_legal_abstract"
    response = requests.post(url, json={
        "query_conds": {
            "案号": value
        },
        "need_fields": []
    }, headers=headers)
    data = response.json()
    return data


def correct_case_num2(
    case_num: Annotated[str, "案号"],
):
    """
    根据案号查询裁判文书相关信息

    Args:
        case_num (str): 案号
    
    Returns:
        LegalDoc: dict

    Example:
        >>> legal_doc = get_legal_document("示例案号")
        >>> legal_doc.get('案由')
    """
    def _query(v):
        url = f"{url_prefix}/get_legal_document"
        response = requests.post(url, json={
            "query_conds": {
                "案号": v
            },
            "need_fields": []
        }, headers=headers)
        data = response.json()
        return data

    case_num = preprocess_case_num(case_num)
    data = _query(case_num)
    if not is_empty(data):
        return data
    
    # 22002200皖05民终1584号
    pattern = r'^(\(?\d+\)?)'
    match = re.search(pattern, case_num)
    if match:
        num = match.group(1)
        if num.startswith('(') and num.endswith(')'):
            case_num = case_num  # 保持原样
        else:
            case_num = f"({num})" + case_num[len(num):]

    # 从问题中直接提取的案号查询不到法律文书
    # 就对案号进行增强，增加一些可能性的尝试
    augmented_case_num_list = augment_case_num(case_num)
    for augmented_case_num in augmented_case_num_list:
        data = _query(augmented_case_num)
        if not is_empty(data):
            return data
    
    # 2019年 湖北襄阳市中级人民法院民初1613号案
    # TODO 这种如果不合并工具，如何增强？

    return data


@register_tool
def get_legal_document(
    value: Annotated[str, "字段值"],
):
    """
    根据案号查询裁判文书相关信息

    Args:
        value (str): 案号
    
    Returns:
        LegalDoc: dict

    Example:
        >>> legal_doc = get_legal_document("示例案号")
        >>> legal_doc.get('案由')
    """
    if is_empty(value):
        raise ToolException(traceback='', ename='get_legal_document 参数错误', evalue='value 不能为空')
    if isinstance(value, list) or isinstance(value, dict):
        raise ToolException(traceback='', ename='get_legal_document 参数错误', evalue='value 需要字符串类型')
    if value == '示例案号':
        raise ToolException(traceback='', ename='get_legal_document 参数错误', evalue='value 参数错误')
    if '法院' in value:
        raise ToolException(traceback='', ename='get_legal_document 参数错误', evalue='案号格式: （起诉年份）+ 法院代字 + 案件类型代字 + 案件编号 + "号"，通过法院名称使用 get_court_code 工具获取法院代字')

    value = preprocess_case_num(value)
    pattern = r'^[\（\(]?(\d+)[\）\)]?[\u4e00-\u9fff]'
    match = re.search(pattern, value)
    if not match:
        raise ToolException(traceback='', ename='get_legal_document 参数错误', evalue='案号缺少年份，请使用问题的年份或案号')
    value = correct_case_num(value)

    url = f"{url_prefix}/get_legal_document"
    response = requests.post(url, json={
        "query_conds": {
            "案号": value
        },
        "need_fields": []
    }, headers=headers)
    data = response.json()
    return data


@register_tool
def get_legal_document_list(
    value: Annotated[str, "字段值"],
):
    """
    查询公司的涉案信息，得到案件列表
    根据查询目标遍历列表，不要假设取其中一个案件
    需要排序时，结合 rank 工具一起使用

    Args:
        value (str): 公司名称
    
    Returns:
        list[LegalDoc]

    Example:
        >>> legal_doc_list = get_legal_document_list("示例公司名称")
        >>> legal_doc_list[0].get('案由')
    """
    if is_empty(value):
        raise ToolException(traceback='', ename='get_legal_document_list 参数错误', evalue='value 不能为空')
    if isinstance(value, list):
        raise ToolException(traceback='', ename='get_legal_document_list 参数错误', evalue='value 需要字符串类型')
    if isinstance(value, str) and len(value) <= 4:
        raise ToolException(traceback='', ename='get_legal_document_list 参数错误', evalue='value 不能使用公司简称')
    if isinstance(value, str) and no_chinese(value):
        if len(value) > 6:
            raise ToolException(traceback='', ename='get_legal_document_list 参数错误', evalue='不能使用统一社会信用代码')
        else:
            raise ToolException(traceback='', ename='get_legal_document_list 参数错误', evalue='不能使用公司代码')
    if value == '示例公司名称':
        raise ToolException(traceback='', ename='get_legal_document_list 参数错误', evalue='value 不能使用 **示例公司名称**')

    # 这种情况是直接把 get_company_register_name 的返回值传入
    if isinstance(value, dict):
        raise ToolException(traceback='', ename='get_legal_document_list 参数错误', evalue='value 不能是 dict 类型，请提取 公司名称 字段')

    url = f"{url_prefix}/get_legal_document_list"
    response = requests.post(url, json={
        "query_conds": {
            "关联公司": value
        },
        "need_fields": []
    }, headers=headers)
    data = response.json()
    if isinstance(data, dict):
        if len(data) == 0:
            return []
        else:
            return [data]
    return data


@register_tool
def get_court_info(
    value: Annotated[str, "字段值"],
):
    """
    根据法院名称查询法院名录相关信息

    Args:
        value (str): 法院名称
    
    Returns:
        CourtInfo: dict

    Example:
        >>> court_info = get_court_info("示例法院名称")
        >>> court_info.get('法院地址')
    """
    if is_empty(value):
        raise ToolException(traceback='', ename='get_court_info 参数错误', evalue='value 不能为空')
    if isinstance(value, list) or isinstance(value, dict):
        raise ToolException(traceback='', ename='get_court_info 参数错误', evalue='value 需要字符串类型')
    if value == "示例法院名称":
        raise ToolException(traceback='', ename='get_court_info 参数错误', evalue='value 不能使用 **示例法院名称**')
    if has_digits(value):
        raise ToolException(traceback='', ename='get_court_info 参数错误', evalue='value 请使用法院名称，而不是法院代字')

    url = f"{url_prefix}/get_court_info"
    response = requests.post(url, json={
        "query_conds": {
            "法院名称": value
        },
        "need_fields": []
    }, headers=headers)
    data = response.json()
    if not is_empty(data):
        return data
    
    augmented_court_name_list = augment_by_cpca(value)
    for augmented_court_name in augmented_court_name_list:
        response = requests.post(url, json={
            "query_conds": {
                "法院名称": augmented_court_name
                },
            "need_fields": []
        }, headers=headers)
        data = response.json()
        if not is_empty(data):
            return data

    return data


@register_tool
def get_court_code(
    value: Annotated[str, "字段值"],
):
    """
    根据法院名称或者法院代字查询法院代字等相关数据（CourtCode）

    Args:
        value (str): 法院名称或法院代字
    
    Returns:
        CourtCode: dict

    Example:
        >>> court_code = get_court_code("示例法院名称")
        >>> court_code.get('法院级别')
        >>> court_code = get_court_code("示例法院代字")
        >>> court_code.get('法院负责人')
    """
    if is_empty(value):
        raise ToolException(traceback='', ename='get_court_code 参数错误', evalue='value 不能为空')
    if isinstance(value, list) or isinstance(value, dict):
        raise ToolException(traceback='', ename='get_court_code 参数错误', evalue='value 需要字符串类型')
    if value == "示例法院名称":
        raise ToolException(traceback='', ename='get_court_code 参数错误', evalue='value 不能使用 **示例法院名称**')
    if value == "示例法院代字":
        raise ToolException(traceback='', ename='get_court_code 参数错误', evalue='value 不能使用 **示例法院代字**')

    # 法院名称
    url = f"{url_prefix}/get_court_code"
    response = requests.post(url, json={
        "query_conds": {
            "法院名称": value
        },
        "need_fields": []
    }, headers=headers)
    data = response.json()
    if not is_empty(data):
        return data
    
    if no_digits(value):
        augmented_court_name_list = augment_by_cpca(value)
        for augmented_court_name in augmented_court_name_list:
            response = requests.post(url, json={
                "query_conds": {
                    "法院名称": augmented_court_name
                },
                "need_fields": []
            }, headers=headers)
            data = response.json()
            if not is_empty(data):
                return data
    
    # 法院代字
    url = f"{url_prefix}/get_court_code"
    response = requests.post(url, json={
        "query_conds": {
            "法院代字": value
        },
        "need_fields": []
    }, headers=headers)
    data = response.json()
    return data


@register_tool
def get_lawfirm_info(
    value: Annotated[str, "字段值"],
):
    """
    根据律师事务所名称查询律师事务所信息（LawfirmInfo）

    Args:
        value (str): 律师事务所名称
    
    Returns:
        LawfirmInfo: dict

    Example:
        >>> lawfirm_info = get_lawfirm_info("示例律师事务所名称")
        >>> lawfirm_info.get('律师事务所负责人')
    """
    if is_empty(value):
        raise ToolException(traceback='', ename='get_lawfirm_info 参数错误', evalue='value 不能为空')
    if isinstance(value, list) or isinstance(value, dict):
        raise ToolException(traceback='', ename='get_lawfirm_info 参数错误', evalue='value 需要字符串类型')
    if value == "示例律师事务所名称":
        raise ToolException(traceback='', ename='get_lawfirm_info 参数错误', evalue='value 不能使用 **示例律师事务所名称**')

    # 广东金粤律师事务所,金粤律师事务所
    if ',' in value:
        value = value.split(',')[0]

    url = f"{url_prefix}/get_lawfirm_info"
    response = requests.post(url, json={
        "query_conds": {
            "律师事务所名称": value
        },
        "need_fields": []
    }, headers=headers)
    data = response.json()
    return data


@register_tool
def get_lawfirm_log(
    value: Annotated[str, "字段值"],
):
    """
    根据律师事务所名称查询律师事务所统计数据（LawfirmLog）

    Args:
        value (str): 律师事务所名称
    
    Returns:
        LawfirmLog: dict

    Example:
        >>> lawfirm_log = get_lawfirm_log("示例律师事务所名称")
        >>> lawfirm_log.get('服务已上市公司')
    """
    if is_empty(value):
        raise ToolException(traceback='', ename='get_lawfirm_log 参数错误', evalue='value 不能为空')
    if isinstance(value, list) or isinstance(value, dict):
        raise ToolException(traceback='', ename='get_lawfirm_log 参数错误', evalue='value 需要字符串类型')
    if value == "示例律师事务所名称":
        raise ToolException(traceback='', ename='get_lawfirm_log 参数错误', evalue='value 不能使用 **示例律师事务所名称**')
    
    url = f"{url_prefix}/get_lawfirm_log"
    response = requests.post(url, json={
        "query_conds": {
            "律师事务所名称": value
        },
        "need_fields": []
    }, headers=headers)
    data = response.json()
    return data


@register_tool
def get_address_info(
    value: Annotated[str, "字段值"],
):
    """
    根据地址查该地址对应的省份城市区县

    Args:
        value (str): 地址
    
    Returns:
        AddrInfo: dict

    Example:
        >>> address_info = get_address_info("示例地址")
        >>> address_info.get('区县')
    """
    if is_empty(value):
        raise ToolException(traceback='', ename='get_address_info 参数错误', evalue='value 不能为空')
    if isinstance(value, list) or isinstance(value, dict):
        raise ToolException(traceback='', ename='get_address_info 参数错误', evalue='value 需要字符串类型')
    if value.startswith("示例"):
        raise ToolException(traceback='', ename='get_address_info 参数错误', evalue='value 不能使用 **示例地址**')

    url = f"{url_prefix}/get_address_info"
    response = requests.post(url, json={
        "query_conds": {
            "地址": value
        },
        "need_fields": []
    }, headers=headers)
    data = response.json()
    if not is_empty(data):
        return data
    
    df = cpca.transform([value])
    if is_empty(df['地址'][0]):
        raise ToolException(traceback='', ename='get_address_info 参数错误', evalue='请使用 get_address_code 工具查询')

    # 江苏省连云港市连云港高新技术产业开发区
    if is_empty(df['区'][0]) and df['地址'][0]:
        raise ToolException(traceback='', ename='get_address_info 参数错误', evalue='请使用 get_address_code 工具查询')

    return data


@register_tool
def get_address_code(
    value: Annotated[str, "地址"]
):
    """
    根据地址查询区划代码

    Args:
        value (str): 地址
    
    Returns:
        AddrCode: dict

    Example:
        >>> address_code = get_address_code("示例地址")
        >>> address_code.get('区县区划代码')
    """
    if is_empty(value):
        raise ToolException(traceback='', ename='get_address_code 参数错误', evalue='value 不能为空')
    if isinstance(value, list) or isinstance(value, dict):
        raise ToolException(traceback='', ename='get_address_code 参数错误', evalue='value 需要字符串类型')
    if value.startswith("示例"):
        raise ToolException(traceback='', ename='get_address_code 参数错误', evalue='value 不能使用 **示例地址**')

    df = cpca.transform([value])
    province = df['省'][0] if df['省'][0] else ''
    city = df['市'][0] if df['市'][0] else ''
    # 直辖市
    if city == '市辖区': city = province
    county = df['区'][0] if df['区'][0] else ''
    address = df['地址'][0] if df['地址'][0] else ''

    if is_empty(county) and is_empty(address):
        data = {
            "省份": province,
            "城市": city,
            "城市区划代码": "",
            "区县": "",
            "区县区划代码": ""
        }
        return data
    
    if is_empty(county) and not is_empty(address):
        county = address

    url = f"{url_prefix}/get_address_code"
    response = requests.post(url, json={
        "query_conds": {
            "省份": province,
            "城市": city,
            "区县": county,
        },
        "need_fields": []
    }, headers=headers)
    data = response.json()
    if not is_empty(data):
        return data
    
    # 江苏省连云港市连云港高新技术产业开发区
    # 江苏省连云港市高新技术产业开发区
    county = value.replace(province, '').replace(city, '')
    response = requests.post(url, json={
        "query_conds": {
            "省份": province,
            "城市": city,
            "区县": county,
        },
        "need_fields": []
    }, headers=headers)
    data = response.json()
    if not is_empty(data):
        return data

    return data

@register_tool
def get_xzgxf_info(
    value: Annotated[str, "字段值"],
):
    """
    根据案号查询限制高消费相关信息

    Args:
        value (str): 案号
    
    Returns:
        XzgxfInfo: dict

    Example:
        >>> xzgxf_info = get_xzgxf_info("示例案号")
        >>> xzgxf_info.get('限制高消费企业名称')
    """
    if is_empty(value):
        raise ToolException(traceback='', ename='get_xzgxf_info 参数错误', evalue='value 不能为空')
    if isinstance(value, list) or isinstance(value, dict):
        raise ToolException(traceback='', ename='get_xzgxf_info 参数错误', evalue='value 需要字符串类型')
    if value.startswith('示例'):
        raise ToolException(traceback='', ename='get_xzgxf_info 参数错误', evalue='value 不能使用 **示例案号**')

    # 限制高消费的案号用的是全角括号
    value = preprocess_xzgxf_case_num(value)
    value = correct_xzgxf_case_num(value)

    url = f"{url_prefix}/get_xzgxf_info"
    response = requests.post(url, json={
        "query_conds": {
            "案号": value,
        },
        "need_fields": []
    }, headers=headers)
    data = response.json()
    if type(data) is list:
        return {}
    return data


@register_tool
def get_xzgxf_info_list(
    value: Annotated[str, "字段值"],
):
    """
    根据公司名称查询所有限制高消费相关信息list
    上市公司和非上市公司的公司名称都可以查询

    Args:
        value (str): 公司名称
    
    Returns:
        List[XzgxfInfo]

    Example:
        >>> xzgxf_info_list = get_xzgxf_info_list("示例公司名称")
        >>> xzgxf_info[0].get('申请人')
    """
    if is_empty(value):
        raise ToolException(traceback='', ename='get_xzgxf_info_list 参数错误', evalue='value 不能为空')
    if isinstance(value, list):
        raise ToolException(traceback='', ename='get_xzgxf_info_list 参数错误', evalue='value 需要字符串类型')
    if isinstance(value, str) and len(value) <= 4:
        raise ToolException(traceback='', ename='get_xzgxf_info_list 参数错误', evalue='value 不能使用公司简称')
    if isinstance(value, str) and no_chinese(value):
        if len(value) > 6:
            raise ToolException(traceback='', ename='get_xzgxf_info_list 参数错误', evalue='不能使用统一社会信用代码')
        else:
            raise ToolException(traceback='', ename='get_xzgxf_info_list 参数错误', evalue='不能使用公司代码')
    if value == '示例公司名称':
        raise ToolException(traceback='', ename='get_xzgxf_info_list 参数错误', evalue='value 不能使用 **示例公司名称**')

    # 这种情况是直接把 get_company_register_name 的返回值传入
    if isinstance(value, dict):
        if '公司名称' not in value:
            raise ToolException(traceback='', ename='get_xzgxf_info_list 参数错误', evalue='value 需要字符串类型')
        
        value = value['公司名称']
        url = f"{url_prefix}/get_xzgxf_info_list"
        response = requests.post(url, json={
            "query_conds": {
                "限制高消费企业名称": value
            },
            "need_fields": []
        }, headers=headers)
        data = response.json()
        if isinstance(data, dict):
            if len(data) == 0:
                return []
            else:
                return [data]
        return data

    url = f"{url_prefix}/get_xzgxf_info_list"
    response = requests.post(url, json={
        "query_conds": {
            "限制高消费企业名称": value,
        },
        "need_fields": []
    }, headers=headers)
    data = response.json()
    if isinstance(data, dict):
        if len(data) == 0:
            return []
        else:
            return [data]
    return data


def search_company_info_by_name(name: str):
    """
    根据公司名称、公司简称、公司代码返回上市公司基本信息

    Args:
        name (str): 公司名称、公司简称或者英文名称
    
    Returns:
        CompanyInfo: dict
    
    Example:
        >>> company_info = search_company_info_by_name(name='示例名称')
        
    """
    # 第一步，判断公司名称
    url = f"{url_prefix}/get_company_info"
    response = requests.post(url, 
        json={
            "query_conds": {
                "公司名称": name
            },
            "need_fields": []
        }, headers=headers
    )
    data = response.json()
    if type(data) is dict and data.get('公司名称'):
        return data
    
    # 第二步，判断公司简称
    response = requests.post(url, 
        json={
            "query_conds": {
                "公司简称": name
            },
            "need_fields": []
        }, headers=headers
    )
    data = response.json()
    if type(data) is dict and data.get('公司名称'):
        return data

    # 第三步，判断英文名称
    response = requests.post(url, 
        json={
            "query_conds": {
                "公司代码": name
            },
            "need_fields": []
        }, headers=headers)
    data = response.json()
    if type(data) is dict and data.get('公司名称'):
        return data
    return None


@register_tool
def get_sum(nums: Union[List[float], List[str], List[int]]):
    """
    求和，可以对传入的int、float、str数组进行求和，str数组只能转换字符串里的千万亿，如"1万"

    Args:
        nums: Union[List[float], List[str], List[int]
    
    Returns:
        数组之和，float 类型

    Example:
        >>> get_sum([1, 2, 3, 4, 5])
        >>> get_sum(['5千万', '1亿', '0.3亿'])
    """
    if not isinstance(nums, list) or len(nums) == 0:
        return -100
    
    if any(not isinstance(x, (int, float, str)) for x in nums):
        return -100
    
    def map_str_to_num(str_num):
        try:
            str_num = str_num.replace("千", "*1e3")
            str_num = str_num.replace("万", "*1e4")
            str_num = str_num.replace("亿", "*1e8")
            return eval(str_num)
        except Exception as e:
            logger.debug(e)
            pass
        return -100
    
    if isinstance(nums[0], str):
        nums = [map_str_to_num(i) for i in nums]
    
    try:
        return sum(nums)
    except Exception as e:
        logger.debug(e)
    
    return -100


@register_tool
def rank(keys: List[Any], values: List[float], is_desc: bool = False) -> List[Any]:
    '''
    排序接口，返回按照 values 排序的 keys
    用于查询最高、第二等需要排序的信息。

    Args:
        keys: 键
        values: 值
        is_desc: 是否从大到小排序，默认从小到大排序
    
    Returns:
        排序后的 keys

    Example:
        >>> rank(keys=["a", "b", "c"], values=[2, 1, 3])
        ['b', 'a', 'c']
    '''
    return [i[0] for i in sorted(zip(keys, values), key=lambda x: x[1], reverse=is_desc)]


@register_tool
def convert_to_float(amount_str):
    """
    处理金额字符串，处理单位（万、亿）。

    Args:
        数字字符串

    Returns:
        float 浮点数

    Example:
        >>> convert_to_float('2.3亿')
        230000000
        >>> convert_to_float('3520.5万')
        35205000
    """
    if amount_str is None:
        return 0.0
    if amount_str == '':
        return 0.0
    if amount_str == '-':
        return 0.0

    amount_str = amount_str.replace(',', '')  # 移除可能的千位分隔符
    if '亿' in amount_str:
        result = float(amount_str.replace('亿', '')) * 100000000
    elif '万' in amount_str:
        result = float(amount_str.replace('万', '')) * 10000
    else:
        result = float(amount_str)
    
    # 如果结果是整数，返回整数类型
    return int(result) if result.is_integer() else result


def extract_court_code(case_num: Annotated[str, "案号"]):
    """
    提取案号的法院代字
    第一步，根据法院代字使用 get_court_code 获取 CourtCode 表
    第二步，如果需要法院地址等法院基本信息，根据上一步 CourtCode 表的法院名称使用 get_court_info 工具 获取 CourtInfo 表

    Args:
        case_num (str): 案号

    Returns:
        法院代字 (str)
    
    Example:
        >>> extract_court_code("示例案号")
    """
    if is_empty(case_num):
        raise ToolException(traceback='', ename='extract_court_code 参数错误', evalue='case_num 不能为空')
    if case_num == '示例案号':
        raise ToolException(traceback='', ename='extract_court_code 参数错误', evalue='case_num 不能使用 **示例案号**')
    if '法院' in case_num:
        raise ToolException(traceback='', ename='extract_court_code 参数错误', evalue='案号格式: （起诉年份）+ 法院代字 + 案件类型代字 + 案件编号 + "号"，通过法院名称使用 get_court_code 工具获取法院代字')

    case_num = preprocess_case_num(case_num)
    pattern = r'^[\（\(]?(\d+)[\）\)]?[\u4e00-\u9fff]'
    match = re.search(pattern, case_num)
    if not match:
        raise ToolException(traceback='', ename='extract_court_code 参数错误', evalue='案号缺少年份，请使用问题的年份或案号')
    case_num = correct_case_num(case_num)

    pattern = r'\((\d{4})\)([\u4e00-\u9fa5\d]+)(?=[民刑行赔执])'
    match = re.search(pattern, case_num)
    if match:
        return match.group(2)
    return None


@register_tool
def extract_code_from_case_num(case_num: Annotated[str, "案号"]):
    """
    提取案号的法院代字

    Args:
        case_num (str): 案号

    Returns:
        法院代字 (str)
    
    Example:
        >>> extract_code_from_case_num("示例案号")
    """
    legal_doc = correct_case_num2(case_num)
    if is_empty(legal_doc):
        return None

    case_num = legal_doc.get('案号')
    pattern = r'\((\d{4})\)([\u4e00-\u9fa5\d]+)(?=[民刑行赔执])'
    match = re.search(pattern, case_num)
    if match:
        return match.group(2)
    return None


@register_tool
def extract_year_from_case_num(
    case_num: Annotated[str, "案号"], 
    type: Annotated[str, "日期类型"] = "起诉日期"
):
    """
    根据案号查询判决日期、起诉日期或立案日期的年份

    Args:
        case_num (str): 案号
        type (str): 日期类型（判决日期、起诉日期、立案日期）

    Returns:
        年份 (int)
    
    Example:
        >>> extract_year_from_case_num("示例案号", "日期类型")
    """
    if is_empty(case_num):
        raise ToolException(traceback='', ename='extract_year_from_case_num 参数错误', evalue='case_num 不能为空')
    if case_num == '示例案号':
        raise ToolException(traceback='', ename='extract_year_from_case_num 参数错误', evalue='case_num 不能使用 **示例案号**')
    if type not in ['判决日期', '起诉日期', '立案日期']:
        raise ToolException(traceback='', ename='extract_year_from_case_num 参数错误', evalue='type 请使用 **判决日期**、**起诉日期** 或 **立案日期**')

    case_num = preprocess_case_num(case_num)
    if type == '判决日期':
        legal_doc = get_legal_document(value=case_num)
        data = datetime.strptime(legal_doc['日期'], "%Y-%m-%d %H:%M:%S")
        return data.year
    else:
        data = extract_case_num(case_num)
        return int(data['year'])


def get_court_info_by_code(code: Annotated[str, "法院代字"]):
    court_code = get_court_code(code)
    if is_empty(court_code):
        return court_code

    court_name = court_code.get("法院名称")
    court_info = get_court_info(court_name)
    return court_info


@register_tool
def convert_amount_unit(amount, from_unit, to_unit, decimal_places=None):
    """
    金额单位转换，参考 **单位规则**

    Args:
        amount (float or int): 数值，浮点型或整型
        from_unit (str): amount 的原始单位，可选: 亿元、万元、元
        to_unit (str): 转换后的查询单位，可选: 亿元、万元、元
        decimal_places (int or None): 精确到几位小数，默认为 None
    
    Returns:
        转换单位后的金额

    Example:
        >>> convert_amount_unit(1, '亿元', '万元')
        10000
        >>> convert_amount_unit(8400, '万元', '亿元', 1)
        0.8
        >>> convert_amount_unit(8400, '万元', '亿元')
        0.84
    """
    if amount == '-':
        return 0

    units = {'亿元': 1e8, '万元': 1e4, '元': 1}
    
    if from_unit not in units or to_unit not in units:
        raise ValueError("Invalid unit. Please use '亿元', '万元', or '元'.")
    
    result = amount * units[from_unit] / units[to_unit]
    
    if decimal_places is not None:
        return f"{result:.{decimal_places}f}"
    else:
        if result.is_integer():
            return int(result)
        else:
            return result


@register_tool
def get_citizens_sue_citizens(
    plaintiff_name: Annotated[str, "原告公司名称"],
    defendant_name: Annotated[str, "被告公司名称"],
    cause: Annotated[str, "案由"],
    plaintiff_lawfirm_name: Annotated[str, "原告律师事务所名称"],
    defendant_lawfirm_name: Annotated[str, "被告律师事务所名称"],
    court_name: Annotated[str, "法院名称"],
    date: Annotated[str, "起诉时间"]
):
    """
    民事起诉状(公民起诉公民)

    Args:
        plaintiff_name (str): 原告公司名称
        defendant_name (str): 被告公司名称
        cause (str): 案由
        plaintiff_lawfirm_name (str): 原告律师事务所名称
        defendant_lawfirm_name (str): 被告律师事务所名称
        court_name (str): 法院名称
        date (str): 起诉时间

    Returns:
        诉讼状 (str)
    """
    # 法定代表人可能还要考虑如果不是上市公司的情况
    if plaintiff_name.endswith('的法人'):
        plaintiff_name = plaintiff_name[:-3]
    else:
        plaintiff_name = plaintiff_name[:-2]
 
    if defendant_name.endswith('的法人'):
        defendant_name = defendant_name[:-3]
    else:
        defendant_name = defendant_name[:-2]

    plaintiff_company_info = get_company_info(plaintiff_name)
    defendant_company_info = get_company_info(defendant_name)
    plaintiff_lawfirm_info = get_lawfirm_info(plaintiff_lawfirm_name)
    defendant_lawfirm_info = get_lawfirm_info(defendant_lawfirm_name)

    data = { 
        "原告": plaintiff_company_info.get("法人代表"), 
        "原告性别": "", 
        "原告生日": "", 
        "原告民族": "", 
        "原告工作单位": plaintiff_company_info.get("公司名称"), 
        "原告地址": plaintiff_company_info.get("注册地址"), 
        "原告联系方式": plaintiff_company_info.get("联系电话"), 
        "原告委托诉讼代理人": plaintiff_lawfirm_info.get("律师事务所名称"), 
        "原告委托诉讼代理人联系方式": plaintiff_lawfirm_info.get("通讯电话"), 
        "被告": defendant_company_info.get("法人代表"), 
        "被告性别": "", 
        "被告生日": "", 
        "被告民族": "", 
        "被告工作单位": defendant_company_info.get("公司名称"), 
        "被告地址": defendant_company_info.get("注册地址"), 
        "被告联系方式": defendant_company_info.get("联系电话"), 
        "被告委托诉讼代理人": defendant_lawfirm_info.get("律师事务所名称"), 
        "被告委托诉讼代理人联系方式": defendant_lawfirm_info.get("通讯电话"), 
        "诉讼请求": cause, 
        "事实和理由": "", 
        "证据": "", 
        "法院名称": court_name, 
        "起诉日期": date 
    }

    url = f"{url_prefix}/get_citizens_sue_citizens"
    response = requests.post(url, json=data, headers=headers)
    text = response.text
    return text


@register_tool
def get_company_sue_company(
    plaintiff_name: Annotated[str, "原告公司名称"],
    defendant_name: Annotated[str, "被告公司名称"],
    cause: Annotated[str, "案由"],
    plaintiff_lawfirm_name: Annotated[str, "原告律师事务所名称"],
    defendant_lawfirm_name: Annotated[str, "被告律师事务所名称"],
    court_name: Annotated[str, "法院名称"],
    date: Annotated[str, "起诉时间"]
):
    """
    民事起诉状(公司起诉公司)

    Args:
        plaintiff_name (str): 原告公司名称
        defendant_name (str): 被告公司名称
        cause (str): 案由
        plaintiff_lawfirm_name (str): 原告律师事务所名称
        defendant_lawfirm_name (str): 被告律师事务所名称
        court_name (str): 法院名称
        date (str): 起诉时间

    Returns:
        诉讼状 (str)
    """
    # 法定代表人可能还要考虑如果不是上市公司的情况
    plaintiff_company_info = get_company_info(plaintiff_name)
    defendant_company_info = get_company_info(defendant_name)
    plaintiff_lawfirm_info = get_lawfirm_info(plaintiff_lawfirm_name)
    defendant_lawfirm_info = get_lawfirm_info(defendant_lawfirm_name)

    data = { 
        "原告": plaintiff_company_info.get("公司名称"), 
        "原告地址": plaintiff_company_info.get("注册地址"), 
        "原告法定代表人": plaintiff_company_info.get("法人代表"), 
        "原告联系方式": plaintiff_company_info.get("联系电话"), 
        "原告委托诉讼代理人": plaintiff_lawfirm_info.get("律师事务所名称"), 
        "原告委托诉讼代理人联系方式": plaintiff_lawfirm_info.get("通讯电话"), 
        "被告": defendant_company_info.get("公司名称"), 
        "被告地址": defendant_company_info.get("注册地址"), 
        "被告法定代表人": defendant_company_info.get("法人代表"), 
        "被告联系方式": defendant_company_info.get("联系电话"), 
        "被告委托诉讼代理人": defendant_lawfirm_info.get("律师事务所名称"), 
        "被告委托诉讼代理人联系方式": defendant_lawfirm_info.get("通讯电话"), 
        "诉讼请求": cause, 
        "事实和理由": "", 
        "证据": "", 
        "法院名称": court_name, 
        "起诉日期": date 
    }

    url = f"{url_prefix}/get_company_sue_company"
    response = requests.post(url, json=data, headers=headers)
    text = response.text
    return text


@register_tool
def get_company_sue_citizens(
    plaintiff_name: Annotated[str, "原告公司名称"],
    defendant_name: Annotated[str, "被告公司名称"],
    cause: Annotated[str, "案由"],
    plaintiff_lawfirm_name: Annotated[str, "原告律师事务所名称"],
    defendant_lawfirm_name: Annotated[str, "被告律师事务所名称"],
    court_name: Annotated[str, "法院名称"],
    date: Annotated[str, "起诉时间"]
):
    """
    民事起诉状(公司起诉公司)

    Args:
        plaintiff_name (str): 原告公司名称
        defendant_name (str): 被告公司名称
        cause (str): 案由
        plaintiff_lawfirm_name (str): 原告律师事务所名称
        defendant_lawfirm_name (str): 被告律师事务所名称
        court_name (str): 法院名称
        date (str): 起诉时间

    Returns:
        诉讼状 (str)
    """
    # 法定代表人可能还要考虑如果不是上市公司的情况
    if defendant_name.endswith('的法人'):
        defendant_name = defendant_name[:-3]
    else:
        defendant_name = defendant_name[:-2]

    plaintiff_company_info = get_company_info(plaintiff_name)
    defendant_company_info = get_company_info(defendant_name)
    plaintiff_lawfirm_info = get_lawfirm_info(plaintiff_lawfirm_name)
    defendant_lawfirm_info = get_lawfirm_info(defendant_lawfirm_name)

    data = { 
        "原告": plaintiff_company_info.get("公司名称"), 
        "原告地址": plaintiff_company_info.get("注册地址"), 
        "原告法定代表人": plaintiff_company_info.get("法人代表"), 
        "原告联系方式": plaintiff_company_info.get("联系电话"), 
        "原告委托诉讼代理人": plaintiff_lawfirm_info.get("律师事务所名称"), 
        "原告委托诉讼代理人联系方式": plaintiff_lawfirm_info.get("通讯电话"), 
        "被告": defendant_company_info.get("法人代表"), 
        "被告性别": "", 
        "被告生日": "", 
        "被告民族": "", 
        "被告工作单位": defendant_company_info.get("公司名称", ""), 
        "被告地址": defendant_company_info.get("注册地址", ""), 
        "被告联系方式": defendant_company_info.get("联系电话"), 
        "被告委托诉讼代理人": defendant_lawfirm_info.get("律师事务所名称"), 
        "被告委托诉讼代理人联系方式": defendant_lawfirm_info.get("通讯电话"), 
        "诉讼请求": cause, 
        "事实和理由": "", 
        "证据": "", 
        "法院名称": court_name, 
        "起诉日期": date 
    }

    url = f"{url_prefix}/get_company_sue_citizens"
    response = requests.post(url, json=data, headers=headers)
    text = response.text
    return text


@register_tool
def get_citizens_sue_company(
    plaintiff_name: Annotated[str, "原告公司名称"],
    defendant_name: Annotated[str, "被告公司名称"],
    cause: Annotated[str, "案由"],
    plaintiff_lawfirm_name: Annotated[str, "原告律师事务所名称"],
    defendant_lawfirm_name: Annotated[str, "被告律师事务所名称"],
    court_name: Annotated[str, "法院名称"],
    date: Annotated[str, "起诉时间"]
):
    """
    民事起诉状(公司起诉公司)

    Args:
        plaintiff_name (str): 原告公司名称
        defendant_name (str): 被告公司名称
        cause (str): 案由
        plaintiff_lawfirm_name (str): 原告律师事务所名称
        defendant_lawfirm_name (str): 被告律师事务所名称
        court_name (str): 法院名称
        date (str): 起诉时间

    Returns:
        诉讼状 (str)
    """
    # 法定代表人可能还要考虑如果不是上市公司的情况
    if plaintiff_name.endswith('的法人'):
        plaintiff_name = plaintiff_name[:-3]
    else:
        plaintiff_name = plaintiff_name[:-2]

    plaintiff_company_info = get_company_info(plaintiff_name)
    defendant_company_info = get_company_info(defendant_name)
    plaintiff_lawfirm_info = get_lawfirm_info(plaintiff_lawfirm_name)
    defendant_lawfirm_info = get_lawfirm_info(defendant_lawfirm_name)

    data = { 
        "原告": plaintiff_company_info.get("法人代表"), 
        "原告性别": "", 
        "原告生日": "", 
        "原告民族": "", 
        "原告工作单位": plaintiff_company_info.get("公司名称"), 
        "原告地址": plaintiff_company_info.get("公司名称"), 
        "原告联系方式": plaintiff_company_info.get("联系电话"), 
        "原告委托诉讼代理人": plaintiff_lawfirm_info.get("律师事务所名称"), 
        "原告委托诉讼代理人联系方式": plaintiff_lawfirm_info.get("通讯电话"), 
        "被告": defendant_company_info.get("公司名称"), 
        "被告地址": defendant_company_info.get("注册地址"), 
        "被告法定代表人": defendant_company_info.get("法人代表"), 
        "被告联系方式": defendant_company_info.get("联系电话"), 
        "被告委托诉讼代理人": defendant_lawfirm_info.get("律师事务所名称"), 
        "被告委托诉讼代理人联系方式": defendant_lawfirm_info.get("通讯电话"), 
        "诉讼请求": cause, 
        "事实和理由": "", 
        "证据": "", 
        "法院名称": court_name, 
        "起诉日期": date 
    }

    url = f"{url_prefix}/get_citizens_sue_company"
    response = requests.post(url, json=data, headers=headers)
    text = response.text
    return text


@register_tool
def is_empty(item):
    """
    检查返回值是否为空，返回 bool
    """
    if item is None:
        return True
    elif isinstance(item, (list, dict)):
        return len(item) == 0
    elif isinstance(item, str):
        return len(item.strip()) == 0
    else:
        return False


@register_tool
def save_dict_list_to_word(
    company_name,
    company_register_info,
    sub_company_info_list = [],
    legal_doc_list = [],
    xzgxf_info_list = [],
):
    """
    通过传入结构化信息，制作生成公司数据报告

    Args:
        company_name (str): 公司名称
        company_register_info (CompanyRegister): 工商信息
        sub_company_info_list (list[SubCompanyInfo]): 子公司信息 
        legal_doc_list (list[LegalDoc]): 裁判文书
        xzgxf_info_list (list[XzgxfInfo]): 限制高消费

    Returns:
        公司数据报告 docx 文件名称
    """
    if is_empty(company_name):
        raise ToolException(traceback='', ename='save_dict_list_to_word 参数错误', evalue='company_name 不能为空')
    if is_empty(company_register_info):
        raise ToolException(traceback='', ename='save_dict_list_to_word 参数错误', evalue='company_register_info 不能为空')
    if isinstance(company_register_info, dict):
        company_register_info = [company_register_info]

    url = f"{url_prefix}/save_dict_list_to_word"
    dict_list = {
        "工商信息": company_register_info,
        "子公司信息": sub_company_info_list,
        "裁判文书": legal_doc_list,
        "限制高消费": xzgxf_info_list,
    }
    data = {
        "company_name": company_name, 
        "dict_list": json.dumps(dict_list, ensure_ascii=False),
    }

    rsp = requests.post(url, json=data, headers=headers)
    return rsp.text


def generate_tools_desc(tools):
    tools_desc = ""

    for tool in tools:
        tools_desc += f"{registered_tools_map[tool].__name__} 工具\n"
        tools_desc += f"{registered_tools_map[tool].__doc__}\n"
        tools_desc += "-------------------------------------\n\n"

    return tools_desc


if __name__ == '__main__':
    test_cases = [
        "(22002200)皖05民终1584号",
    ]
    for case in test_cases:
        case_num = preprocess_case_num(case)
        case_num = correct_case_num(case_num)
