from enum import Enum
from dataclasses import dataclass

from pydantic import BaseModel


class CompanyInfo(BaseModel):

    公司名称: str
    公司简称: str
    英文名称: str
    关联证券: str
    公司代码: str
    曾用简称: str
    所属市场: str
    所属行业: str
    成立日期: str
    上市日期: str
    法人代表: str
    总经理: str
    董秘: str
    邮政编码: str
    注册地址: str
    办公地址: str
    联系电话: str
    传真: str
    官方网址: str
    电子邮箱: str
    入选指数: str
    主营业务: str
    经营范围: str
    机构简介: str
    每股面值: str
    首发价格: str
    首发募资净额: str
    首发主承销商: str


class CompanyRegister(BaseModel):

    公司名称: str
    登记状态: str
    统一社会信用代码: str
    法定代表人: str
    注册资本: str
    成立日期: str
    企业地址: str
    联系电话: str
    联系邮箱: str
    注册号: str
    组织机构代码: str
    参保人数: str
    行业一级: str
    行业二级: str
    行业三级: str
    曾用名: str
    企业简介: str
    经营范围: str


class SubCompanyInfo(BaseModel):

    关联上市公司全称: str
    上市公司关系: str
    上市公司参股比例: str
    上市公司投资金额: str
    公司名称: str


class LegalDoc(BaseModel):

    关联公司: str
    标题: str
    案号: str
    文书类型: str
    原告: str
    被告: str
    原告律师事务所: str
    被告律师事务所: str
    案由: str
    涉案金额: str
    判决结果: str
    日期: str
    文件名: str


class CourtInfo(BaseModel):

    法院名称: str
    法院负责人: str
    成立日期: str
    法院地址: str
    法院联系电话: str
    法院官网: str


class CourtCode(BaseModel):

    法院名称: str
    行政级别: str
    法院级别: str
    法院代字: str
    区划代码: str
    级别: str


class LawfirmInfo(BaseModel):

    律师事务所名称: str
    律师事务所唯一编码: str
    律师事务所负责人: str
    事务所注册资本: str
    事务所成立日期: str
    律师事务所地址: str
    通讯电话: str
    通讯邮箱: str
    律所登记机关: str


class LawfirmLog(BaseModel):

    律师事务所名称: str
    业务量排名: str
    服务已上市公司: str
    报告期间所服务上市公司违规事件: str
    报告期所服务上市公司接受立案调查: str


class AddrInfo(BaseModel):

    地址: str
    省份: str
    城市: str
    区县: str


class AddrCode(BaseModel):

    省份: str
    城市: str
    城市区划代码: str
    区县: str
    区县区划代码: str


class TempInfo(BaseModel):

    日期: str
    省份: str
    城市: str
    天气: str
    最高温度: str
    最低温度: str
    湿度: str


class LegalAbstract(BaseModel):

    文件名: str
    案号: str
    文本摘要: str


class XzgxfInfo(BaseModel):

    限制高消费企业名称: str
    案号: str
    法定代表人: str
    申请人: str
    涉案金额: str
    执行法院: str
    立案日期: str
    限高发布日期: str


def build_enum_class(dataclass, exclude_enums=[]):
    exclude_enums = []
    keys = [key for key in dataclass.__fields__.keys() if key not in exclude_enums]
    return Enum(dataclass.__name__ + "Enum", dict(zip(keys, keys)))


# TODO 这里 exclude_enums 可能要需要琢磨一下
CompanyInfoEnum = build_enum_class(CompanyInfo, exclude_enums=["公司名称"])
CompanyRegisterEnum = build_enum_class(CompanyRegister, exclude_enums=["公司名称"])
SubCompanyInfoEnum = build_enum_class(SubCompanyInfo, exclude_enums=["公司名称"])   
LegalDocEnum = build_enum_class(LegalDoc, exclude_enums=["案号"])
CourtInfoEnum = build_enum_class(CourtInfo, exclude_enums=["法院名称"])
CourtCodeEnum = build_enum_class(CourtCode, exclude_enums=["法院名称"])
LawfirmInfoEnum = build_enum_class(LawfirmInfo, exclude_enums=["律师事务所名称"])   
LawfirmLogEnum = build_enum_class(LawfirmLog, exclude_enums=["律师事务所名称"])
AddrInfoEnum = build_enum_class(AddrInfo, exclude_enums=["省份", "城市", "区县"])
AddrCodeEnum = build_enum_class(AddrCode, exclude_enums=["省份", "城市", "区县"])
TempInfoEnum = build_enum_class(TempInfo, exclude_enums=["省份", "城市"])   
LegalAbstractEnum = build_enum_class(LegalAbstract, exclude_enums=["案号"])
XzgxfInfoEnum = build_enum_class(XzgxfInfo, exclude_enums=["案号"])


def build_enum_list(enum_class): return [enum.value for enum in enum_class]


enum_list_map = {
    "CompanyInfo": build_enum_list(CompanyInfoEnum),
    "CompanyRegister": build_enum_list(CompanyRegisterEnum),
    "SubCompanyInfo": build_enum_list(SubCompanyInfoEnum),
    "LegalDoc": build_enum_list(LegalDocEnum),
    "CourtInfo": build_enum_list(CourtInfoEnum),
    "CourtCode": build_enum_list(CourtCodeEnum),
    "LawfirmInfo": build_enum_list(LawfirmInfoEnum),
    "LawfirmLog": build_enum_list(LawfirmLogEnum),
    "AddrInfo": build_enum_list(AddrInfoEnum),
    "AddrCode": build_enum_list(AddrCodeEnum),
    "TempInfo": build_enum_list(TempInfoEnum),
    "LegalAbstract": build_enum_list(LegalAbstractEnum),
    "XzgxfInfo": build_enum_list(XzgxfInfoEnum),
}

enum_class_zh = {
    "CompanyInfo": "上市公司基本信息表",
    "CompanyRegister": "公司工商照面信息表",
    "SubCompanyInfo": "上市公司投资子公司关联信息表",
    "LegalDoc": "法律文书信息表",
    "CourtInfo": "法院基础信息表（名录）",
    "CourtCode": "法院地址信息、代字表",
    "LawfirmInfo": "律师事务所信息表（名录）",
    "LawfirmLog": "律师事务所业务数据表",
    "AddrInfo": "通用地址省市区信息表",
    "AddrCode": "通用地址编码表",
    "TempInfo": "天气数据表",
    "LegalAbstract": "法律文书摘要表",
    "XzgxfInfo": "限制高消费数据表",
}


def generate_database_schema(tables):
    schema = ""
    
    for table in tables:
        schema += f"{table}有下列字段：\n"
        schema += f"{enum_list_map[table]}\n"
        schema += "-------------------------------------\n\n"
    
    return f'{schema}'


ALL_DATABASE_SCHEMA = generate_database_schema([
    'CompanyInfo',
    'CompanyRegister',
    'SubCompanyInfo',
    'LegalDoc',
    'CourtInfo',
    'CourtCode',
    'LawfirmInfo',
    'LawfirmLog',
    'AddrInfo',
    'AddrCode',
    'TempInfo',
    'LegalAbstract',
    'XzgxfInfo',
])


@dataclass
class NamedEntityDef:
    name: str
    desc: str
    example: str


class NamedEntityType(Enum):
    CASE_NUM = NamedEntityDef(
        name="案号",
        desc="法院或其他司法机关给予案件的唯一识别编号，通常包含年份、案件类型代码和序号等信息。",
        example=""
    )
    LAWFIRM_NAME = NamedEntityDef(
        name="律师事务所名称",
        desc="提供法律服务的专业机构的正式名称。",
        example=""
    )
    COMPANY_FULL_NAME = NamedEntityDef(
        name="公司名称",
        desc="企业或组织在工商登记中使用的完整法定名称。",
        example=""
    )
    COMPANY_ABBR_NAME = NamedEntityDef(
        name="公司简称",
        desc="公司名称的简化形式,通常用于日常交流或媒体报道。",
        example=""
    )
    COMPANY_CODE = NamedEntityDef(
        name="公司代码",
        desc="用于识别上市公司的唯一代码，通常由数字或字母组成。",
        example=""
    )
    COMPANY_UNIFIED_SOCIAL_CREDIT_CODE = NamedEntityDef(
        name="统一社会信用代码",
        desc="中国大陆地区企业、事业单位和其他组织的唯一身份代码,由18位阿拉伯数字或大写英文字母组成。",
        example=""
    )
    COURT_NAME = NamedEntityDef(
        name="法院名称",
        desc="司法机构的官方名称，通常包含行政区划和级别信息。",
        example=""
    )
    LOCATION_NAME = NamedEntityDef(
        name="地名",
        desc="指特定地理位置的名称,可以是国家、省份、城市、区县、街道等。",
        example=""
    )

    @property
    def name(self):
        return self.value.name

    @property
    def desc(self):
        return self.value.desc

    @property
    def example(self):
        return self.value.example
