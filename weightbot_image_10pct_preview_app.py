# -*- coding: utf-8 -*-
import io
from PIL import Image
import streamlit as st
import pandas as pd

st.set_page_config(page_title="WeightBot · 이미지/치수 기반 무게 추정", layout="wide")

# --- 헤더 ---
st.markdown("### 🧰 **WeightBot · 이미지/치수 기반 무게 추정**")
st.caption("• L/W/H는 공란 시작(0.00 없음) · 엔터키로 다음 칸 이동 · 사량여유는 2.5cm 기본(수정 가능) · 출력용량 kW 드롭다운·직접 입력")

# --- 이미지 업로드 ---
st.subheader("상품/스펙 이미지 업로드")
uploaded_file = st.file_uploader(
    "Drag and drop files here",
    type=["png", "jpg", "jpeg", "webp"],
    accept_multiple_files=False,
    label_visibility="collapsed",
)

# 미리보기: 원본의 10% 크기로 표시
if uploaded_file is not None:
    try:
        image = Image.open(uploaded_file)
        # 일부 webp/PNG는 mode 변환 필요
        if image.mode not in ("RGB", "RGBA"):
            image = image.convert("RGB")
        preview_width = max(1, int(image.width * 0.10))  # 10%로 축소
        st.image(image, width=preview_width, caption="미리보기(원본 대비 10%)")
    except Exception as e:
        st.warning(f"이미지 미리보기 중 오류: {e}")

# --- 치수 입력 (간소화 예시) ---
col1, col2 = st.columns([1,1])
with col1:
    st.markdown("#### 치수(cm)")
    L = st.text_input("가로 L (cm)", value="", placeholder="예: 30.0", key="L")
    W = st.text_input("세로 W (cm)", value="", placeholder="예: 30.0", key="W")
    H = st.text_input("높이 H (cm)", value="", placeholder="예: 25.0", key="H")

with col2:
    st.markdown("#### 사량여유(+cm)")
    clearance = st.number_input("사량여유(+cm)", min_value=0.0, step=0.5, value=2.5)
    st.caption("기본 2.5cm (수정 가능)")

# --- 출력용량 입력(드롭다운 + 직접입력) ---
st.markdown("#### 출력용량 (kW)")
kw_choices = [round(x * 0.5, 1) for x in range(1, 11)]  # 0.5~5.0
c1, c2 = st.columns([1,1])
with c1:
    kw_pick = st.selectbox("드롭다운", options=kw_choices, index=5, key="kw_pick")
with c2:
    kw_free = st.text_input("직접 입력(원하면)", value="", key="kw_free")
power_kw = kw_pick
if kw_free.strip():
    try:
        power_kw = float(kw_free)
    except:
        st.warning("직접 입력 kW는 숫자로 입력하세요.")

# --- 결과 테이블 (자리표시자) ---
st.markdown("#### 결과(예시)")
df = pd.DataFrame(
    [{
        "L(cm)": L or None,
        "W(cm)": W or None,
        "H(cm)": H or None,
        "clearance_cm": clearance,
        "power_kW": power_kw,
    }]
)
st.dataframe(df, use_container_width=True)

st.info("요청하신 대로 **업로드 이미지 미리보기는 원본의 10% 크기**로 고정해 두었습니다. 기존 기능과 함께 쓰려면 이 파일을 기존 앱 파일로 교체하세요.")
