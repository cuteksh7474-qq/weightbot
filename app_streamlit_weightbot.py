
import streamlit as st
from PIL import Image
import io, os, json, time, re, math
import pandas as pd

# Optional OCR dependencies
try:
    import easyocr
    import numpy as np
    import cv2
    HAS_OCR = True
except Exception:
    HAS_OCR = False

st.set_page_config(page_title="WeightBot · 이미지 기반 무게 추정(웹·학습형)", page_icon="⚖️", layout="wide")

# -----------------------------
# Local feedback DB (simple)
# -----------------------------
LOCAL_DB = "feedback_db.json"
def load_local_db():
    try:
        with open(LOCAL_DB,"r",encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}
def save_local_db(data):
    try:
        with open(LOCAL_DB,"w",encoding="utf-8") as f:
            json.dump(data,f,ensure_ascii=False,indent=2)
    except Exception:
        pass

# -----------------------------
# Dictionaries & Priors
# -----------------------------
CATEGORY_KEYWORDS = {
    "rice_cooker": ["밥솥","전기밥솥","电饭煲","电饭锅","rice cooker"],
    "kettle": ["주전자","전기주전자","电热水壶","kettle"],
    "thermos": ["보온병","保温壶","flask","thermos"],
    "air_fryer": ["에어프라이어","空气炸锅","air fryer"],
    "blender": ["믹서기","블렌더","破壁机","blender"],
    "shoes": ["신발","鞋","sneakers","shoes"],
    "clothing": ["의류","옷","衣服","clothes","jacket","coat","tee","T恤"],
    "small_elec": ["드라이기","헤어드라이어","청소기","핸디청소기","전자","small electronics","hair dryer","vacuum","吸尘器"],
    "container": ["용기","수납함","플라스틱","塑料","塑料盒","container","box","收纳"],
    "pot_pan": ["냄비","锅","pot","cookware","平底锅","汤锅"],
    "beauty": ["갈바닉","미용기기","美容","beauty","洁面仪","面部"],
}
PRIORS = {
    "rice_cooker": {"shell_per_L":0.90,"inner_per_L":0.20,"base":0.30,"acc":0.10},
    "kettle": {"shell_per_L":0.45,"inner_per_L":0.12,"base":0.15,"acc":0.05},
    "thermos": {"shell_per_L":0.30,"inner_per_L":0.00,"base":0.05,"acc":0.00},
    "air_fryer": {"shell_per_L":0.70,"inner_per_L":0.18,"base":0.35,"acc":0.10},
    "blender": {"shell_per_L":0.55,"inner_per_L":0.10,"base":0.25,"acc":0.10},
    "container": {"thickness":0.03,"avg_density":1.0,"acc":0.05},
    "small_elec": {"base":0.35,"per_cm3_g":0.0009},
    "shoes": {"pair":0.80},
    "clothing": {"piece":0.35},
    "pot_pan": {"base":1.80},
    "beauty": {"base":0.40},
}
# 전력(모터/히터) 기반 가중치 (kg/kW) – 소형가전 중심의 보수적 추정값
POWER_FACTORS_KG_PER_KW = {
    "small_elec": 0.9,
    "blender": 0.8,
    "air_fryer": 0.6,
    "beauty": 0.5,
    "kettle": 0.3,
    "rice_cooker": 0.35,
    "thermos": 0.0,
    "container": 0.0,
    "shoes": 0.0,
    "clothing": 0.0,
    "pot_pan": 0.0
}

# -----------------------------
# Helper functions
# -----------------------------
def infer_category_from_name(name: str):
    name_l = (name or "").lower()
    for cat, kws in CATEGORY_KEYWORDS.items():
        for kw in kws:
            if kw.lower() in name_l:
                return cat
    if any(k in name_l for k in ["3l","2l","4l","5l","6l","리터","升"]):
        return "rice_cooker"
    return "small_elec"

def extract_capacity_L(txt: str):
    m = re.search(r'(\d+(?:\.\d+)?)\s*(l|리터|升)', (txt or "").lower())
    if m:
        try: return float(m.group(1))
        except: return 0.0
    m2 = re.search(r'(\d+(?:\.\d+)?)\s*(ml|毫升)', (txt or "").lower())
    if m2:
        try: return float(m2.group(1))/1000.0
        except: return 0.0
    return 0.0

def parse_weight_from_text(txt: str):
    txt_l = (txt or "").lower()
    m = re.search(r'(\d+(?:\.\d+)?)\s*(kg|g|斤|千克|公斤|克)', txt_l)
    if m:
        val = float(m.group(1)); unit = m.group(2)
        if unit in ["g","克"]: val/=1000.0
        elif unit in ["斤"]: val*=0.5
        return round(val,2)
    return None

def cn_unit_to_cm(val, unit):
    unit = (unit or "cm").lower()
    if unit in ["mm","毫米"]: return val/10.0
    if unit in ["cm","厘米"]: return val
    if unit in ["m","米"]: return val*100.0
    return val

def parse_dims_from_text(txt: str):
    txt = (txt or "").replace("：",":").replace("，",",").replace("×","x").replace("＊","x").replace("X","x")
    m = re.search(r'(\d+(?:\.\d+)?)\s*[x\*]\s*(\d+(?:\.\d+)?)\s*[x\*]\s*(\d+(?:\.\d+)?)(\s*(mm|cm|m|毫米|厘米|米))?', txt, re.I)
    if m:
        a,b,c = float(m.group(1)), float(m.group(2)), float(m.group(3))
        unit = (m.group(5) or "cm").lower()
        return tuple(sorted([cn_unit_to_cm(a,unit), cn_unit_to_cm(b,unit), cn_unit_to_cm(c,unit)], reverse=True))
    m2 = re.search(r'长\s*(\d+(?:\.\d+)?)\s*(mm|cm|m|毫米|厘米|米)?\s*宽\s*(\d+(?:\.\d+)?)\s*(mm|cm|m|毫米|厘米|米)?\s*高\s*(\d+(?:\.\d+)?)\s*(mm|cm|m|毫米|厘米|米)?', txt, re.I)
    if m2:
        l = cn_unit_to_cm(float(m2.group(1)), (m2.group(2) or "cm").lower())
        w = cn_unit_to_cm(float(m2.group(3)), (m2.group(4) or "cm").lower())
        h = cn_unit_to_cm(float(m2.group(5)), (m2.group(6) or "cm").lower())
        return (l,w,h)
    return None

def parse_power_to_kw(txt: str):
    if not txt: return 0.0
    t = txt.lower().replace(" ", "")
    mkw = re.search(r'(\d+(?:\.\d+)?)\s*kw', t)
    if mkw:
        try: return float(mkw.group(1))
        except: return 0.0
    mw = re.search(r'(\d+(?:\.\d+)?)\s*w', t)
    if mw:
        try: return float(mw.group(1))/1000.0
        except: return 0.0
    return 0.0

def packaging_weight(L,W,H,override=None):
    if override and override>0: return override
    if not (L and W and H): return 0.5
    vol = L*W*H
    return 0.25 + min(1.5, vol*0.000001)

def volumetric(L,W,H,divisor):
    if not (L and W and H): return 0.0
    return (L*W*H)/divisor

def avg_delta_for_category(db, category):
    deltas = []
    for _,v in db.items():
        if v.get("category")==category and isinstance(v.get("delta"),(int,float)):
            deltas.append(v["delta"])
    if not deltas: return 0.0
    return max(-2.0, min(2.0, sum(deltas)/len(deltas)))

def estimate_weight_auto(product_name, capacity_L, category_key, dims_cm, feedback_db, power_kw=0.0, extra_kg=0.1, net_override=None):
    L,W,H = dims_cm
    pri = PRIORS.get(category_key, {})
    net = 0.0

    if net_override is not None:
        net = net_override + 0.0
    elif category_key in ["rice_cooker","kettle","thermos","air_fryer","blender"]:
        cap = max(0.0, capacity_L or 0.0)
        net = pri.get("shell_per_L",0)*cap + pri.get("inner_per_L",0)*cap + pri.get("base",0) + pri.get("acc",0) + extra_kg
    elif category_key=="container":
        cap = capacity_L or 0.0
        if cap<=0 and all(dims_cm): cap = (L*W*H*0.6)/1000.0
        thickness = PRIORS["container"]["thickness"]
        avg_d = PRIORS["container"]["avg_density"]
        shell_vol_cm3 = (cap*1000.0)*thickness
        mass_kg = max(0.05, (shell_vol_cm3*avg_d)/1000.0)
        net = mass_kg + extra_kg
    elif category_key=="small_elec":
        vol_cm3 = (L or 30)*(W or 30)*(H or 25)
        net = PRIORS["small_elec"]["base"] + vol_cm3*PRIORS["small_elec"]["per_cm3_g"]/1000.0 + extra_kg
    elif category_key=="shoes":
        net = PRIORS["shoes"]["pair"]
    elif category_key=="clothing":
        net = PRIORS["clothing"]["piece"]
    elif category_key=="pot_pan":
        net = PRIORS["pot_pan"]["base"] + extra_kg
    elif category_key=="beauty":
        net = PRIORS["beauty"]["base"] + extra_kg
    else:
        net = 0.6 + extra_kg

    # 전력 기반 추가 질량
    factor = POWER_FACTORS_KG_PER_KW.get(category_key, 0.3)
    net += max(0.0, power_kw) * factor

    delta = avg_delta_for_category(feedback_db, category_key)
    net_adj = max(0.05, net + delta)

    pkg = packaging_weight(L,W,H,None)
    gross = net_adj + pkg
    vol5000 = volumetric(L,W,H,5000)
    vol6000 = volumetric(L,W,H,6000)

    conf = 70
    if capacity_L>0: conf += 10
    if all(dims_cm): conf += 10
    if power_kw>0: conf += 5
    conf = max(30, min(95, conf))

    return {"net_kg": round(net_adj,2), "gross_kg": round(gross,2),
            "vol_5000": round(vol5000,2), "vol_6000": round(vol6000,2),
            "confidence": conf, "category": category_key, "delta_applied": round(delta,2),
            "power_kw": power_kw, "power_factor": factor}

# -----------------------------
# OCR utilities
# -----------------------------
def ocr_text_from_image(img_bytes):
    if not HAS_OCR: return None, "OCR 모듈 미설치(easyocr)."
    try:
        img = Image.open(io.BytesIO(img_bytes)).convert("RGB")
        arr = __import__("numpy").array(img)
        reader = easyocr.Reader(['ch_sim','en','ko'], gpu=False)
        result = reader.readtext(arr, detail=0, paragraph=True)
        text = "\n".join(result)
        return text, None
    except Exception as e:
        return None, f"OCR 실패: {e}"

OPTION_HINT_KEYWORDS = ["选项","颜色","颜色分类","容量","规格","尺寸","尺码","款式","型号","版本","组合","套装","材质","图案","口味","大小","重量","功率","瓦","w","W","千瓦","kW","KW"]
def extract_option_candidates_from_text(txt: str):
    if not txt: return []
    lines = [l.strip() for l in txt.splitlines() if l.strip()]
    cand = []
    for line in lines:
        if any(kw in line for kw in OPTION_HINT_KEYWORDS):
            part = re.split(r'[:：]\s*', line, maxsplit=1)
            tail = part[-1] if len(part)>1 else line
            items = re.split(r'[、/,\|，\s]+', tail)
            items = [i.strip() for i in items if i.strip() and len(i.strip())<=25]
            items = [i for i in items if not any(kw==i for kw in OPTION_HINT_KEYWORDS)]
            cand.extend(items)
    seen=set(); out=[]
    for i in cand:
        if i not in seen:
            out.append(i); seen.add(i)
    return out[:20]

# -----------------------------
# UI
# -----------------------------
st.title("⚖️ WeightBot · 이미지 기반 무게 추정(웹·학습형)")
st.caption("이미지·상품명·상품코드만 입력하면 결과는 항상 **한국어**로 보여드립니다. 옵션명이 제공되면 **우선 적용**, 없으면 자동 옵션코드 생성. 전기 제품은 **출력용량(W/kW)** 선택 시 추가 반영합니다.")

db = load_local_db()

colA, colB, colC = st.columns([1.2,1.2,1.2])
with colA:
    product_code = st.text_input("상품코드", placeholder="예: A240812")
    product_name = st.text_input("상품명 (재질/용량 포함 시 정확도↑)", placeholder="예: 3L 전기밥솥 스테인리스 내솥형")
with colB:
    imgs = st.file_uploader("상품/스펙 이미지 업로드 (여러 장 가능, 중국어 OK)", type=["png","jpg","jpeg","webp"], accept_multiple_files=True)
    if imgs:
        st.image(imgs[0], caption="대표 이미지", use_column_width=True)
with colC:
    c1, c2, c3 = st.columns(3)
    with c1:
        manual_L = st.number_input("수동 용량(L, 선택)", min_value=0.0, step=0.1, value=0.0)
    with c2:
        power_options = ["선택 안함"] + [f"{i}W" for i in range(100,1000,100)] + [f"{i}kW" for i in range(1,11)]
        power_choice = st.selectbox("출력용량(선택, W/kW)", options=power_options, index=0, help="전기·모터 제품이면 선택하세요. 백단위 W(9개) + 1~10 kW(10개)")
    with c3:
        num_options = st.number_input("옵션 개수(옵션명 없을 때만 사용)", min_value=1, step=1, value=1)

st.markdown("---")

ocr_text = ""
if imgs:
    for i, f in enumerate(imgs, start=1):
        t, err = ocr_text_from_image(f.read())
        if t: ocr_text += f"\n[이미지{i}]\n{t}\n"

st.subheader("옵션명 입력(선택, 한 줄에 하나) — 제공되면 **우선 적용**")
if "option_names_text" not in st.session_state: st.session_state["option_names_text"] = ""
colO1, colO2 = st.columns([3,1])
with colO1:
    option_names_text = st.text_area("옵션명 목록(예: 검정색 3L / 800W)", key="option_names_text", height=120, placeholder="여기에 옵션명을 한 줄에 하나씩 입력하세요.")
with colO2:
    if st.button("OCR에서 옵션명 후보 가져오기"):
        if ocr_text:
            cands = extract_option_candidates_from_text(ocr_text)
            if cands:
                st.session_state["option_names_text"] = "\n".join(cands)
            else:
                st.warning("OCR 텍스트에서 옵션명을 찾지 못했습니다.")
        else:
            st.warning("먼저 이미지(스펙표)를 업로드하세요.")

option_names = [ln.strip() for ln in (st.session_state.get("option_names_text") or "").splitlines() if ln.strip()]
total_options = len(option_names) if option_names else int(num_options)

auto_cat = infer_category_from_name(product_name)
global_cap = extract_capacity_L(product_name) or extract_capacity_L(ocr_text) or manual_L or 0.0
dims_from_ocr = parse_dims_from_text(ocr_text) or (30.0,30.0,25.0)
global_power_kw = parse_power_to_kw(power_choice)

st.write(f"🧠 자동 판별: 카테고리=`{auto_cat}`, 기준 용량≈`{global_cap} L`, OCR 치수(cm)={dims_from_ocr}, 전력={global_power_kw} kW")

rows = []
for idx in range(1, total_options+1):
    with st.expander(f"옵션 {idx}", expanded=(idx==1)):
        opt_code = f"{product_code}-{idx:02d}" if product_code else f"OPT-{idx:02d}"
        display_name = option_names[idx-1] if option_names else f"(자동){opt_code}"
        st.text_input("옵션코드", value=opt_code, key=f"opt_code_{idx}", disabled=True)
        st.text_input("옵션명(표 제공/수동 입력 시 우선)", value=display_name, key=f"opt_name_{idx}")

        cap_opt = extract_capacity_L(display_name) or global_cap
        net_override = parse_weight_from_text(display_name)
        power_opt_kw = parse_power_to_kw(display_name) or global_power_kw

        result = estimate_weight_auto(
            product_name=product_name,
            capacity_L=cap_opt,
            category_key=auto_cat,
            dims_cm=dims_from_ocr,
            feedback_db=db,
            power_kw=power_opt_kw,
            extra_kg=0.10,
            net_override=net_override
        )

        st.markdown(f"""
**결과(한국어):**  
- 옵션코드: **{opt_code}**  
- 옵션명: **{display_name}**  
- **순중량**: **{result['net_kg']} kg**  
- **포장 포함 총중량**: **{result['gross_kg']} kg**  
- **부피무게(5000 / 6000)**: **{result['vol_5000']} / {result['vol_6000']} kg**  
- 전력 반영: **{result['power_kw']} kW × {result['power_factor']} kg/kW**  
- 신뢰도: **{result['confidence']}%** *(카테고리 평균 보정: {result['delta_applied']} kg)*
""")
        rows.append({
            "product_code": product_code,
            "option_code": opt_code,
            "option_name": display_name,
            "product_name": product_name,
            "category": result["category"],
            "capacity_L": cap_opt,
            "power_kW": result["power_kw"],
            "box_cm": f"{dims_from_ocr[0]}x{dims_from_ocr[1]}x{dims_from_ocr[2]}",
            "net_kg": result["net_kg"],
            "gross_kg": result["gross_kg"],
            "vol_5000": result["vol_5000"],
            "vol_6000": result["vol_6000"],
            "confidence": result["confidence"],
            "delta_applied": result["delta_applied"],
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
        })

st.markdown("---")
if rows:
    df = pd.DataFrame(rows)
    st.dataframe(df, use_container_width=True)
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="xlsxwriter") as writer:
        df.to_excel(writer, sheet_name="results", index=False)
    st.download_button("결과를 Excel로 저장", data=buf.getvalue(), file_name=f"{(product_code or 'results')}_estimate.xlsx")

st.subheader("실측무게 피드백 → 학습 반영")
c1,c2,c3 = st.columns(3)
with c1:
    fb_opt = st.text_input("옵션코드 (예: A240812-01)")
with c2:
    fb_pred = st.number_input("당시 예측값 (kg)", min_value=0.0, step=0.01, value=0.0)
with c3:
    fb_actual = st.number_input("실측값 (kg)", min_value=0.0, step=0.01, value=0.0)
if st.button("피드백 저장 & 학습 반영"):
    if not fb_opt or fb_pred<=0 or fb_actual<=0:
        st.error("옵션코드/예측/실측값을 모두 입력하세요.")
    else:
        delta = round(fb_actual - fb_pred, 3)
        db[fb_opt] = {"predicted": fb_pred, "actual": fb_actual, "delta": delta, "category": infer_category_from_name(product_name), "ts": time.time()}
        save_local_db(db)
        st.success(f"저장 완료! (Δ={delta} kg) 다음부터 같은 카테고리에 평균 보정이 적용됩니다.")
