
# -*- coding: utf-8 -*-
"""
weightbot_patch_app.py
----------------------
기존 앱을 건드리지 않고, '입력 UX 개선 + 현실 추정 무게계산 + 이미지 업로더'만 포함한
경량 보조 앱입니다. 이 파일 단독으로 실행/배포하셔도 되고, 원 앱에 참고용으로 쓰셔도 됩니다.
"""
from __future__ import annotations
import io
import pandas as pd
import streamlit as st

from weightbot_ui_patch import enable_enter_to_next_and_shorten, estimate_weight

st.set_page_config(page_title="WeightBot · 보조앱", layout="centered")
st.title("📦 WeightBot · 치수 입력(보조앱)")
st.caption("입력 UX(엔터로 이동/좁은 폭) + 현실적인 무게 추정 + 이미지 드래그&업로드만 포함한 간단 버전입니다. "
           "원래 앱 기능은 그대로 두고 병행 테스트용으로 쓰세요.")

enable_enter_to_next_and_shorten(input_width_px=220)

with st.expander("상품/스펙 이미지 업로드 (여러 장 가능, 중국어 OK)", expanded=True):
    imgs = st.file_uploader("여기로 드래그하거나 클릭해서 업로드하세요", type=["png","jpg","jpeg","webp"], accept_multiple_files=True)
    if imgs:
        st.write(f"업로드 {len(imgs)}장")
        cols = st.columns(min(3, len(imgs)))
        for i, img in enumerate(imgs):
            cols[i % len(cols)].image(img, caption=img.name, use_column_width=True)

st.subheader("치수(cm) + 사량여유 + 출력용량")
c1, c2 = st.columns([1.1, 1])

with c1:
    L = st.text_input("가로 L(cm)", key="len_cm", placeholder="예: 30.0")
    W = st.text_input("세로 W(cm)", key="wid_cm", placeholder="예: 30.0")
    H = st.text_input("높이 H(cm)", key="hei_cm", placeholder="예: 25.0")

with c2:
    clr = st.number_input("사량여유(+cm)", min_value=0.0, max_value=20.0, step=0.1, value=2.5, format="%.2f")
    quick = st.selectbox("출력용량(빠른 선택, kW)", [None] + [x/2 for x in range(1, 11)], index=5, help="0.5~5.0kW 범위 빠른 선택")
    pkw = st.number_input("출력용량 직접 입력(kW)", min_value=0.0, max_value=50.0, step=0.1, value=float(quick or 0.0))
    cat = st.selectbox("카테고리", ["small_elec","metal_tool","plastic"], index=0)

res = estimate_weight(L, W, H, clearance_cm=clr, power_kw=pkw, category=cat)

st.subheader("결과 미리보기")
df = pd.DataFrame([{
    "L(cm)": L or None,
    "W(cm)": W or None,
    "H(cm)": H or None,
    "clearance_cm": clr,
    "box_cm": res["box_cm"],
    "net_kg": res["net_kg"],
    "gross_kg": res["gross_kg"],
}])
st.dataframe(df, use_container_width=True, hide_index=True)

mem = io.BytesIO()
with pd.ExcelWriter(mem, engine="xlsxwriter") as writer:
    df.to_excel(writer, index=False, sheet_name="weight_est")
mem.seek(0)
st.download_button("결과를 Excel로 저장", data=mem, file_name="weight_est.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

st.markdown("---")
st.subheader("피드백(실측 무게를 알게 되면 적어주세요)")
fb = st.text_input("예: 옵션2 순중량 18.2kg, 박스 20.4kg")
if st.button("피드백 저장(로컬 세션)"):
    st.session_state.setdefault("feedbacks", []).append(fb)
    st.success("세션에 저장했습니다. (배포용 저장은 기존 앱의 구글시트 연동을 사용하세요)")
if st.session_state.get("feedbacks"):
    st.write("최근 피드백:", st.session_state["feedbacks"][-3:])
