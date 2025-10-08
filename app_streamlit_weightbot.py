# -*- coding: utf-8 -*-
import io
from typing import Optional, Tuple
import pandas as pd
import streamlit as st

st.set_page_config(page_title="WeightBot · 이미지 기반 무게 추정(웹·학습형)", layout="wide")

# -----------------------------
# Helpers
# -----------------------------
def parse_float(txt: str) -> Optional[float]:
    """Return float if parseable, else None."""
    if txt is None:
        return None
    s = str(txt).strip().replace(',', '')
    if s == "":
        return None
    try:
        return float(s)
    except Exception:
        return None

def dims_tuple(l: Optional[float], w: Optional[float], h: Optional[float]) -> Optional[Tuple[float, float, float]]:
    if l is None or w is None or h is None:
        return None
    return (float(l), float(w), float(h))

def format_dims_cm(d: Optional[Tuple[float, float, float]]) -> str:
    if not d:
        return ""
    l, w, h = d
    return f"{l:.1f}x{w:.1f}x{h:.1f}"

def vol_weight(d: Optional[Tuple[float, float, float]], allowance_cm: float, divisor: int) -> Optional[float]:
    if not d:
        return None
    l, w, h = d
    # 박스 여유값을 각 변에 + allowance로 반영
    L = l + allowance_cm
    W = w + allowance_cm
    H = h + allowance_cm
    try:
        return round((L * W * H) / divisor, 2)
    except Exception:
        return None

def to_excel_bytes(df: pd.DataFrame) -> bytes:
    out = io.BytesIO()
    with pd.ExcelWriter(out, engine="xlsxwriter") as writer:
        df.to_excel(writer, index=False, sheet_name="results")
        writer.close()
    return out.getvalue()

# -----------------------------
# Session init
# -----------------------------
if "num_options" not in st.session_state:
    st.session_state["num_options"] = 4  # 최초 1회만 기본 4로 초기화

# -----------------------------
# Header
# -----------------------------
st.markdown("## ⚖️ WeightBot · 이미지 기반 무게 추정(웹·학습형)")
st.caption("이미지/상품명/상품코드만 입력해도 결과는 항상 **한국어**로 보여집니다.")

# -----------------------------
# Top inputs (product)
# -----------------------------
colA, colB = st.columns([1.2, 1])
with colA:
    product_code = st.text_input("상품코드", placeholder="예: A240812")
    product_name = st.text_input("상품명 (재질/용량 포함 시 정확도↑)", placeholder="예: 3L 전기밥솥 스테인리스 내솥형")

with colB:
    st.file_uploader("상품/스펙 이미지 업로드 (여러 장 가능, 중국어 OK)", type=["png", "jpg", "jpeg", "webp"], accept_multiple_files=True)

# -----------------------------
# Dimension section (requested change)
# -----------------------------
st.markdown("---")
st.markdown("### 치수(cm)")

c1, c2, c3, c4 = st.columns([1, 1, 1, 1])

# 🔴 요구사항: 빨간 박스 → 0.00 없이 **공란**
with c1:
    L_txt = st.text_input("가로 L", value="", placeholder="")
with c2:
    W_txt = st.text_input("세로 W", value="", placeholder="")
with c3:
    H_txt = st.text_input("높이 H", value="", placeholder="")

# 🔵 요구사항: 파란 박스 → **2.5cm 고정값**
with c4:
    allowance_cm_fixed = st.number_input("사량여유(+cm)", value=2.5, step=0.1, disabled=True,
                                         help="요청대로 2.5cm 고정 (수정 불가)")

L = parse_float(L_txt)
W = parse_float(W_txt)
H = parse_float(H_txt)
dims = dims_tuple(L, W, H)
box_str = format_dims_cm(dims)

# 가이드 입력 상자 (값 3개 직접 입력시 강제 적용 버튼 필요X)
helper_txt = st.text_input("입력하세요(예: 750mm, 640mm, 550mm / 75cm,55cm,64cm)", value="")

st.markdown("---")

# -----------------------------
# Options & power
# -----------------------------
st.markdown("### 옵션명(선택, 한 줄에 하나) + 출력 용량 선택")
opt_lines = st.text_area("옵션명 목록", placeholder="여기에 옵션명을 한 줄에 하나씩 입력하세요.")
options_raw = [s.strip() for s in opt_lines.splitlines() if s.strip()]
if options_raw:
    st.session_state["num_options"] = len(options_raw)

# 전력 선택 목록
power_choices = ["선택 안함"] + [f"{w}W" for w in range(100, 1000, 100)] + [f"{k}kW" for k in range(1, 11)]

# -----------------------------
# Compute table
# -----------------------------
rows = []
n = max(1, st.session_state["num_options"])

for i in range(n):
    opt_name = options_raw[i] if i < len(options_raw) else f"옵션 {i+1}"

    # 간단히 동일 출력값을 먼저 적용(옵션별 세부 선택은 하단에서 가능하도록 확장 가능)
    pcol1, pcol2 = st.columns([3, 1.2])
    with pcol1:
        opt_name = st.text_input(f"옵션명 {i+1}", value=opt_name, key=f"opt_name_{i}")
    with pcol2:
        p = st.selectbox(f"출력용량 {i+1}", options=power_choices, index=power_choices.index("선택 안함"),
                         key=f"power_{i}")

    # 계산 (치수 입력된 경우에만)
    vol_5000 = vol_weight(dims, allowance_cm_fixed, 5000)
    vol_6000 = vol_weight(dims, allowance_cm_fixed, 6000)

    rows.append({
        "option_name": opt_name,
        "product_name": product_name,
        "category": "small_elec",
        "capacity_L": 0,
        "power_kW": (p.replace("kW", "") if "kW" in p else ("0" if p == "선택 안함" else "0")),
        "box_cm": box_str,
        "vol_5000": vol_5000 if vol_5000 is not None else "",
        "vol_6000": vol_6000 if vol_6000 is not None else "",
    })

st.markdown("---")

df = pd.DataFrame(rows)
st.dataframe(df, use_container_width=True, height=280)

# -----------------------------
# Save / Download
# -----------------------------
excel_bytes = to_excel_bytes(df)
st.download_button("결과를 Excel로 저장", data=excel_bytes, file_name="weightbot_results.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

st.caption("※ 요청 반영: L/W/H 입력칸은 0.00 없이 공란, '사량여유(+cm)'는 고정 2.5cm(수정 불가).")
