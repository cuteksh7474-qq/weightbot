
# -*- coding: utf-8 -*-
import io
from datetime import datetime

import numpy as np
import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

st.set_page_config(page_title="WeightBot • 무게/치수 계산", layout="wide")

# =====================
# 스타일(컴팩트 UI)
# =====================
st.markdown(
    """
    <style>
    /* 전체 폰트 크기 소폭 축소 */
    html, body, [class*="css"] {font-size: 15px;}
    /* 입력창 높이/패딩 축소 */
    .stTextInput > div > div > input,
    .stNumberInput input {
        height: 2.0rem !important;
        padding: 0.1rem 0.5rem !important;
        font-size: 0.95rem !important;
    }
    .stSelectbox div[data-baseweb="select"] > div { min-height: 2.0rem !important; }
    .stSelectbox div[data-baseweb="select"] span { font-size: 0.95rem !important; }
    .stButton>button { padding: 0.2rem 0.6rem !important; font-size: 0.9rem !important; }
    /* 라벨 간격 줄이기 */
    label, .st-emotion-cache-q8sbsg, .st-emotion-cache-1catygn  { margin-bottom: 0.1rem !important; }
    .block-container { padding-top: 1rem; padding-bottom: 2rem; }
    /* 열 간격 약간 축소 */
    .st-emotion-cache-1r6slb0 { gap: 0.5rem !important; }
    </style>
    """,
    unsafe_allow_html=True,
)

st.title("📦 WeightBot · 치수/무게 추정")

# ========= 세션 초기값 =========
if "base_dims" not in st.session_state:
    st.session_state.base_dims = {"L": None, "W": None, "H": None}
if "num_options" not in st.session_state:
    st.session_state.num_options = 1
if "allowance" not in st.session_state:
    st.session_state.allowance = 2.5

# ========= 상단 입력: L/W/H + 사량여유 =========
c1, c2 = st.columns([2, 1])
with c1:
    st.subheader("치수(cm)")
    L = st.text_input("가로 L (cm)", value="", placeholder="예: 30.0", key="L_input")
    W = st.text_input("세로 W (cm)", value="", placeholder="예: 30.0", key="W_input")
    H = st.text_input("높이 H (cm)", value="", placeholder="예: 25.0", key="H_input")

with c2:
    st.subheader("사량여유(+cm)")
    allowance = st.number_input("값(수정 가능)", min_value=0.0, value=2.5, step=0.1, key="allow_input")
    st.caption("기본 2.5cm (사용자 수정 가능)")

# 엔터키로 다음 칸 이동 (L→W→H→L)
components.html(
    """
    <script>
    (function(){
        const doc = window.parent.document;
        function onKey(e){
            if(e.key === "Enter"){
                const inputs = Array.from(doc.querySelectorAll("input"))
                    .filter(n => ["text","number"].includes(n.type));
                const idx = inputs.indexOf(doc.activeElement);
                if(idx > -1){
                    e.preventDefault();
                    const next = inputs[(idx + 1) % inputs.length];
                    next.focus();
                    if(next.select){ next.select(); }
                }
            }
        }
        doc.addEventListener("keydown", onKey, true);
    })();
    </script>
    """,
    height=0,
)

# 파싱 함수
def f2(x):
    if x is None or x == "":
        return None
    try:
        return float(str(x).strip())
    except Exception:
        return None

L_val, W_val, H_val = f2(L), f2(W), f2(H)
st.session_state.base_dims = {"L": L_val, "W": W_val, "H": H_val}
st.session_state.allowance = float(allowance)

st.divider()

# ========= 옵션 개수 설정 (드롭다운 1~10 + 직접입력) =========
st.markdown("##### 옵션 개수")
colA, colB = st.columns([1, 1])
with colA:
    sugg = st.selectbox("빠른 선택", options=list(range(1, 11)), index=st.session_state.num_options-1)
with colB:
    manual = st.number_input("직접 입력(11 이상도 가능)", min_value=1, value=st.session_state.num_options, step=1)
num_options = int(manual if manual else sugg)
st.session_state.num_options = num_options

st.caption("※ 처음 옵션의 L/W/H는 상단 입력값을 기본으로 가져오며, 이후 옵션은 앞 옵션 값을 기본으로 이어받습니다.")

# ========= 옵션들 입력 =========
options_data = []
for idx in range(1, num_options + 1):
    with st.expander(f"옵션 {idx}", expanded=(idx == 1)):
        c0, c1, c2, c3 = st.columns([1.2, 1.8, 1.2, 1.2])
        with c0:
            code = st.text_input("옵션코드", value=f"OPT-{idx:02d}", key=f"code_{idx}")
        with c1:
            name = st.text_input("옵션명", value=f"옵션 {idx}", key=f"name_{idx}")

        # 기본 치수: 첫 옵션은 상단 입력값, 그 다음부터는 이전 옵션의 값을 기본으로
        if idx == 1:
            base_L = st.session_state.base_dims["L"]
            base_W = st.session_state.base_dims["W"]
            base_H = st.session_state.base_dims["H"]
        else:
            prev = options_data[-1]
            base_L, base_W, base_H = prev["L"], prev["W"], prev["H"]

        with c2:
            L_i = st.number_input("L(cm)", value=base_L if base_L is not None else 0.0, min_value=0.0, step=0.1, key=f"L_{idx}")
            W_i = st.number_input("W(cm)", value=base_W if base_W is not None else 0.0, min_value=0.0, step=0.1, key=f"W_{idx}")
        with c3:
            H_i = st.number_input("H(cm)", value=base_H if base_H is not None else 0.0, min_value=0.0, step=0.1, key=f"H_{idx}")

        # 출력용량(kW): 0.5~5.0(0.5 step) + 직접입력
        st.markdown("###### 출력용량(kW)")
        colp1, colp2 = st.columns([1.3, 1])
        with colp1:
            preset_labels = [f"{x:.1f} kW" for x in np.arange(0.5, 5.0 + 0.5, 0.5)]
            choice = st.selectbox("드롭다운", options=["선택 안함"] + preset_labels + ["직접 입력"], index=0, key=f"p_sel_{idx}")
        with colp2:
            custom = None
            if choice == "직접 입력":
                custom = st.number_input("임의 입력", min_value=0.0, step=0.1, key=f"p_custom_{idx}")
        if choice == "선택 안함":
            power_kw = custom if custom is not None else 0.0
        elif choice == "직접 입력":
            power_kw = custom if custom is not None else 0.0
        else:
            power_kw = float(choice.replace(" kW",""))

        options_data.append(
            {
                "idx": idx,
                "code": code.strip(),
                "name": name.strip(),
                "L": float(L_i),
                "W": float(W_i),
                "H": float(H_i),
                "power_kW": float(power_kw),
            }
        )

st.divider()

# ========= 결과표 & 계산 =========
def add_allowance(l, w, h, allow):
    # 사량여유는 각 변에 +allow로 단순 가정
    return (l + allow, w + allow, h + allow)

def vol_weight_cm(l, w, h, div):
    # cm 단위 부피중량(kg) 계산: (L*W*H)/div
    return round((l * w * h) / div, 2)

records = []
for row in options_data:
    l2, w2, h2 = add_allowance(row["L"], row["W"], row["H"], st.session_state.allowance)
    rec = {
        "option_code": row["code"],
        "option_name": row["name"],
        "box_cm": f"{l2:.1f}x{w2:.1f}x{h2:.1f}",
        "power_kW": row["power_kW"],
        "vol_5000": vol_weight_cm(l2, w2, h2, 5000.0),
        "vol_6000": vol_weight_cm(l2, w2, h2, 6000.0),
        "net_kg": np.nan,
        "gross_kg": np.nan,
        "confidence": 85,
    }
    records.append(rec)

df = pd.DataFrame(records)

st.subheader("결과표")
st.dataframe(df, use_container_width=True, hide_index=True)

# ========= 저장(엑셀) =========
buf = io.BytesIO()
with pd.ExcelWriter(buf, engine="xlsxwriter") as writer:
    df.to_excel(writer, index=False, sheet_name="results")
st.download_button(
    "결과를 Excel로 저장",
    data=buf.getvalue(),
    file_name=f"weightbot_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
)

st.caption("※ 사량여유(+cm)는 기본 2.5로 표시되지만, 우측에서 수정한 값이 즉시 반영됩니다.")

st.divider()

# ========= 피드백 입력(실측 무게) =========
st.subheader("피드백 입력(실측 무게 반영)")
with st.form("feedback_form", clear_on_submit=True):
    f_code = st.text_input("옵션코드", placeholder="OPT-01")
    f_net = st.number_input("실측 순중량(kg)", min_value=0.0, step=0.01, value=0.0)
    f_gross = st.number_input("실측 총중량(kg)", min_value=0.0, step=0.01, value=0.0)
    sent = st.form_submit_button("저장")
    if sent:
        try:
            fb = pd.DataFrame(
                [{
                    "time": datetime.now().isoformat(timespec="seconds"),
                    "option_code": f_code.strip(),
                    "net_kg": f_net,
                    "gross_kg": f_gross,
                }]
            )
            # 로컬 CSV 추가 저장
            try:
                old = pd.read_csv("feedback.csv")
                fb_all = pd.concat([old, fb], ignore_index=True)
            except Exception:
                fb_all = fb
            fb_all.to_csv("feedback.csv", index=False, encoding="utf-8-sig")
            st.success("피드백이 저장되었습니다 (feedback.csv).")
        except Exception as e:
            st.error(f"저장 중 오류: {e}")

# ========= 디버그(현재 값 미리보기) =========
with st.expander("현재 값 미리보기", expanded=False):
    st.json(
        {
            "L(cm)": L_val,
            "W(cm)": W_val,
            "H(cm)": H_val,
            "사량여유(cm)": st.session_state.allowance,
            "옵션수": num_options,
            "power_kW(1번옵션)": options_data[0]["power_kW"] if options_data else None,
        }
    )
