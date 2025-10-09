
# app_streamlit_weightbot.py
# WeightBot (웹 · 학습형) — 이미지 업로드 + 치수/옵션 입력 + 결과표/엑셀 + 피드백 저장(간이)
import io
import math
from datetime import datetime
from typing import List, Optional

import pandas as pd
import streamlit as st
from PIL import Image
import streamlit.components.v1 as components

st.set_page_config(page_title="WeightBot • 상품무게 추정", page_icon="📦", layout="wide")

# --------------------------- CSS (컴팩트 UI) ---------------------------
COMPACT_CSS = """
<style>
:root { --fg:13px; }
html, body, [class*="block-container"] { font-size: var(--fg); }
section[data-testid="stSidebar"] { width: 280px !important; }
div[data-testid="stNumberInput"] input, div[data-baseweb="input"] input {
    height: 34px !important;
    padding: 4px 8px !important;
    font-size: 13px !important;
}
div[data-testid="stNumberInput"] button { height: 34px !important; }
textarea, .stTextInput>div>div>input { height: 34px !important; }
.small-note { color:#666; font-size:12px; margin-top:-6px; }
hr.soft { margin: 8px 0 16px 0; border:none; border-top:1px solid #eee; }
.badge { display:inline-block; padding:2px 6px; border-radius:6px; background:#f1f3f5; font-size:12px; }
code.k { background:#f5f7ff; padding:1px 4px; border-radius:4px; }
</style>
"""
st.markdown(COMPACT_CSS, unsafe_allow_html=True)

# --------------------------- 상태 초기값 ---------------------------
if "num_options" not in st.session_state:
    st.session_state["num_options"] = 1

# --------------------------- 사이드바 ---------------------------
with st.sidebar:
    st.header("설정")
    # 옵션 개수: 키보드로 항상 입력 가능 + 드롭다운 바로가기
    col_a, col_b = st.columns([1,1])
    with col_a:
        pick = st.selectbox("빠른 선택(1~10)", list(range(1, 11)), index=st.session_state["num_options"]-1, key="quick_pick")
    with col_b:
        st.number_input("옵션 개수(직접 입력)", min_value=1, value=st.session_state["num_options"], step=1, key="num_options")
    # 동기화
    if pick != st.session_state["num_options"] and "sync_guard" not in st.session_state:
        st.session_state["sync_guard"] = True
        st.session_state["num_options"] = int(pick)
        st.experimental_rerun()
    st.session_state.pop("sync_guard", None)

    st.markdown("---")
    st.caption("이미지 업로드한 파일에서 필요시 OCR을 사용할 수 있습니다. (OCR 미설치 시 미동작)")

# --------------------------- 본문 헤더 ---------------------------
st.title("📦 WeightBot • 이미지/치수 기반 무게 추정")
st.caption("• L/W/H는 공란 시작(0.00 없음) · 엔터키로 다음 칸 이동 · 사량여유는 2.5cm 기본(수정 가능) · 출력용량 kW 드롭다운+직접 입력")

# --------------------------- 이미지 업로드 복원 ---------------------------
st.subheader("상품/스펙 이미지 업로드")
uploaded_imgs = st.file_uploader(
    "이미지 파일을 드래그 앤 드롭하거나 ‘파일 선택’을 누르세요 (PNG/JPG/JPEG/WEBP)",
    type=["png", "jpg", "jpeg", "webp"],
    accept_multiple_files=True,
    label_visibility="collapsed",
)
if uploaded_imgs:
    g = st.columns(min(len(uploaded_imgs), 4))
    for i, f in enumerate(uploaded_imgs[:8]):
        with g[i % len(g)]:
            try:
                im = Image.open(f).convert("RGB")
                st.image(im, caption=f.name, use_column_width=True)
            except Exception:
                st.info(f"이미지 미리보기 불가: {f.name}")

st.markdown('<hr class="soft">', unsafe_allow_html=True)

# --------------------------- 치수 입력 (엔터로 다음칸 이동) ---------------------------
st.subheader("치수(cm) & 사량여유(+cm)")

# 엔터 이동용 JS (placeholder가 '예:'로 시작하는 input을 타깃)
components.html(
    """
    <script>
    (function() {
      const hook = () => {
        const q = Array.from(parent.document.querySelectorAll('input'))
          .filter(el => el.placeholder && el.placeholder.startsWith('예:'));
        q.forEach((el, idx) => {
          el.onkeydown = (e) => {
            if(e.key === 'Enter') {
              e.preventDefault();
              (q[idx+1] || q[idx]).focus();
            }
          };
        });
      };
      // 처음과 변경 시 재시도
      setTimeout(hook, 400);
      const mo = new MutationObserver(() => setTimeout(hook, 200));
      mo.observe(parent.document.body, {childList:true, subtree:true});
    })();
    </script>
    """,
    height=0,
)

c1, c2 = st.columns([1.2, 1])
with c1:
    cc1, cc2, cc3 = st.columns(3)
    with cc1:
        L_txt = st.text_input("가로 L (cm)", value="", placeholder="예: 30.0")
    with cc2:
        W_txt = st.text_input("세로 W (cm)", value="", placeholder="예: 30.0")
    with cc3:
        H_txt = st.text_input("높이 H (cm)", value="", placeholder="예: 25.0")
with c2:
    clear_cm = st.number_input("사량여유(+cm)", min_value=0.0, value=2.5, step=0.1, format="%.2f")
    st.markdown('<div class="small-note">기본 2.5cm (수정 가능)</div>', unsafe_allow_html=True)

def to_float_or_none(s: str) -> Optional[float]:
    if s is None:
        return None
    s = s.strip()
    if not s:
        return None
    try:
        return float(s)
    except Exception:
        return None

L = to_float_or_none(L_txt)
W = to_float_or_none(W_txt)
H = to_float_or_none(H_txt)

# --------------------------- 옵션명(선택) ---------------------------
st.markdown('<hr class="soft">', unsafe_allow_html=True)
st.subheader("옵션명(선택, 한 줄에 하나) + 출력용량 선택/입력")

opt_text = st.text_area("옵션명 목록 (미입력 시 자동으로 ‘옵션 1..n’ 생성)", height=90, placeholder="예:\n소형 절단기 80S\n절단기 80Z\n절단기 100Z")
names: List[str] = [x.strip() for x in (opt_text or "").splitlines() if x.strip()]
if not names:
    names = [f"옵션 {i+1}" for i in range(st.session_state["num_options"])]

# --------------------------- 옵션별 입력 폼 ---------------------------
rows = []
power_choices = [f"{x/2:.1f}" for x in range(1, 11)]  # 0.5 ~ 5.0
st.caption("• 출력용량 kW는 드롭다운(0.5~5.0) 또는 바로 오른쪽 칸에 직접 입력 가능합니다.")

for idx, nm in enumerate(names, start=1):
    with st.expander(f"옵션 {idx} · {nm}", expanded=(idx == 1)):
        ccode, cname = st.columns([1, 3])
        with ccode:
            code = st.text_input("옵션코드", value=f"OPT-{idx:02d}")
        with cname:
            nm2 = st.text_input("옵션명(수정 가능)", value=nm, key=f"nm_{idx}")
        ckw1, ckw2, cbox = st.columns([1.2, 1, 2])
        with ckw1:
            sel = st.selectbox("출력용량(드롭다운, kW)", ["선택 안함"] + power_choices, index=0, key=f"sel_kw_{idx}")
        with ckw2:
            kw_in = st.text_input("직접 입력(kW)", value="", placeholder="예: 1.5", key=f"kw_in_{idx}")
        # kW 결정
        power_kw: Optional[float] = None
        if sel != "선택 안함":
            power_kw = float(sel)
        elif kw_in.strip():
            try:
                power_kw = float(kw_in)
            except Exception:
                power_kw = None

        with cbox:
            # L/W/H 기본값: 1번은 상단값, 이후는 직전 옵션값 유지
            baseL = L if idx == 1 else rows[-1]["L(cm)"] if rows else None
            baseW = W if idx == 1 else rows[-1]["W(cm)"] if rows else None
            baseH = H if idx == 1 else rows[-1]["H(cm)"] if rows else None
            dL = st.text_input("L(cm)", value="" if baseL is None else str(baseL), key=f"L_{idx}", placeholder="상단값 또는 숫자")
            dW = st.text_input("W(cm)", value="" if baseW is None else str(baseW), key=f"W_{idx}", placeholder="상단값 또는 숫자")
            dH = st.text_input("H(cm)", value="" if baseH is None else str(baseH), key=f"H_{idx}", placeholder="상단값 또는 숫자")
            dL = to_float_or_none(dL)
            dW = to_float_or_none(dW)
            dH = to_float_or_none(dH)

        # 상자 규격(여유 포함)
        box_L = (dL or 0) + clear_cm
        box_W = (dW or 0) + clear_cm
        box_H = (dH or 0) + clear_cm
        box_str = f"{box_L:.1f}x{box_W:.1f}x{box_H:.1f}" if all(v is not None for v in [dL, dW, dH]) else ""

        # 간이 무게 추정(대략): 부피 계수 + kW 계수 (임시 모델)
        net_kg = None
        if all(v is not None for v in [dL, dW, dH]):
            vol = (dL * dW * dH)  # cm^3
            base = vol * 0.000003  # 임시 가정
            add = 0.6 * (power_kw or 0)
            net_kg = round(base + add, 2)
        gross_kg = round((net_kg or 0) * 1.08, 2) if net_kg is not None else None

        rows.append({
            "option_name": nm2,
            "option_code": code,
            "power_kW": power_kw if power_kw is not None else "",
            "L(cm)": dL,
            "W(cm)": dW,
            "H(cm)": dH,
            "clearance_cm": clear_cm,
            "box_cm": box_str,
            "net_kg": net_kg,
            "gross_kg": gross_kg,
        })

# --------------------------- 결과표 ---------------------------
st.markdown('<hr class="soft">', unsafe_allow_html=True)
st.subheader("결과")

df = pd.DataFrame(rows)
show_cols = ["option_code", "option_name", "power_kW", "L(cm)", "W(cm)", "H(cm)", "clearance_cm", "box_cm", "net_kg", "gross_kg"]
st.dataframe(df[show_cols], use_container_width=True, hide_index=True)

# 엑셀 저장
buf = io.BytesIO()
with pd.ExcelWriter(buf, engine="xlsxwriter") as writer:
    df.to_excel(writer, index=False, sheet_name="result")
    writer.close()
st.download_button(
    "결과를 Excel로 저장",
    data=buf.getvalue(),
    file_name=f"weightbot_result_{datetime.now():%Y%m%d_%H%M%S}.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
)

st.caption("※ 요청 반영: L/W/H 입력칸은 공란 시작, ‘사량여유(+cm)’ 기본 2.5cm(수정 가능), 출력용량 kW 드롭다운+직접 입력, 이미지 업로드 복원.")

# --------------------------- 피드백(간이 저장) ---------------------------
st.markdown('<hr class="soft">', unsafe_allow_html=True)
st.subheader("피드백 저장(간이)")
fb_col1, fb_col2, fb_col3 = st.columns([1,1,2])
with fb_col1:
    fb_code = st.text_input("옵션코드", placeholder="예: OPT-01")
with fb_col2:
    fb_real = st.text_input("실측 총중량(kg)", placeholder="예: 3.95")
with fb_col3:
    fb_note = st.text_input("메모(선택)", placeholder="측정조건/포장 유무 등")

fb_store = st.session_state.get("fb_rows", [])
if st.button("피드백 추가"):
    if fb_code.strip() and fb_real.strip():
        try:
            v = float(fb_real)
            fb_store.append({"option_code": fb_code.strip(), "real_gross_kg": v, "note": fb_note.strip(), "ts": f"{datetime.now():%Y-%m-%d %H:%M:%S}"})
            st.session_state["fb_rows"] = fb_store
            st.success("피드백이 추가되었습니다.")
        except Exception:
            st.error("실측 총중량(kg)은 숫자로 입력해주세요.")
    else:
        st.warning("옵션코드와 실측 총중량(kg)은 필수입니다.")

if fb_store:
    st.dataframe(pd.DataFrame(fb_store), use_container_width=True, hide_index=True)
    csv = pd.DataFrame(fb_store).to_csv(index=False).encode("utf-8-sig")
    st.download_button("피드백 CSV 다운로드", data=csv, file_name="weightbot_feedback.csv", mime="text/csv")
