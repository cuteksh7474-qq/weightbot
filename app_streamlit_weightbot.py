# -*- coding: utf-8 -*-
"""
WeightBot - 이미지 기반 무게 추정 (필요 최소 UI 버전)
- 요청 반영:
  (1) L/W/H 입력 후 Enter 키 → 다음 칸 자동 포커스 이동 (L→W→H→L)
  (2) 사량여유(+cm)는 기본 2.5로 보이지만, 사용자가 수정 가능
이 파일은 최소 실행 예시입니다. 대규모 기존 기능은 "TODO" 영역에 다시 붙여 확장하세요.
"""

import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
from datetime import datetime

st.set_page_config(page_title="WeightBot", page_icon="📦", layout="wide")

# =========================
# 헤더
# =========================
st.title("📦 WeightBot · 이미지 기반 무게 추정(웹·학습형)")
st.caption("이미지/상품명/상품코드를 입력하면 결과는 항상 **한국어**로 보여집니다. 아래 두 가지 요청 사항을 반영했습니다.")

# =========================
# 기본 입력 (상품코드/상품명/이미지)
# =========================
with st.container():
    c0, c1 = st.columns([1, 3])
    with c0:
        st.text_input("상품코드", key="prod_code", value="", placeholder="예: A240812")
    with c1:
        st.text_input("상품명 (재질/용량 포함 시 정확↑)", key="prod_name", value="", placeholder="예: 3L 전기압력솥 스테인리스 내솥형")
    
    st.file_uploader("상품/스펙 이미지 업로드 (여러 장 가능, 중국어 OK)", type=["png", "jpg", "jpeg", "webp"], accept_multiple_files=True, key="images")

st.divider()

# =========================
# (1) L/W/H Enter → 다음 칸 이동
# (2) 사량여유(+cm) = 기본 2.5 (수정 가능)
# =========================
st.subheader("치수(cm) · 사량여유(+cm)")

l_col, w_col, h_col, s_col = st.columns([1, 1, 1, 1])

with l_col:
    if "L_input" not in st.session_state:
        st.session_state["L_input"] = 0.0
    L = st.number_input("가로 L (cm)", min_value=0.0, step=0.1, format="%.2f",
                        key="L_input", placeholder="예: 66.0")

with w_col:
    if "W_input" not in st.session_state:
        st.session_state["W_input"] = 0.0
    W = st.number_input("세로 W (cm)", min_value=0.0, step=0.1, format="%.2f",
                        key="W_input", placeholder="예: 30.0")

with h_col:
    if "H_input" not in st.session_state:
        st.session_state["H_input"] = 0.0
    H = st.number_input("높이 H (cm)", min_value=0.0, step=0.1, format="%.2f",
                        key="H_input", placeholder="예: 25.0")

with s_col:
    if "slack_cm" not in st.session_state:
        st.session_state["slack_cm"] = 2.5
    slack_cm = st.number_input("사량여유(+cm)", min_value=0.0, step=0.1, format="%.1f",
                               value=st.session_state["slack_cm"], key="slack_cm_input",
                               help="기본 2.5cm, 필요 시 수정 가능")
    st.session_state["slack_cm"] = slack_cm

# --- 엔터키 포커스 이동 ---
components.html(\"\"\"\
<script>
(function(){
  function wire(){
    const inputs = {};
    document.querySelectorAll('div[data-testid=\"stNumberInput\"]').forEach(div=>{
      const label = div.querySelector('label')?.innerText?.trim() || '';
      const input = div.querySelector('input');
      if(!input) return;
      if(label.includes('가로 L')) inputs['L']=input;
      if(label.includes('세로 W')) inputs['W']=input;
      if(label.includes('높이 H')) inputs['H']=input;
    });
    const order = ['L','W','H'];
    order.forEach((k, i)=>{
      const el = inputs[k]; if(!el) return;
      el.addEventListener('keydown', e=>{
        if(e.key==='Enter'){
          e.preventDefault();
          const next = inputs[order[(i+1)%order.length]];
          if(next){ next.focus(); next.select && next.select(); }
        }
      });
    });
  }
  const obs = new MutationObserver(wire);
  obs.observe(document.body, {subtree:true, childList:true});
  wire();
})();
</script>
\"\"\", height=0)

st.info("※ 현재 설정: L/W/H는 **Enter 키로 다음 칸 이동**, 사량여유는 **기본 2.5cm(수정 가능)** 입니다.", icon="ℹ️")

st.divider()

# =========================
# TODO: 기존의 옵션/출력용량/자동코드/표/엑셀 저장/학습/피드백 로직을
#       아래 영역에 다시 붙여 확장하세요.
# =========================

st.subheader("임시 결과 미리보기 (샘플)")
vol_5000 = round(((L + slack_cm) * (W + slack_cm) * (H + slack_cm)) / 5000.0, 2) if all([L, W, H]) else 0
vol_6000 = round(((L + slack_cm) * (W + slack_cm) * (H + slack_cm)) / 6000.0, 2) if all([L, W, H]) else 0

df = pd.DataFrame([{
    "상품코드": st.session_state.get("prod_code", ""),
    "상품명": st.session_state.get("prod_name", ""),
    "L(cm)": L, "W(cm)": W, "H(cm)": H,
    "사량여유(cm)": slack_cm,
    "부피중량(5000)": vol_5000,
    "부피중량(6000)": vol_6000,
    "생성시각": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
}])

st.dataframe(df, use_container_width=True, height=220)

st.caption("※ L/W/H에 0.00이 보이면 공란처럼 사용하셔도 됩니다. 사량여유(+cm)는 기본 2.5로 넣어두었지만, 언제든지 수정 가능합니다.")

fname = f"weightbot_result_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
st.download_button("결과를 CSV로 저장", data=df.to_csv(index=False).encode("utf-8-sig"),
                   file_name=fname, mime="text/csv")
