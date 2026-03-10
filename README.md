# EHRSHOT 用药管理QA数据集生成

从 EHRSHOT 数据集中筛选内科住院患者，生成用于评估医疗AI用药决策能力的QA数据集。

---

## 项目结构

```
ehrshot_analysis/
│
├── data/                              # 所有数据文件
│   ├── visit_occurrence.csv           # 住院记录（含科室、入出院时间）
│   ├── condition_occurrence.csv       # 诊断记录（含 visit_occurrence_id）
│   ├── drug_exposure.csv              # 用药记录
│   ├── concept.csv                    # OMOP concept 映射表（concept_id → 名称）
│   ├── care_site.csv                  # 科室信息
│   ├── rxnorm_to_atc.csv.csv          # RxNorm → ATC 分类映射（25,356条）
│   ├── rxnorm_cache.json              # 缓存：RxNorm代码 → 药物名（5,082条）
│   ├── rxnorm_extension_cache.json    # 缓存：OMOP concept_id → 药物名（214万条）
│   └── snomed_cache.json              # 缓存：SNOMED代码 → 诊断名（41万条）
│
├── output/
│   ├── internal_medicine_2days_visits.csv   # Step1输出：内科≤2天住院（1,405条）
│   ├── qa_candidate/
│   │   └── qa_candidate_visits.csv          # Step2输出：QA候选visits（236条）
│   └── QA/                                  # Step3输出：最终QA数据集
│       ├── qa_output_with_atc.json
│       └── qa_output_with_atc.csv
│
├── step1_filter_internal_medicine.ipynb     # Step1：筛选内科≤2天住院患者
├── step2_filter_qa_candidates.ipynb         # Step2：进一步筛选QA候选visits
├── step3_generate_qa.py                     # Step3：生成QA（主脚本）
├── medical_code_mapping.py                  # 工具：医学代码 → 可读名称
└── README.md
```

---

## 数据来源

- **EHRSHOT 主表**：`/data/ehr/EHRSHOT/EHRSHOT_ASSETS/data/ehrshot.csv`（4,166万条）
  - OMOP 标准格式，字段：`patient_id, start, end, code, value, unit, visit_id, omop_table`
  - `omop_table` 区分：`condition_occurrence / measurement / drug_exposure / person`
- **本地导出表**（`data/` 目录）：从原始数据库单独导出，包含 EHRSHOT 主表中缺失的字段（如 `visit_occurrence_id`、`condition_type_concept_id`）

---

## 流程说明

### Step 1 — 筛选内科住院患者

**脚本**：`step1_filter_internal_medicine.ipynb`

**筛选逻辑**：
1. 通过 `care_site_name` 匹配内科相关科室（GASTROENTEROLOGY、CARDIOLOGY、NEPHROLOGY 等）
2. 住院时长 ≤ 2 天

**输出**：`output/internal_medicine_2days_visits.csv`（1,405 条 visits）

---

### Step 2 — 筛选QA候选visits

**脚本**：`step2_filter_qa_candidates.ipynb`

**筛选条件**：

| 步骤 | 条件 |
|------|------|
| 1 | 入院前有历史诊断记录 |
| 2 | 排除肿瘤/移植/手术（前病史 + 入院诊断双重检查） |
| 3 | 入院后 24h 内有 Vitals/Labs 记录 |
| 4 | 出院后 GT 用药 1–10 种 |
| 5 | 年龄、性别信息完整 |

**GT 用药定义**：
```
持续用药 = 入院前30天口服药 ∩ 出院后7天口服药
新增用药 = 出院后7天口服药 - 入院前30天口服药
GT = 持续用药 ∪ 新增用药
```

**输出**：`output/qa_candidate/qa_candidate_visits.csv`（236 条 visits）

---

### Step 3 — 生成QA

**脚本**：`generate_qa_with_atc.py`

**题干包含**：
1. PRE-ADMISSION PROBLEM LIST — 入院前历史诊断
2. ADMISSION DIAGNOSIS — 本次入院诊断（来自 `condition_occurrence.csv`）
3. ADMISSION VITALS — 入院当天生命体征（原始单位）
4. ADMISSION LABS — 入院后 24h 内实验室检查（过滤零值和无单位数值）
5. CURRENT MEDICATIONS — 入院前 30 天口服药，附 ATC 分类

**答案**：GT 用药列表，每条标注 ATC 代码和 [Continued]/[New] 状态

**输出**：`output/QA/qa_output_with_atc.json/csv`

---

## QA 格式示例

```
PATIENT: 46-year-old Male
Department: GASTROENTEROLOGY
Admission: [REDACTED]
Discharge: [REDACTED]

─── PRE-ADMISSION PROBLEM LIST ────────────────────────────────────────
Cirrhosis of liver  (since [YEAR])
Bleeding esophageal varices  (since [YEAR])
...

─── ADMISSION DIAGNOSIS ───────────────────────────────────────────────
Cirrhosis of liver
Bleeding esophageal varices

─── ADMISSION VITALS ──────────────────────────────────────────────────
Systolic blood pressure: 86.00 mmHg
Pulse rate: 67.00 bpm
Body temperature: 97.90 F

─── ADMISSION LABS ([REDACTED]) ────────────────────────────────────────
Creatinine: 1.07 mg/dL
Hemoglobin: 9.50 g/dL
Platelet count: 104.00 K/uL
...

─── CURRENT MEDICATIONS (prior to admission) ──────────────────────────────
  - levothyroxine sodium 0.025 MG Oral Tablet  [ATC: H03AA - Thyroid hormones]
  ...

================================================================================

CLINICAL DECISION TASK:

Based on the admission information above, list the medications you would
prescribe for this patient after discharge.

Medication Orders:
1. lactulose  [ATC: A06AD - Osmotically acting laxatives]  [New]
2. rifaximin  [ATC: A07AA - Antibiotics]  [New]
3. levothyroxine sodium  [ATC: H03AA - Thyroid hormones]  [Continued]
```

---

## 工具模块：`medical_code_mapping.py`

EHRSHOT 中的医学代码都是标准化编码（如 `SNOMED/59621000`、`RxNorm/197391`），不能直接阅读。这个模块负责把代码翻译成可读的英文名称，供 Step2 和 Step3 使用。

| 函数 | 输入示例 | 输出示例 |
|------|----------|----------|
| `get_code_description("SNOMED/59621000")` | SNOMED/LOINC/CPT4 代码 | `"Essential hypertension"` |
| `get_medication_name("RxNorm/197391")` | RxNorm/RxNorm Extension 代码 | `"amlodipine 5 MG Oral Tablet"` |

三个 JSON 缓存文件是提前从外部 API 和数据库批量查询后保存的，避免每次运行时重复请求：
- `data/rxnorm_cache.json` — 从 NLM RxNorm REST API 获取（5,082条）
- `data/rxnorm_extension_cache.json` — 从 OMOP concept 表提取（214万条）
- `data/snomed_cache.json` — 从 UMLS MRCONSO.RRF 提取（41万条）

---

## 运行方式

```bash
cd /home/bingkun_zhao/ehrshot_analysis

# Step 1 & 2: 在 Jupyter 中运行对应 notebook
# Step 3: 修改 TARGET_COUNT 控制生成数量
python3 step3_generate_qa.py
```
