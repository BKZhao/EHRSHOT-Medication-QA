# EHRSHOT 用药管理QA数据集生成 — 技术报告

---

## 目录

1. [项目概述](#1-项目概述)
2. [数据来源与结构](#2-数据来源与结构)
3. [Step 1：筛选内科住院患者](#3-step-1筛选内科住院患者)
4. [Step 2：筛选QA候选visits](#4-step-2筛选qa候选visits)
5. [Step 3：生成QA题目](#5-step-3生成qa题目)
6. [QA质量分析](#6-qa质量分析)
7. [工具模块说明](#7-工具模块说明)
8. [附录：工具数据的获取方式](#8-附录工具数据的获取方式)

---

## 1. 项目概述

本项目基于 Stanford EHRSHOT 数据集，构建一个用于评估医疗AI**出院用药决策能力**的QA数据集。

**任务定义**：给定患者的入院信息（既往病史、入院诊断、生命体征、实验室检查、入院前用药），预测该患者出院后应开具的药物列表。

**核心设计原则**：
- Ground Truth（GT）来自真实电子病历中的出院后用药记录，而非人工标注
- 只考虑口服药物（排除住院期间的静脉注射、麻醉药等）
- 每个QA题目包含 ATC 药物分类信息，便于按药理类别评估模型表现

---

## 2. 数据来源与结构

### 2.1 EHRSHOT 主表

路径：`/data/ehr/EHRSHOT/EHRSHOT_ASSETS/data/ehrshot.csv`

EHRSHOT 是 Stanford 发布的去标识化 EHR 数据集，包含 6,712 名患者的纵向医疗记录，共 4,166 万条记录。所有数据以 OMOP CDM 标准格式存储，每行代表一个医疗事件：

| 字段 | 说明 |
|------|------|
| `patient_id` | 患者唯一标识 |
| `start` | 事件发生时间 |
| `code` | 标准化编码（如 `SNOMED/59621000`、`RxNorm/197391`） |
| `value` | 数值（用于 measurement） |
| `unit` | 单位 |
| `visit_id` | 关联的住院ID（部分记录为空） |
| `omop_table` | 数据类型：`condition_occurrence / measurement / drug_exposure / person` |

### 2.2 本地导出表（`data/` 目录）

EHRSHOT 主表缺少部分字段（如 `visit_occurrence_id`、`condition_type_concept_id`），需要从原始数据库单独导出：

| 文件 | 来源 | 关键字段 |
|------|------|----------|
| `visit_occurrence.csv` | OMOP visit_occurrence 表 | `visit_occurrence_id`, `care_site_id`, `visit_start_date`, `visit_end_date` |
| `condition_occurrence.csv` | OMOP condition_occurrence 表 | `visit_occurrence_id`, `condition_concept_id`, `condition_type_concept_id` |
| `drug_exposure.csv` | OMOP drug_exposure 表 | `person_id`, `drug_concept_id`, `drug_exposure_start_DATE` |
| `concept.csv` | OMOP concept 表 | `concept_id`, `concept_name`（用于 concept_id → 名称映射） |
| `care_site.csv` | OMOP care_site 表 | `care_site_id`, `care_site_name` |
| `rxnorm_to_atc.csv.csv` | 外部下载 | RxNorm → ATC 四级分类映射 |

---

## 3. Step 1：筛选内科住院患者

**脚本**：`step1_filter_internal_medicine.ipynb`

### 3.1 筛选逻辑

从 `data/visit_occurrence.csv` 出发，筛选满足以下条件的住院记录：

1. **科室匹配**：`care_site_name` 包含内科相关关键词
   ```
   GASTROENTEROLOGY, CARDIOLOGY, NEPHROLOGY, PULMONOLOGY,
   ENDOCRINOLOGY, HEMATOLOGY, RHEUMATOLOGY, HEPATOLOGY,
   INTERNAL MEDICINE, GENERAL MEDICINE
   ```

2. **住院时长 < 2 天**：`duration_days = visit_end_date - visit_start_date < 2`

### 3.2 筛选结果

- 初始 visits：全部住院记录
- 筛选后：**1,405 条 visits，714 名患者**

**输出**：`output/internal_medicine_2days_visits.csv`

---

## 4. Step 2：筛选QA候选visits

**脚本**：`step2_filter_qa_candidates.ipynb`

### 4.1 时间窗口定义

```
                    入院前30天          入院日          出院日          出院后7天
                        |               |               |               |
时间轴  ────────────────●───────────────●───────────────●───────────────●────────▶
                        ↑               ↑               ↑               ↑
                   pre_window_start  admission      discharge      post_window_end

PRE-ADMISSION WINDOW:  [入院前30天, 入院日)   → 用于识别"入院前用药"
POST-DISCHARGE WINDOW: (出院日, 出院后7天]    → 用于识别"出院后用药"（GT）
```

### 4.2 GT 用药定义

```
持续用药 (Continued) = 入院前30天口服药 ∩ 出院后7天口服药
新增用药 (New)       = 出院后7天口服药 - 入院前30天口服药
GT                   = 持续用药 ∪ 新增用药
```

**口服药物判断**：药物名称包含以下剂型关键词：
```
oral tablet, oral capsule, oral solution, oral suspension,
chewable tablet, disintegrating oral tablet, extended release oral,
delayed release oral, oral powder
```

**排除药物**（麻醉/化疗/免疫抑制剂）：
```
lidocaine, propofol, ketamine, sevoflurane, fentanyl,
rocuronium, vecuronium, succinylcholine, midazolam,
cisplatin, carboplatin, doxorubicin, paclitaxel,
tacrolimus, cyclosporine, sirolimus, mycophenolate
```

### 4.3 五步筛选流程

```
初始 visits: 1,405
      │
      ▼ 筛选条件1：入院前有历史诊断记录
      │  （EHRSHOT condition_occurrence 中有 start < admission_date 的记录）
      │
      ▼ 筛选条件2：排除肿瘤/移植/手术
      │  检查范围：前病史 + 入院诊断（双重检查）
      │  排除关键词：malignant neoplasm, carcinoma, cancer,
      │              transplanted, transplantation,
      │              complication of surgical procedure, postoperative, ...
      │
      ▼ 筛选条件3：入院后24h内有 Vitals/Labs 记录
      │  时间窗口：[admission_date, admission_date + 24h]
      │
      ▼ 筛选条件4：GT 用药数量 1–10 种
      │  过少（0种）：无法构成有意义的QA
      │  过多（>10种）：题目过于复杂，可能是多病共患的复杂病例
      │
      ▼ 筛选条件5：年龄、性别信息完整
      │  从 EHRSHOT person 表提取：
      │  - Gender/M → Male, Gender/F → Female
      │  - SNOMED/3950001（birth date）→ 计算年龄
      │
      ▼
最终候选: 236 条 visits
```

### 4.4 性能优化

Step 2 需要对每个 visit 扫描数百万条记录，原始实现极慢。优化方案：

1. **预解析日期**：在循环外一次性将所有日期列转为 `datetime` 类型，避免循环内重复调用 `pd.to_datetime()`
2. **建立 patient_id 索引**：用 `groupby` 将 conditions/measures/drugs 按 `patient_id` 分组为字典，每次查询从 O(N) 降为 O(1)
3. **建立 visit_id 索引**：`condition_occurrence` 按 `visit_occurrence_id` 分组，快速查找入院诊断

```python
# 预处理示例
conditions['start_dt'] = pd.to_datetime(conditions['start'], errors='coerce')
conditions_by_patient = {pid: grp for pid, grp in conditions.groupby('patient_id')}
```

**输出**：`output/qa_candidate/qa_candidate_visits.csv`（236 条 visits）

---

## 5. Step 3：生成QA题目

**脚本**：`step3_generate_qa.py`

### 5.1 题干构建

对每个候选 visit，按以下顺序构建 `clinical_note`：

#### (1) 患者基本信息
```
PATIENT: {age}-year-old {gender}
Department: {care_site_name}
Admission: [REDACTED]
Discharge: [REDACTED]
```
入院/出院日期用 `[REDACTED]` 替换，防止模型直接查找日期对应的用药记录。

#### (2) PRE-ADMISSION PROBLEM LIST
来源：EHRSHOT `condition_occurrence` 表，取 `start < admission_date` 的所有诊断。
- 通过 `medical_code_mapping.get_code_description()` 将 SNOMED 代码翻译为英文名称
- 去重（同一诊断只显示一次）
- 过滤掉无法解析的原始代码（以 `SNOMED/`、`ICD` 开头的未命中条目）

#### (3) ADMISSION DIAGNOSIS
来源：`data/condition_occurrence.csv`，通过 `visit_occurrence_id` 精确匹配本次住院的诊断记录。
- 通过 `concept_map`（concept_id → concept_name）翻译诊断名称

> **注**：Stanford EHRSHOT 的 condition_occurrence 主要为 billing diagnosis（`condition_type_concept_id = 32019`），与 Problem List 存在重叠是正常的临床现象（慢性病患者的既往史会在每次住院时重新记录）。

#### (4) ADMISSION VITALS
来源：EHRSHOT `measurement` 表，时间窗口：`[admission_date, admission_date + 24h]`

| LOINC 代码 | 指标 | 默认单位（unit 为空时） |
|------------|------|------------------------|
| LOINC/8480-6 | Systolic blood pressure | mmHg |
| LOINC/8462-4 | Diastolic blood pressure | mmHg |
| LOINC/8867-4 | Pulse rate | bpm |
| LOINC/9279-1 | Respiratory rate | bpm |
| LOINC/8310-5 | Body temperature | F（EHRSHOT 中 unit=NaN 的体温值域为 96–100，为华氏度） |
| LOINC/29463-7 | Body weight | ounces |
| LOINC/8302-2 | Body height | in |

单位规范化：`[in_us]` → `in`，`deg C` → `°C`，`deg F` → `F`

#### (5) ADMISSION LABS
来源：同上，排除 vitals LOINC 代码后的其余 measurement 记录。

过滤规则：
- 数值为 0 的条目（通常是缺失值的占位符）
- 无单位的数值型条目（如 `Renal function panel: 15.00`，无临床解读意义）
- 无法解析的原始代码

#### (6) CURRENT MEDICATIONS
来源：EHRSHOT `drug_exposure` 表，时间窗口：`[admission_date - 30天, admission_date)`

每条药物附加 ATC 分类信息：
```
- furosemide 20 MG Oral Tablet  [ATC: C03CA - Sulfonamides, plain]
```

### 5.2 答案构建

GT 用药列表，每条包含：
- 药物通用名（截断到第一个数字前，去掉剂量和剂型）
- ATC 第4级分类代码和名称
- 状态标签：`[Continued]` 或 `[New]`

```
Medication Orders:
1. lactulose  [ATC: A06AD - Osmotically acting laxatives]  [New]
2. furosemide  [ATC: C03CA - Sulfonamides, plain]  [Continued]
```

### 5.3 ATC 映射

ATC（Anatomical Therapeutic Chemical）分类系统将药物按解剖部位和治疗用途分为4级：

```
A        消化道及代谢（Alimentary tract and metabolism）
└── A06      泻药（Laxatives）
    └── A06A     泻药
        └── A06AD    渗透性泻药（Osmotically acting laxatives）
                     ↑ 第4级，最细粒度，用于QA标注
```

映射来源：`data/rxnorm_to_atc.csv.csv`（25,356 条 RxNorm → ATC 映射）

查找逻辑：从药物的 RxNorm 代码中提取 `rxcui`，在映射表中查找对应的 ATC 信息。

---

## 6. QA质量分析

### 6.1 当前测试集（5条）统计

| QA | 患者 | 科室 | 年龄/性别 | GT用药 | 续开 | 新开 | ATC覆盖 |
|----|------|------|-----------|--------|------|------|---------|
| QA1 | 115968266 | GASTROENTEROLOGY | 46M | 6 | 1 | 5 | 100% |
| QA2 | 115972686 | GASTROENTEROLOGY | 67M | 15 | 8 | 7 | 100% |
| QA3 | 115969732 | GASTROENTEROLOGY | 60M | 11 | 7 | 4 | 100% |
| QA4 | 115969919 | GASTROENTEROLOGY | 28F | 5 | 5 | 0 | 100% |
| QA5 | 115972081 | GASTROENTEROLOGY | 66F | 9 | 8 | 1 | 100% |

- 平均 GT 用药：9.2 种
- ATC 覆盖率：100%（46/46）

### 6.2 已知局限性

1. **科室多样性不足**：当前5条全来自 GASTROENTEROLOGY，因为候选排序给消化科加了优先级。扩大规模后会覆盖更多科室。

2. **GT 噪音**：GT 基于真实出院后用药记录，部分药物的临床合理性存疑（如胆管炎患者出院后开了 metformin）。这是数据驱动方法的固有局限，无法从代码层面完全过滤。

3. **Problem List 模糊诊断**：部分诊断名称过于模糊（如 `Musculoskeletal finding`、`Illness`），对 LLM 的临床推理帮助有限。

---

## 7. 工具模块说明

### 7.1 `medical_code_mapping.py`

EHRSHOT 中所有医学事件均以标准化编码存储，无法直接阅读。该模块提供两个核心函数：

```python
get_code_description("SNOMED/59621000")
# → "Essential hypertension"

get_medication_name("RxNorm/197391")
# → "amlodipine 5 MG Oral Tablet"

get_medication_name("RxNorm Extension/OMOP994671")
# → "metformin hydrochloride 500 MG Oral Tablet"
```

**查找优先级**：
```
SNOMED 代码  →  snomed_cache.json（41万条）→ 内置 SNOMED_CODES 字典 → 返回原始代码
RxNorm 代码  →  rxnorm_cache.json（5,082条）→ 内置 RXNORM_CODES 字典 → 返回原始代码
RxNorm Ext   →  rxnorm_extension_cache.json（214万条）→ 返回原始代码
LOINC 代码   →  内置 LOINC_CODES 字典 → 返回原始代码
```

---

## 8. 附录：工具数据的获取方式

### 8.1 `rxnorm_to_atc.csv.csv`

**来源**：从公开的 RxNorm-ATC 映射数据库下载，包含 25,356 条 RxNorm → ATC 四级分类的映射关系。

**文件格式**（无表头，BOM 编码）：
```
rxcui, drug_name, atc1_code, atc1_name, atc2_code, atc2_name, atc3_code, atc3_name, atc4_code, atc4_name
```

**读取注意事项**：
```python
atc_df = pd.read_csv(RXNORM_ATC_CSV, header=None,
    names=['rxcui','drug_name','atc1_code','atc1_name','atc2_code','atc2_name',
           'atc3_code','atc3_name','atc4_code','atc4_name'],
    dtype={'rxcui': str}, encoding='utf-8-sig')  # BOM 编码
atc_df['rxcui'] = atc_df['rxcui'].str.strip('"')  # 去除引号
```

### 8.2 `rxnorm_cache.json`

**来源**：通过 NLM RxNorm REST API 批量查询生成。

**API 端点**：
```
https://rxnav.nlm.nih.gov/REST/rxcui/{rxcui}/properties.json
```

**生成方式**：遍历 EHRSHOT 中所有 `RxNorm/` 前缀的药物代码，提取 rxcui，批量请求 API，将结果缓存为 `{rxcui: drug_name}` 字典。

**内容**：5,082 条标准 RxNorm 药物代码 → 药物名称映射。

### 8.3 `rxnorm_extension_cache.json`

**来源**：从 OMOP `concept` 表直接提取。

EHRSHOT 中大量药物使用 `RxNorm Extension/OMOP{concept_id}` 格式的代码，这些是 OMOP 扩展的非标准 RxNorm 代码，无法通过 NLM API 查询。

**生成方式**：
```python
# 从 concept 表提取所有 RxNorm Extension 条目
concept_df = pd.read_csv('data/concept.csv')
rxnorm_ext = concept_df[concept_df['vocabulary_id'] == 'RxNorm Extension']
cache = dict(zip(rxnorm_ext['concept_id'].astype(str), rxnorm_ext['concept_name']))
```

**内容**：214 万条 OMOP concept_id → 药物名称映射。

### 8.4 `snomed_cache.json`

**来源**：从 UMLS（Unified Medical Language System）的 `MRCONSO.RRF` 文件提取。

UMLS 需要申请账号后下载（免费，需签署使用协议）：https://www.nlm.nih.gov/research/umls/

**生成方式**：
```python
# 从 MRCONSO.RRF 提取 SNOMED CT 英文术语
with open('MRCONSO.RRF') as f:
    for line in f:
        fields = line.strip().split('|')
        sab = fields[11]   # 来源词汇表
        lang = fields[1]   # 语言
        cui = fields[0]    # 概念唯一标识
        term = fields[14]  # 术语名称
        code = fields[13]  # 代码
        if sab == 'SNOMEDCT_US' and lang == 'ENG':
            cache[code] = term
```

**内容**：41 万条 SNOMED 代码 → 英文诊断名称映射。
