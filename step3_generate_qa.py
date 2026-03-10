"""
Step 3: 生成用药管理QA数据集
- 输入：Step2 筛选后的候选 visits（qa_candidate_visits.csv）
- 题干包含：前病史、入院诊断、Vitals、Labs、入院前用药（含ATC分类）
- 答案：出院后GT用药列表（含ATC分类和续开/新开状态）
"""
import pandas as pd
import json
import sys
import os
from datetime import timedelta

# Add current directory to path for medical_code_mapping import
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from medical_code_mapping import get_medication_name, get_code_description

# ── 配置 ──────────────────────────────────────────────────────────────────
EHRSHOT_CSV = "/data/ehr/EHRSHOT/EHRSHOT_ASSETS/data/ehrshot.csv"
CANDIDATES_CSV = "/home/bingkun_zhao/ehrshot-medication-qa/output/qa_candidate/qa_candidate_visits.csv"
CONDITION_CSV = "/home/bingkun_zhao/ehrshot-medication-qa/data/condition_occurrence.csv"
CONCEPT_CSV = "/home/bingkun_zhao/ehrshot-medication-qa/data/concept.csv"
RXNORM_ATC_CSV = "/home/bingkun_zhao/ehrshot-medication-qa/data/rxnorm_to_atc.csv.csv"
OUTPUT_JSON = "/home/bingkun_zhao/ehrshot-medication-qa/output/QA/qa_output_with_atc.json"
OUTPUT_CSV = "/home/bingkun_zhao/ehrshot-medication-qa/output/QA/qa_output_with_atc.csv"

TARGET_COUNT = 236
RECENT_MED_LOOKBACK_DAYS = 30
POST_DISCHARGE_WINDOW_DAYS = 30

ORAL_FORM_KEYWORDS = [
    'oral tablet', 'oral capsule', 'oral solution', 'oral suspension',
    'chewable tablet', 'disintegrating oral tablet', 'extended release oral',
    'delayed release oral', 'oral powder',
]

EXCLUDE_DRUG_KEYWORDS = [
    'lidocaine', 'propofol', 'ketamine', 'sevoflurane', 'fentanyl',
    'rocuronium', 'vecuronium', 'succinylcholine', 'midazolam',
    'cisplatin', 'carboplatin', 'doxorubicin', 'paclitaxel',
    'tacrolimus', 'cyclosporine', 'sirolimus', 'mycophenolate',
]

def is_oral_medication(drug_name):
    name_lower = drug_name.lower()
    return any(kw in name_lower for kw in ORAL_FORM_KEYWORDS)

def is_excluded_medication(drug_name):
    name_lower = drug_name.lower()
    return any(kw in name_lower for kw in EXCLUDE_DRUG_KEYWORDS)

def _resolve(code):
    desc = get_code_description(code)
    if "(" in desc and ")" in desc:
        inner = desc.split("(")[1].split(")")[0].strip()
        if inner and not inner.startswith(("SNOMED", "ICD", "LOINC")):
            return inner
    return desc

def _fmt_unit(unit):
    if unit is None:
        return ""
    s = str(unit)
    return "" if s in ("nan", "None", "") else s

# Vital default units when EHRSHOT unit field is empty
_VITAL_DEFAULT_UNITS = {
    "Systolic blood pressure": "mmHg",
    "Diastolic blood pressure": "mmHg",
    "Pulse rate": "bpm",
    "Respiratory rate": "bpm",
    "Body temperature": "F",   # EHRSHOT NaN unit temps are in Fahrenheit
    "Body weight": "ounces",
    "Body height": "in",
}

def _fmt_val(val):
    """Format numeric value to 2 decimal places."""
    try:
        return f"{float(val):.2f}"
    except (TypeError, ValueError):
        return str(val)

# ── 加载数据 ──────────────────────────────────────────────────────────────
print("="*80)
print("生成包含ATC信息的QA（v2）")
print("="*80)

print(f"\n1. 加载候选visits...")
candidates = pd.read_csv(CANDIDATES_CSV)
candidates['priority'] = 0
candidates.loc[candidates['care_site_name'] == 'GASTROENTEROLOGY', 'priority'] += 10
candidates = candidates.sort_values('priority', ascending=False)
print(f"   候选visits数: {len(candidates)}")

print(f"\n2. 加载EHRSHOT数据（仅候选患者）...")
candidate_pids = set(candidates['person_id'])
print(f"   候选患者数: {len(candidate_pids)}")
df = pd.read_csv(EHRSHOT_CSV, low_memory=False)
df = df[df['patient_id'].isin(candidate_pids)]
print(f"   过滤后记录数: {len(df):,}")

print(f"\n3. 分离OMOP表...")
conditions = df[df["omop_table"] == "condition_occurrence"]
drugs = df[df["omop_table"] == "drug_exposure"]
measures = df[df["omop_table"] == "measurement"]
print(f"   conditions: {len(conditions):,}, drugs: {len(drugs):,}, measures: {len(measures):,}")

print(f"\n4. 加载本地condition_occurrence数据...")
visit_conditions = pd.read_csv(CONDITION_CSV, low_memory=False)
print(f"   记录数: {len(visit_conditions):,}")

print(f"\n5. 加载concept数据...")
concept = pd.read_csv(CONCEPT_CSV, low_memory=False)
concept_map = dict(zip(concept['concept_id'], concept['concept_name']))
print(f"   记录数: {len(concept):,}")

def get_condition_name(concept_id):
    return concept_map.get(concept_id, f"Concept_{concept_id}")

print(f"\n6. 加载RxNorm→ATC映射表...")
atc_df = pd.read_csv(
    RXNORM_ATC_CSV,
    header=None,
    names=['rxcui', 'drug_name', 'atc1_code', 'atc1_name', 'atc2_code', 'atc2_name',
           'atc3_code', 'atc3_name', 'atc4_code', 'atc4_name'],
    dtype={'rxcui': str},
    encoding='utf-8-sig'  # 处理BOM
)
# rxcui去掉引号
atc_df['rxcui'] = atc_df['rxcui'].str.strip('"')
atc_map = {}
for _, row in atc_df.iterrows():
    rxcui = str(row['rxcui'])
    # Clean up values, convert \N to "Unknown"
    def clean_atc_value(val):
        val_str = str(val).strip('"')
        return "Unknown" if val_str in ('\\N', 'nan', '', 'None') else val_str

    atc_map[rxcui] = {
        'atc4_code': clean_atc_value(row['atc4_code']),
        'atc4_name': clean_atc_value(row['atc4_name']),
        'atc3_code': clean_atc_value(row['atc3_code']),
        'atc3_name': clean_atc_value(row['atc3_name']),
        'atc2_code': clean_atc_value(row['atc2_code']),
        'atc2_name': clean_atc_value(row['atc2_name']),
        'atc1_code': clean_atc_value(row['atc1_code']),
        'atc1_name': clean_atc_value(row['atc1_name']),
    }
print(f"   映射条目数: {len(atc_map):,}")

def get_atc_info(code):
    """从code中提取RxCUI并查找ATC信息"""
    rxcui = code.split("/")[-1] if "/" in code else code
    return atc_map.get(rxcui, {})

# ── 生成QA ────────────────────────────────────────────────────────────────
print(f"\n{'='*80}")
print(f"开始生成QA (目标: {TARGET_COUNT}个)")
print(f"{'='*80}")

qa_items = []
stats = {'no_gt_drugs': 0, 'ok': 0}
total_candidates = len(candidates)

for idx_i, (i, row) in enumerate(candidates.iterrows()):
    if len(qa_items) >= TARGET_COUNT:
        break

    patient_id = row["person_id"]
    visit_id = row["visit_occurrence_id"]
    admission_dt = pd.to_datetime(row["visit_start_date"])
    discharge_dt = pd.to_datetime(row["visit_end_date"])
    age = row.get("age", "Unknown")
    gender = row.get("gender", "Unknown")
    care_site = row["care_site_name"]
    los_days = row["duration_days"]

    print(f"\n[进度 {idx_i+1}/{total_candidates}] 已生成 {len(qa_items)}/{TARGET_COUNT} | Patient {patient_id}, Visit {visit_id}")

    admission_date_start = pd.Timestamp(admission_dt.date())

    # ── 1. 前病史 ────────────────────────────────────────────────────────
    pre_cond = conditions[
        (conditions["patient_id"] == patient_id) &
        (pd.to_datetime(conditions["start"], errors="coerce") < admission_date_start)
    ].copy()

    pre_cond["_dt"] = pd.to_datetime(pre_cond["start"], errors="coerce")
    pre_cond = pre_cond.sort_values("_dt").drop_duplicates(subset=["code"], keep="first")
    print(f"  前病史: {len(pre_cond)} 条")

    # ── 2. 入院诊断 ──────────────────────────────────────────────────────
    admission_diagnoses = visit_conditions[visit_conditions['visit_occurrence_id'] == visit_id]
    print(f"  入院诊断: {len(admission_diagnoses)} 条")

    # ── 3. 近期用药（入院前30天，口服药） ────────────────────────────────
    pre_meds_raw = drugs[
        (drugs["patient_id"] == patient_id) &
        (drugs["visit_id"] != visit_id) &
        (pd.to_datetime(drugs["start"], errors="coerce") >= admission_dt - timedelta(days=RECENT_MED_LOOKBACK_DAYS)) &
        (pd.to_datetime(drugs["start"], errors="coerce") < admission_date_start)
    ]

    seen_pre = set()
    valid_pre_meds = []
    recent_drug_bases = set()

    for _, dr in pre_meds_raw.iterrows():
        drug_name = get_medication_name(dr["code"])
        if drug_name == dr["code"] or not is_oral_medication(drug_name) or is_excluded_medication(drug_name):
            continue
        base = drug_name.split()[0].lower()
        if base in seen_pre:
            continue
        seen_pre.add(base)
        recent_drug_bases.add(base)
        atc_info = get_atc_info(dr["code"])
        valid_pre_meds.append({"name": drug_name, "atc": atc_info})

    print(f"  近期用药: {len(valid_pre_meds)} 种")

    # ── 4. GT用药（出院后30天，口服药） ──────────────────────────────────
    post_discharge_drugs = drugs[
        (drugs["patient_id"] == patient_id) &
        (drugs["visit_id"] != visit_id) &
        (pd.to_datetime(drugs["start"], errors="coerce") >= discharge_dt) &
        (pd.to_datetime(drugs["start"], errors="coerce") <= discharge_dt + timedelta(days=POST_DISCHARGE_WINDOW_DAYS))
    ]

    gt_drugs = []
    seen_gt = set()

    for _, dr in post_discharge_drugs.iterrows():
        drug_name = get_medication_name(dr["code"])
        if drug_name == dr["code"] or not is_oral_medication(drug_name) or is_excluded_medication(drug_name):
            continue
        base = drug_name.split()[0].lower()
        if base in seen_gt:
            continue
        seen_gt.add(base)
        atc_info = get_atc_info(dr["code"])
        gt_drugs.append({
            "medication_name": drug_name,
            "atc": atc_info,
            "is_continued": base in recent_drug_bases,
        })

    if len(gt_drugs) == 0:
        print("  ⚠️ 无GT用药，跳过")
        stats['no_gt_drugs'] += 1
        continue

    continued = sum(1 for d in gt_drugs if d["is_continued"])
    new_drugs_count = len(gt_drugs) - continued
    print(f"  GT用药: {len(gt_drugs)} 种 (续开:{continued}, 新开:{new_drugs_count})")

    # ── 5. 构建clinical_note ─────────────────────────────────────────────
    cutoff_24h = admission_date_start + timedelta(hours=24)

    lines = [
        f"PATIENT: {age}-year-old {gender}",
        f"Department: {care_site}",
        f"Admission: [REDACTED]",
        f"Discharge: [REDACTED]",
        "",
        "─── PRE-ADMISSION PROBLEM LIST ────────────────────────────────────────",
    ]

    added_conds = set()
    for _, cr in pre_cond.iterrows():
        cond_name = _resolve(cr["code"])
        if cond_name.startswith(("SNOMED/", "ICD", "ICDO")) or cond_name in added_conds:
            continue
        added_conds.add(cond_name)
        lines.append(f"{cond_name}  (since [YEAR])")
    lines.append("")

    # 入院诊断
    if len(admission_diagnoses) > 0:
        lines.append("─── ADMISSION DIAGNOSIS ───────────────────────────────────────────────")
        added_dx = set()
        for _, dx in admission_diagnoses.iterrows():
            dx_name = get_condition_name(dx['condition_concept_id'])
            if dx_name not in added_dx:
                added_dx.add(dx_name)
                lines.append(f"{dx_name}")
        lines.append("")

    # Vitals
    pat_measures = measures[
        (measures["patient_id"] == patient_id) &
        (pd.to_datetime(measures["start"], errors="coerce") >= admission_date_start) &
        (pd.to_datetime(measures["start"], errors="coerce") <= cutoff_24h)
    ]

    if not pat_measures.empty:
        lines.append("─── ADMISSION VITALS ──────────────────────────────────────────────────")
        vital_codes = {
            "LOINC/8480-6": "Systolic blood pressure",
            "LOINC/8462-4": "Diastolic blood pressure",
            "LOINC/8867-4": "Pulse rate",
            "LOINC/9279-1": "Respiratory rate",
            "LOINC/8310-5": "Body temperature",
            "LOINC/29463-7": "Body weight",
            "LOINC/8302-2": "Body height",
        }
        added_vitals = set()
        for vcode, vlabel in vital_codes.items():
            vrows = pat_measures[pat_measures["code"] == vcode]
            if not vrows.empty and vlabel not in added_vitals:
                val = vrows.iloc[0]["value"]
                unit = _fmt_unit(vrows.iloc[0].get("unit", ""))
                if pd.notna(val):
                    unit = unit or _VITAL_DEFAULT_UNITS.get(vlabel, "")
                    unit = unit.replace("[in_us]", "in").replace("deg C", "°C").replace("deg F", "F")
                    # Fix temperature unit based on value range
                    if vlabel == "Body temperature":
                        fval = float(val)
                        if fval < 50:  # Celsius range (normal: 35-42°C)
                            unit = "°C"
                        else:  # Fahrenheit range (normal: 95-108°F)
                            unit = "F"
                    lines.append(f"{vlabel}: {_fmt_val(val)} {unit}".strip())
                    added_vitals.add(vlabel)
        lines.append("")

    # Labs — 排除 vitals LOINC 代码、0值、已在 vitals 中出现的指标
    _VITAL_LOINC_CODES = {"LOINC/8480-6","LOINC/8462-4","LOINC/8867-4","LOINC/9279-1",
                          "LOINC/8310-5","LOINC/29463-7","LOINC/8302-2"}
    if not pat_measures.empty:
        lab_rows = pat_measures[~pat_measures["code"].isin(_VITAL_LOINC_CODES)]
        if not lab_rows.empty:
            lines.append("─── ADMISSION LABS ([REDACTED]) ────────────────────────────────────────")
            seen_labs = set()
            for _, lr in lab_rows.iterrows():
                lab_name = _resolve(lr["code"])
                if lab_name.startswith(("LOINC/", "SNOMED/")) or lab_name in seen_labs:
                    continue
                seen_labs.add(lab_name)
                val = lr["value"]
                unit = _fmt_unit(lr.get("unit", ""))
                try:
                    fval = float(val)
                    if pd.notna(val) and fval != 0.0:
                        # Skip numeric values with no unit (likely panel scores without clinical meaning)
                        if not unit:
                            continue
                        lines.append(f"{lab_name}: {_fmt_val(val)} {unit}".strip())
                except (TypeError, ValueError):
                    if pd.notna(val):
                        lines.append(f"{lab_name}: {val}")
            lines.append("")

    # 入院前用药（含ATC）
    if valid_pre_meds:
        lines.append("─── CURRENT MEDICATIONS (prior to admission) ──────────────────────────────")
        for m in valid_pre_meds:
            atc = m['atc']
            atc_code = atc.get('atc4_code', 'Unknown')
            atc_name = atc.get('atc4_name', 'Unknown')

            if atc_code != 'Unknown':
                lines.append(f"  - {m['name']}  [ATC: {atc_code} - {atc_name}]")
            else:
                lines.append(f"  - {m['name']}  [ATC: Unknown]")
        lines.append("")

    lines += [
        "=" * 80, "",
        "CLINICAL DECISION TASK:", "",
        "Based on the admission information above, list the medications you would",
        "prescribe for this patient after discharge.",
    ]

    clinical_note = "\n".join(lines)

    # ── 6. 答案 ──────────────────────────────────────────────────────────
    question = "What medications would you prescribe for this patient after discharge?"

    answer_lines = ["Medication Orders:"]
    for idx, med in enumerate(gt_drugs, 1):
        status = "Continued" if med["is_continued"] else "New"
        atc = med['atc']
        # Strip dose/form: keep everything before dose pattern (e.g., "0.025 MG", "600 MG")
        # Dose units: MG, ML, MCG, UNIT, UNT, %, etc. (not HR which is time)
        dose_units = {'MG', 'ML', 'MCG', 'UNIT', 'UNT', '%', 'G', 'L'}
        words = med['medication_name'].split()
        name_words = []

        for i, w in enumerate(words):
            # Check if this word is a number and next word is a dose unit
            if i < len(words) - 1:
                next_word = words[i + 1]
                # If current word has digits and next is a dose unit
                if any(c.isdigit() for c in w) and next_word in dose_units:
                    # Found dose pattern, stop here
                    break
            name_words.append(w)

        drug_base = " ".join(name_words).rstrip(",") if name_words else med['medication_name']

        # Display ATC info (show "Unknown" if not available)
        atc_code = atc.get('atc4_code', 'Unknown')
        atc_name = atc.get('atc4_name', 'Unknown')

        if atc_code != 'Unknown':
            answer_lines.append(f"{idx}. {drug_base}  [ATC: {atc_code} - {atc_name}]  [{status}]")
        else:
            answer_lines.append(f"{idx}. {drug_base}  [ATC: Unknown]  [{status}]")

    answer = "\n".join(answer_lines)

    qa_items.append({
        "qa_id": f"qa_{len(qa_items)+1:03d}",
        "patient_id": str(patient_id),
        "visit_id": str(visit_id),
        "care_site": care_site,
        "los_days": int(los_days),
        "age": int(age) if age != "Unknown" else None,
        "gender": gender,
        "clinical_note": clinical_note,
        "question": question,
        "answer": answer,
        "ground_truth_medications": gt_drugs,
        "num_gt_medications": len(gt_drugs),
        "num_continued": continued,
        "num_new": new_drugs_count,
    })

    stats['ok'] += 1
    print(f"  ✅ 已生成QA #{len(qa_items)}")

# ── 保存结果 ──────────────────────────────────────────────────────────────
print(f"\n{'='*80}")
print("保存结果...")

with open(OUTPUT_JSON, 'w') as f:
    json.dump(qa_items, f, indent=2, ensure_ascii=False)
print(f"✓ JSON: {OUTPUT_JSON}")

csv_data = [{
    'qa_id': qa['qa_id'], 'patient_id': qa['patient_id'], 'visit_id': qa['visit_id'],
    'care_site': qa['care_site'], 'los_days': qa['los_days'],
    'age': qa['age'], 'gender': qa['gender'],
    'clinical_note': qa['clinical_note'], 'question': qa['question'], 'answer': qa['answer'],
    'num_gt_medications': qa['num_gt_medications'],
    'num_continued': qa['num_continued'], 'num_new': qa['num_new'],
} for qa in qa_items]
pd.DataFrame(csv_data).to_csv(OUTPUT_CSV, index=False)
print(f"✓ CSV: {OUTPUT_CSV}")

# ── 统计 ──────────────────────────────────────────────────────────────────
print(f"\n{'='*80}")
print("统计")
print(f"{'='*80}")
for k, v in stats.items():
    print(f"  {k}: {v}")

if qa_items:
    total_meds = sum(qa['num_gt_medications'] for qa in qa_items)
    meds_with_atc = sum(
        sum(1 for med in qa['ground_truth_medications'] if med.get('atc', {}).get('atc4_code'))
        for qa in qa_items
    )
    print(f"\n  总GT用药: {total_meds}")
    print(f"  有ATC信息: {meds_with_atc} ({meds_with_atc/total_meds*100:.1f}%)")
    print(f"  平均GT用药: {total_meds/len(qa_items):.1f}种")

print(f"\n完成！")
