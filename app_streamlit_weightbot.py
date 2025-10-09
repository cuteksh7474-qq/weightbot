# -*- coding: utf-8 -*-
import streamlit as st
import streamlit.components.v1 as components

st.set_page_config(page_title="WeightBot - Size Inputs", page_icon="📦", layout="centered")

st.title("📦 WeightBot · 치수 입력 테스트")

# --- session helpers ---
if "move_to" not in st.session_state:
    st.session_state.move_to = None

def set_move(target):
    st.session_state.move_to = target

# --- 1) Size inputs as text (blank allowed) ---
st.subheader("치수(cm)")

col1, col2 = st.columns(2)
with col1:
    L = st.text_input("가로 L (cm)", key="L_text", placeholder="예: 30.0", on_change=lambda: set_move("W_text"))
    W = st.text_input("세로 W (cm)", key="W_text", placeholder="예: 30.0", on_change=lambda: set_move("H_text"))
    H = st.text_input("높이 H (cm)", key="H_text", placeholder="예: 25.0", on_change=lambda: set_move("L_text"))

with col2:
    st.markdown("### 사량여유(+cm)")
    allowance = st.number_input(" ", min_value=0.0, step=0.1, value=2.5, format="%.2f", label_visibility="collapsed")
    st.caption("기본 2.5cm (수정 가능)")

# --- 2) Enter key → focus next input (L → W → H → L) ---
move_map = {"L_text": 0, "W_text": 1, "H_text": 2}
target_map = {"W_text": 1, "H_text": 2, "L_text": 0}

# If a move was requested by on_change, run a tiny JS to focus the next input
if st.session_state.move_to in target_map:
    index = target_map[st.session_state.move_to]
    components.html(f"""
    <script>
      const els = window.parent.document.querySelectorAll('input[type="text"]');
      if (els && els.length >= 3) {{
        try {{
          els[{index}].focus();
          els[{index}].select();
        }} catch(e) {{}}
      }}
    </script>
    """, height=0)
    # reset
    st.session_state.move_to = None

# --- 3) Parse numbers safely (blank allowed) ---
def to_float(x):
    try:
        x = x.strip()
        if not x:
            return None
        return float(x)
    except Exception:
        return None

L_val = to_float(L)
W_val = to_float(W)
H_val = to_float(H)

st.divider()
st.subheader("현재 값 미리보기")
st.write({
    "L(cm)": L_val,
    "W(cm)": W_val,
    "H(cm)": H_val,
    "사량여유(cm)": allowance
})
st.info("이 파일은 '엔터키로 다음 칸 이동' + '사량여유 2.5 기본, 수정 가능'만 반영한 최소 실행 예시입니다. "
        "기존 앱의 나머지 기능은 이 파일 아래쪽(또는 주석의 TODO 지점)에 병합하세요.")
