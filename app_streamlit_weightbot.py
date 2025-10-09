
# -*- coding: utf-8 -*-
import io
import json
import math
from datetime import datetime
from typing import List, Optional, Tuple

import numpy as np
import pandas as pd
import streamlit as st
from streamlit.components.v1 import html as components_html

APP_TITLE = "WeightBot · 옵션별 무게/포장 추정"

# -------------- Helper: safe parse float from text ----------------
def fnum(x: Optional[str]) -> Optional[float]:
    if x is None:
        return None
    if isinstance(x, (int, float)):
        try:
            v = float(x)
            if math.isnan(v):
                return None
            return v
        except:
            return None
    s = str(x).strip().replace(",", "")
    if not s:
        return None
    try:
        return float(s)
    except:
        # try to extract float substrings
        import re
        m = re.search(r"[-+]?\d*\.?\d+", s)
        if m:
            try:
                return float(m.group())
            except:
                return None
    return None


# -------------- Layout ---------------
st.set_page_config(page_title=APP_TITLE, layout="wide", page_icon="📦")
st.title(APP_TITLE)

# --- Basic inputs (top) ---
colA, colB = st.columns([0.55, 0.45], gap="large")
with colA:
    st.subheader("치수(cm)")
    L = st.text_input("가로 L (cm)", placeholder="L입력", key="L_txt")
    W = st.text_input("세로 W (cm)", placeholder="W입력", key="W_txt")
    H = st.text_input("높이 H (cm)", placeholder="H입력", key="H_txt")
with colB:
    st.subheader("사량여유(+cm)")
    margin = st.number_input(" ", min_value=0.0, step=0.1, value=2.5, key="margin_cm", label_visibility="collapsed")
    st.caption("기본 2.5cm (수정 가능)")

# --- JS: Enter → 다음 칸 포커스 (L→W→H→L) ---
components_html(
    """
<script>
(function(){
  const order = ['L입력','W입력','H입력'];
  function bind(){
    try{
      order.forEach((ph, idx)=>{
        const el = window.parent.document.querySelector(`input[placeholder="${ph}"]`);
        if(el && !el.dataset.bound){
          el.dataset.bound = '1';
          el.addEventListener('keydown', (e)=>{
            if(e.key==='Enter'){
              const next = window.parent.document.querySelector(`input[placeholder="${order[(idx+1)%order.length]}"]`);
              if(next){ next.focus(); next.select(); }
              e.preventDefault();
            }
          });
        }
      });
    }catch(e){}
  }
  setInterval(bind, 400);
})();
</script>
    """,
    height=0
)

# --------- Optional: Image upload + OCR fill ---------
with st.expander("이미지 업로드 / OCR로 치수 채우기(선택)", expanded=False):
    up = st.file_uploader("제품/스펙 이미지 업로드 (PNG/JPG/WEBP)", type=["png","jpg","jpeg","webp"])
    c1,c2 = st.columns([1,1])
    with c1:
        if up:
            st.image(up, caption="업로드된 이미지 미리보기", use_container_width=True)
    with c2:
        if st.button("🧠 OCR로 채우기 (중국어/숫자 인식)", disabled=not bool(up)):
            try:
                import easyocr  # optional
                reader = easyocr.Reader(['ch_sim','en'], gpu=False)
                import numpy as np
                import PIL.Image as Image
                img = Image.open(up).convert("RGB")
                arr = np.array(img)
                results = reader.readtext(arr, detail=0)
                text = " ".join(results)
            except Exception as e:
                text = ""
                st.warning("easyocr가 설치되어 있지 않거나 런타임에서 동작하지 않습니다. 숫자 텍스트에서 추출을 시도합니다.")
                try:
                    text = up.read().decode("utf-8","ignore")
                except:
                    text = ""

            import re
            nums = re.findall(r'(\d{2,4})\s*mm', text, flags=re.IGNORECASE)
            dims = [float(n)/10.0 if float(n)>50 else float(n) for n in [*nums]]  # mm→cm
            if len(dims) >= 3:
                st.session_state["L_txt"] = f"{dims[0]:.1f}"
                st.session_state["W_txt"] = f"{dims[1]:.1f}"
                st.session_state["H_txt"] = f"{dims[2]:.1f}"
                st.success(f"OCR 결과 → L={dims[0]:.1f}, W={dims[1]:.1f}, H={dims[2]:.1f}")
                st.experimental_rerun()
            else:
                st.info("3개 치수(mm)가 충분히 인식되지 않았습니다.")

# ---------- Options count + product info ----------
st.markdown("---")
col0a, col0b = st.columns([0.7, 0.3])
with col0a:
    product_name = st.text_input("상품명/모델명", placeholder="예: 3L 전기밥솥 스테인리스 내솥형")
    product_code = st.text_input("상품코드", placeholder="예: A240812")
with col0b:
    st.write("옵션 개수 (빠른 선택)")
    bcols = st.columns(10)
    for i in range(10):
        if bcols[i].button(str(i+1)):
            st.session_state["num_options"] = i+1
    default_num = st.session_state.get("num_options", 1)
    num_options = st.number_input("직접 입력", min_value=1, step=1, value=default_num, key="num_options", label_visibility="collapsed")

st.caption("※ 빠른 선택 버튼을 눌러도 되고, 직접 입력 박스에 11 이상의 수를 적어도 됩니다.")

# ---------- Option blocks ----------
st.markdown("---")
st.subheader("옵션별 입력")

# propagate default L/W/H from top-level
topL = fnum(L)
topW = fnum(W)
topH = fnum(H)

# power list
kw_list = [0.0] + [round(x,1) for x in np.concatenate([np.arange(0.1,1.0,0.1), [1,1.5,2,2.2,2.5,3,3.5,4,5,6,7,8,9,10]])]
kw_options = [str(k).rstrip("0").rstrip(".")+"kW" if k>0 else "0" for k in kw_list]

opt_rows = []
for idx in range(int(num_options)):
    e = st.expander(f"옵션 {idx+1}", expanded=idx==0)
    with e:
        oc, on = st.columns([0.35, 0.65])
        with oc:
            opt_code = st.text_input("옵션코드", key=f"opt_code_{idx}", placeholder=f"{product_code}-{idx+1:02d}" if product_code else f"OPT-{idx+1:02d}")
        with on:
            opt_name = st.text_input("옵션명", key=f"opt_name_{idx}", placeholder=f"옵션 {idx+1} 이름")

        # per-option size (default to top-level if blank)
        cL, cW, cH, cP = st.columns([0.2,0.2,0.2,0.4])
        with cL:
            ovL = st.text_input("L(cm)", key=f"optL_{idx}", placeholder=f"{topL:.1f}" if topL else "예: 30.0")
        with cW:
            ovW = st.text_input("W(cm)", key=f"optW_{idx}", placeholder=f"{topW:.1f}" if topW else "예: 30.0")
        with cH:
            ovH = st.text_input("H(cm)", key=f"optH_{idx}", placeholder=f"{topH:.1f}" if topH else "예: 25.0")
        with cP:
            kw = st.selectbox("출력용량", options=kw_options, index=kw_options.index("0") if "0" in kw_options else 0, key=f"kw_{idx}")

        # resolve numbers
        rL = fnum(ovL) if fnum(ovL) is not None else topL
        rW = fnum(ovW) if fnum(ovW) is not None else topW
        rH = fnum(ovH) if fnum(ovH) is not None else topH
        kW = 0.0
        try:
            kW = float(kw.replace("kW","")) if "kW" in kw else float(kw)
        except:
            kW = 0.0

        opt_rows.append({
            "option_idx": idx+1,
            "option_code": opt_code or f"OPT-{idx+1:02d}",
            "option_name": opt_name or f"옵션 {idx+1}",
            "L(cm)": rL,
            "W(cm)": rW,
            "H(cm)": rH,
            "power_kW": kW
        })

# ------------- Calculation -------------
def estimate_weight(row: dict) -> Tuple[Optional[float], Optional[float]]:
    L,W,H = row["L(cm)"], row["W(cm)"], row["H(cm)"]
    if None in (L,W,H):
        return (None, None)
    volume = (L + st.session_state.get("margin_cm", 2.5)) * (W + st.session_state.get("margin_cm", 2.5)) * (H + st.session_state.get("margin_cm", 2.5))
    vol_litres = volume / 1000.0  # rough litre-like proxy

    # heuristic: base by size + bump by motor power
    base = 0.12 * vol_litres  # kg per 'litre' proxy
    bump = 0.6 * row.get("power_kW", 0.0)  # motor bump
    net = max(0.2, round(base + bump, 2))
    gross = round(net * 1.085, 2)
    return net, gross

def build_results(rows: List[dict]) -> pd.DataFrame:
    out = []
    for r in rows:
        net, gross = estimate_weight(r)
        # volumetric weights
        L,W,H = r["L(cm)"], r["W(cm)"], r["H(cm)"]
        if None not in (L,W,H):
            boxL, boxW, boxH = L+margin, W+margin, H+margin
            vol_5000 = round((boxL*boxW*boxH)/5000.0, 2)
            vol_6000 = round((boxL*boxW*boxH)/6000.0, 2)
            box_str = f"{boxL:.1f}x{boxW:.1f}x{boxH:.1f}"
        else:
            vol_5000 = None
            vol_6000 = None
            box_str = ""
        out.append({
            "option_idx": r["option_idx"],
            "option_code": r["option_code"],
            "option_name": r["option_name"],
            "category": "small_elec",
            "capacity_L": 0,
            "power_kW": r.get("power_kW",0.0),
            "box_cm": box_str,
            "net_kg": net,
            "gross_kg": gross,
            "vol_5000": vol_5000,
            "vol_6000": vol_6000,
            "confidence": 85
        })
    df = pd.DataFrame(out)
    return df

res_df = build_results(opt_rows)

# ---------- Results table & Excel export ----------
st.markdown("---")
st.subheader("결과표")
st.dataframe(res_df, use_container_width=True, hide_index=True)

def to_excel_bytes(df: pd.DataFrame) -> bytes:
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="xlsxwriter") as writer:
        df.to_excel(writer, index=False, sheet_name="results")
        ws = writer.sheets["results"]
        for i, col in enumerate(df.columns, 1):
            ws.set_column(i-1, i-1, max(12, min(40, int(df[col].astype(str).str.len().mean()+4))))
    return buf.getvalue()

st.download_button("결과를 Excel로 저장", data=to_excel_bytes(res_df), file_name=f"weightbot_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

st.caption("※ 요청 반영: L/W/H 입력칸은 0.00 없이 공란, ‘사량여유(+cm)’는 기본 2.5cm(수정 가능).")

# -------- Feedback section (persistent & optional Google Sheets) --------
st.markdown("---")
st.subheader("피드백 입력(실측 무게 반영)")
st.write("판매 후 실제 ‘순중량/총중량’을 옵션별로 알려주시면, 추정 모델 보정에 반영됩니다.")

fb_cols = ["timestamp","product_code","product_name","option_code","option_name","L","W","H","power_kW","margin_cm","net_real","gross_real"]
fb_df_show = None

with st.form("feedback_form", clear_on_submit=True):
    c1,c2,c3 = st.columns([0.35,0.35,0.3])
    with c1:
        fb_opt_code = st.text_input("옵션코드", value=res_df["option_code"].iloc[0] if len(res_df)>0 else "")
        fb_net = st.number_input("실측 순중량(kg)", min_value=0.0, step=0.01)
    with c2:
        fb_opt_name = st.text_input("옵션명", value=res_df["option_name"].iloc[0] if len(res_df)>0 else "")
        fb_gross = st.number_input("실측 총중량(kg)", min_value=0.0, step=0.01)
    with c3:
        fb_note = st.text_area("메모/비고", height=38, placeholder="선택")

    submitted = st.form_submit_button("피드백 저장")
    if submitted:
        row = {
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "product_code": product_code, "product_name": product_name,
            "option_code": fb_opt_code, "option_name": fb_opt_name,
            "L": topL, "W": topW, "H": topH, "power_kW": opt_rows[0]["power_kW"] if opt_rows else None,
            "margin_cm": margin,
            "net_real": fb_net, "gross_real": fb_gross,
        }
        # append to local CSV
        try:
            csv_path = "weight_feedback_log.csv"
            try:
                prev = pd.read_csv(csv_path)
            except:
                prev = pd.DataFrame(columns=fb_cols+["note"])
            cur = pd.DataFrame([row | {"note": fb_note}])
            new = pd.concat([prev, cur], ignore_index=True)
            new.to_csv(csv_path, index=False, encoding="utf-8-sig")
            st.success("로컬 CSV에 저장 완료: weight_feedback_log.csv")
        except Exception as e:
            st.warning(f"로컬 CSV 저장에 실패: {e}")

        # optional Google Sheets append
        if "gsheets" in st.secrets:
            try:
                import gspread
                from google.oauth2.service_account import Credentials
                scopes = ["https://www.googleapis.com/auth/spreadsheets"]
                creds_dict = dict(st.secrets["gsheets"])
                creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
                gc = gspread.authorize(creds)
                sh = gc.open_by_key(st.secrets["gsheets"]["spreadsheet_id"])
                ws = sh.worksheet(st.secrets["gsheets"].get("worksheet","weightbot"))
                ws.append_row([row.get(k,"") for k in fb_cols] + [fb_note])
                st.success("구글시트에 추가 저장 완료")
            except Exception as e:
                st.info(f"구글시트 연동은 설정되었지만 추가 실패: {e}")

# show recent feedback
try:
    fb_df_show = pd.read_csv("weight_feedback_log.csv")
    st.dataframe(fb_df_show.tail(10), use_container_width=True, hide_index=True)
except:
    pass

# ------------- Debug / preview block -------------
with st.expander("현재 값 미리보기"):
    preview = {
        "L(cm)": fnum(st.session_state.get("L_txt")),
        "W(cm)": fnum(st.session_state.get("W_txt")),
        "H(cm)": fnum(st.session_state.get("H_txt")),
        "사량여유(cm)": st.session_state.get("margin_cm", 2.5),
        "옵션 수": int(num_options),
    }
    st.json(preview)

# ------------- Footer note -------------
st.info("이 앱은 기존 기능(결과표, Excel 저장, 피드백 입력)을 유지하면서, ‘엔터키로 다음 칸 이동’과 ‘사량여유 2.5 기본(수정 가능)’을 반영했습니다.")
