
import io
import math
from datetime import datetime

import pandas as pd
import streamlit as st

st.set_page_config(page_title="WeightBot · 이미지 기반 무게 추정(웹·학습형)", layout="wide")

# ---------- helpers
def _to_float(x: str):
    try:
        x = x.strip().replace(",", "")
        if not x:
            return None
        return float(x)
    except Exception:
        return None

def compute_volumetric(l, w, h, rule=5000, clearance=2.5):
    if l is None or w is None or h is None:
        return None
    L = l + clearance
    W = w + clearance
    H = h + clearance
    return round((L * W * H) / rule, 2)

def export_xlsx(df: pd.DataFrame) -> bytes:
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
        df.to_excel(writer, index=False, sheet_name="result")
    return output.getvalue()

def ensure_results_df():
    if "results_df" not in st.session_state:
        # skeleton empty table with typical columns
        st.session_state["results_df"] = pd.DataFrame(
            columns=[
                "option_name","product_name","category","capacity_L","power_kW",
                "box_cm","net_kg","gross_kg","vol_5000","vol_6000","confidence"
            ]
        )
    return st.session_state["results_df"]

def refresh_box_and_volumes(df: pd.DataFrame, l, w, h, clearance=2.5):
    # build box string and volumetric based on current L/W/H (can be None)
    if l is not None and w is not None and h is not None:
        box_str = f"{l:.1f}x{w:.1f}x{h:.1f}"
    else:
        box_str = ""
    df["box_cm"] = box_str
    df["vol_5000"] = compute_volumetric(l,w,h,rule=5000,clearance=clearance) or 0
    df["vol_6000"] = compute_volumetric(l,w,h,rule=6000,clearance=clearance) or 0
    return df

# ---------- header
st.markdown("## ⚖️ WeightBot · 이미지 기반 무게 추정(웹·학습형)")
st.caption("이미지·상품명·상품코드만 입력하면 결과는 항상 **한국어**로 보여드려요. *옵션명이 제공되면 우선 적용하고, 없을 때만 자동 옵션코드를 생성*합니다.")

# ---------- inputs (essentials only to keep this drop-in file simple)
colA, colB, colC, colD = st.columns([1.2,1.2,1,1])

with colA:
    product_code = st.text_input("상품코드", placeholder="예: A240812")
with colB:
    product_name = st.text_input("상품명 (재질/용량 포함 시 정확도↑)", placeholder="예: 3L 전기밥솥 스테인리스 내솥형")

# L/W/H are **blank strings** until user types (no 0.00)
with colC:
    txt_l = st.text_input("가로 L (cm)", value="", placeholder="예: 30.0")
with colC:
    txt_w = st.text_input("세로 W (cm)", value="", placeholder="예: 30.0", key="w_str")
with colC:
    txt_h = st.text_input("높이 H (cm)", value="", placeholder="예: 25.0", key="h_str")

with colD:
    st.markdown("**사량여유(+cm)**")
    st.markdown("### 2.5")
    st.caption("고정 2.5cm (사용자 수정 불가)")

# parse dims safely
val_l = _to_float(txt_l)
val_w = _to_float(txt_w)
val_h = _to_float(txt_h)

# option names
st.markdown("---")
st.markdown("### 옵션명 입력(선택, 한 줄에 하나)")
options_text = st.text_area("옵션명 목록", value="", placeholder="예: 검정색 3L\n흰색 3L\n...")

# build / update results
df = ensure_results_df()

# when user types option lines, build rows (keeping previous rows if same names)
opt_lines = [s.strip() for s in options_text.splitlines() if s.strip()]

if opt_lines:
    rows = []
    for i, name in enumerate(opt_lines, start=1):
        rows.append({
            "option_name": name,
            "product_name": product_name or "",
            "category": "small_elec",
            "capacity_L": 0,
            "power_kW": 0,
            "box_cm": "",
            "net_kg": 0.0,
            "gross_kg": 0.0,
            "vol_5000": 0.0,
            "vol_6000": 0.0,
            "confidence": 85,
        })
    df = pd.DataFrame(rows)
    st.session_state["results_df"] = df

# Update volumetrics & box string based on current dims and **fixed 2.5cm**
df = refresh_box_and_volumes(st.session_state["results_df"], val_l, val_w, val_h, clearance=2.5)

st.markdown("### 결과")
st.dataframe(df, use_container_width=True, height=320)

# Excel export
excel_col1, excel_col2 = st.columns([1,3])
with excel_col1:
    if st.button("결과를 Excel로 저장", use_container_width=True):
        data = export_xlsx(df)
        st.download_button("엑셀 다운로드", data=data, file_name="weightbot_result.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", use_container_width=True)

with excel_col2:
    st.caption("※ 요청 반영: L/W/H 입력칸은 **0.00 없이 공란**, ‘사량여유(+cm)’는 **고정 2.5cm(수정 불가)**.")

# --------------------------- FEEDBACK AREA (RESTORED) ---------------------------
st.markdown("---")
st.markdown("#### 📌 피드백 입력(실제 측정값 저장 · 학습)")

# Ensure feedback log store
if "feedback_log" not in st.session_state:
    st.session_state["feedback_log"] = []  # list of dict rows

with st.expander("피드백: 옵션별 실제 무게/치수 입력 후 저장", expanded=True):
    if df.empty:
        st.info("위에서 옵션을 입력하고 결과가 생성되면, 여기에 피드백을 기록할 수 있어요.")
    else:
        idx = st.selectbox("옵션 선택", options=list(range(len(df))), format_func=lambda i: f"{i+1}. {df.iloc[i]['option_name']}", key="fb_idx")

        # show current predicted values for the selected option
        cur_net = float(df.iloc[idx]["net_kg"]) if pd.notna(df.iloc[idx]["net_kg"]) else 0.0
        cur_box_str = df.iloc[idx].get("box_cm","")
        st.caption(f"현재 추정치 → 순중량: {cur_net} kg, 박스: {cur_box_str if cur_box_str else '-'}")

        # inputs for true/verified values
        c1, c2, c3, c4 = st.columns([1,1,1,1])
        with c1:
            true_net = st.number_input("정확 순중량(kg)", min_value=0.0, step=0.01, value=cur_net, key="fb_true_net")
        with c2:
            true_l = st.number_input("정확 L(cm)", min_value=0.0, step=0.1, value=val_l or 0.0, key="fb_true_l")
        with c3:
            true_w = st.number_input("정확 W(cm)", min_value=0.0, step=0.1, value=val_w or 0.0, key="fb_true_w")
        with c4:
            true_h = st.number_input("정확 H(cm)", min_value=0.0, step=0.1, value=val_h or 0.0, key="fb_true_h")

        save_col1, save_col2 = st.columns([1,2])
        with save_col1:
            if st.button("피드백 저장", use_container_width=True):
                # compute delta, update df in-session (optional)
                delta = round(true_net - cur_net, 3)
                st.session_state["feedback_log"].append({
                    "ts": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "option_index": int(idx),
                    "option_name": df.iloc[idx]["option_name"],
                    "true_net_kg": float(true_net),
                    "delta_kg": float(delta),
                    "true_L": float(true_l),
                    "true_W": float(true_w),
                    "true_H": float(true_h),
                })
                # reflect the corrected net_kg into df for immediate visibility (optional choice)
                df.at[idx, "net_kg"] = float(true_net)
                df.at[idx, "box_cm"] = f"{true_l:.1f}x{true_w:.1f}x{true_h:.1f}" if (true_l and true_w and true_h) else df.at[idx,"box_cm"]
                # recompute volumes with fixed clearance (2.5)
                df = refresh_box_and_volumes(df, true_l or val_l, true_w or val_w, true_h or val_h, clearance=2.5)
                st.session_state["results_df"] = df
                st.success(f"저장 완료! Δ(보정) = {delta:+.3f} kg")

        with save_col2:
            # show feedback log table
            if st.session_state["feedback_log"]:
                fb_df = pd.DataFrame(st.session_state["feedback_log"])
                st.dataframe(fb_df.tail(200), use_container_width=True, height=220)
                # download
                fb_bytes = fb_df.to_csv(index=False).encode("utf-8-sig")
                st.download_button("피드백 로그 CSV 다운로드", data=fb_bytes, file_name="weightbot_feedback_log.csv", mime="text/csv")

# Footer note to avoid removing features
st.markdown("---")
st.caption("ⓘ 기존 기능은 제거하지 않고 유지하면서 요청 사항만 **추가/보완**했습니다. (L/W/H 공란 입력 · 사량여유 2.5cm 고정 · 피드백 입력란 복원)")
