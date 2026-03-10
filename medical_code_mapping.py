"""
Medical code mapping.

Translates SNOMED, LOINC, CPT4, and RxNorm codes to human-readable names.
- RxNorm drug names: loaded from rxnorm_cache.json (NLM RxNorm REST API)
- RxNorm Extension: loaded from rxnorm_extension_cache.json (OMOP concept table)
- SNOMED terms: loaded from snomed_cache.json (UMLS MRCONSO.RRF, 414K entries)
"""

import json
import os

_HERE = os.path.dirname(os.path.abspath(__file__))
_DATA_DIR = os.path.join(_HERE, "data")

def _load_json_cache(filename: str) -> dict:
    path = os.path.join(_DATA_DIR, filename)
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return {}

_RXNORM_CACHE: dict = _load_json_cache("rxnorm_cache.json")
_RXNORM_EXT_CACHE: dict = _load_json_cache("rxnorm_extension_cache.json")
_SNOMED_CACHE: dict = _load_json_cache("snomed_cache.json")

# SNOMED编码映射（常见疾病诊断）
SNOMED_CODES = {
    '59621000': '原发性高血压 (Essential hypertension)',
    '38341003': '高血压 (Hypertension)',
    '194783001': '继发性高血压 (Secondary hypertension)',
    '21522001': '腹痛 (Abdominal pain)',
    '29738008': '黄疸 (Jaundice)',
    '37796009': '移植肾 (Transplanted kidney)',
    '78275009': '阻塞性睡眠呼吸暂停 (Obstructive sleep apnea)',
    '40930008': '甲状腺功能减退 (Hypothyroidism)',
    '74627003': '糖尿病并发症 (Diabetic complication)',
    '87557004': '2型糖尿病 (Type 2 diabetes mellitus)',
    '90560007': '痛风 (Gout)',
    '279039007': '低钾血症 (Hypokalemia)',
    '786457000': '急性呼吸道感染 (Acute respiratory infection)',
    '44054006': '2型糖尿病 (Type 2 diabetes mellitus)',
    '15777000': '糖尿病前期 (Prediabetes)',
    '271737000': '贫血 (Anemia)',
    '13645005': '慢性阻塞性肺病 (COPD)',
    '49436004': '房颤 (Atrial fibrillation)',
    '53741008': '冠心病 (Coronary artery disease)',
    '84114007': '心力衰竭 (Heart failure)',
    '73211009': '糖尿病 (Diabetes mellitus)',
    '195967001': '哮喘 (Asthma)',
    '399211009': '慢性肾病 (Chronic kidney disease)',
    '431855005': '慢性肾病3期 (CKD stage 3)',
    '46635009': '1型糖尿病 (Type 1 diabetes mellitus)',
}

# LOINC编码映射（实验室检查）
LOINC_CODES = {
    '788-0': '红细胞分布宽度 (RBC distribution width)',
    '5778-6': '血清肌酐 (Creatinine)',
    '24323-8': '综合代谢检查 (Comprehensive metabolic panel)',
    '32554-8': '血清钾 (Potassium)',
    '65818-7': '血红蛋白A1c (Hemoglobin A1c)',
    '1975-2': '血清胆红素 (Bilirubin)',
    '2160-0': '血清肌酐 (Creatinine)',
    '38214-3': '肾小球滤过率 (GFR)',
    '1751-7': '血清白蛋白 (Albumin)',
    '57698-3': '脂质代谢检查 (Lipid panel)',
    '49229-8': '血氧饱和度 (Oxygen saturation)',
    '9279-1': '呼吸频率 (Respiratory rate)',
    '2823-3': '血清钾 (Potassium)',
    '8478-0': '平均血压 (Mean blood pressure)',
    '33037-3': '血糖 (Glucose)',
    '718-7': '血红蛋白 (Hemoglobin)',
    '35088-4': '肾功能检查 (Renal function panel)',
    '2085-9': '血清胆固醇-HDL (HDL cholesterol)',
    '2089-1': '血清胆固醇-LDL (LDL cholesterol)',
    '2571-8': '血清甘油三酯 (Triglycerides)',
    '6690-2': '白细胞计数 (WBC count)',
    '777-3': '血小板计数 (Platelet count)',
    '4544-3': '血细胞比容 (Hematocrit)',
}

# CPT4编码映射（医疗操作/检查）
CPT4_CODES = {
    '80053': '综合代谢检查 (Comprehensive metabolic panel)',
    '84439': '甲状腺功能检查 (Thyroid function test)',
    '85027': '全血细胞计数 (Complete blood count)',
    '84443': '促甲状腺激素 (TSH)',
    '82947': '血糖检查 (Glucose test)',
    '80061': '脂质代谢检查 (Lipid panel)',
    '83036': '糖化血红蛋白 (Hemoglobin A1c)',
}

# RxNorm编码映射（常见降压药）
RXNORM_CODES = {
    '197391': '氨氯地平 5mg (Amlodipine 5mg)',
    '197527': '阿司匹林 81mg (Aspirin 81mg)',
    '197625': '阿托伐他汀 20mg (Atorvastatin 20mg)',
    '197901': '赖诺普利 10mg (Lisinopril 10mg)',
    '312087': '氢氯噻嗪 25mg (Hydrochlorothiazide 25mg)',
    '314200': '胰岛素 (Insulin)',
    '860771': '二甲双胍 500mg (Metformin 500mg)',
    '483448': '辛伐他汀 20mg (Simvastatin 20mg)',
    '308136': '氯沙坦 50mg (Losartan 50mg)',
    '866427': '美托洛尔 25mg (Metoprolol 25mg)',
    '197884': '赖诺普利 20mg (Lisinopril 20mg)',
    '308962': '缬沙坦 80mg (Valsartan 80mg)',
}

def get_code_description(code_with_system):
    """
    获取编码的中文描述

    Args:
        code_with_system: 格式如 "SNOMED/59621000" 或 "LOINC/788-0"

    Returns:
        中文描述，如果找不到则返回原编码
    """
    if not code_with_system or not isinstance(code_with_system, str):
        return str(code_with_system)

    parts = code_with_system.split('/')
    if len(parts) != 2:
        return code_with_system

    system, code = parts

    if system == 'SNOMED':
        name = _SNOMED_CACHE.get(code) or SNOMED_CODES.get(code)
        return name if name else code_with_system
    elif system == 'LOINC':
        return LOINC_CODES.get(code, code_with_system)
    elif system == 'CPT4':
        return CPT4_CODES.get(code, code_with_system)
    elif system == 'RxNorm':
        name = _RXNORM_CACHE.get(code) or RXNORM_CODES.get(code)
        return name if name else code_with_system
    else:
        return code_with_system


def get_medication_name(rxnorm_code):
    """
    Return the drug name for an RxNorm code string like "RxNorm/197391"
    or "RxNorm Extension/OMOP994671".

    Looks up:
    1. RxNorm Extension cache (from OMOP concept table)
    2. RxNorm cache (from NLM RxNorm API)
    3. Hand-coded RXNORM_CODES table

    Returns the original code string if no match is found.
    """
    if not rxnorm_code or not isinstance(rxnorm_code, str):
        return str(rxnorm_code)

    parts = rxnorm_code.split("/")

    # Handle RxNorm Extension/OMOP{concept_id}
    if len(parts) == 2 and parts[0] == "RxNorm Extension":
        concept_id = parts[1].replace("OMOP", "")
        name = _RXNORM_EXT_CACHE.get(concept_id)
        if name:
            return name

    # Handle RxNorm/{code}
    if len(parts) == 2 and parts[0] == "RxNorm":
        code = parts[1]
        name = _RXNORM_CACHE.get(code) or RXNORM_CODES.get(code)
        if name:
            return name

    return rxnorm_code


# 导出函数
__all__ = ['get_code_description', 'get_medication_name',
           'SNOMED_CODES', 'LOINC_CODES', 'CPT4_CODES', 'RXNORM_CODES']
