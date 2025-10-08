# -*- coding: utf-8 -*-
import streamlit as st
from PIL import Image, ImageOps, ImageEnhance
import io, json, time, re
import pandas as pd
import streamlit.components.v1 as components

# ---------- Optional OCR ----------
HAS_OCR=False
try:
    import easyocr, numpy as np
    HAS_OCR=True
except Exception:
    HAS_OCR=False

st.set_page_config(page_title="WeightBot · 이미지 기반 무게 추정", page_icon="⚖️", layout="wide")

# ---------- Storage ----------
LOCAL_DB="feedback_db.json"          # 피드백(실측) 저장
HISTORY_DB="estimate_history.json"   # 모든 조회 결과 자동 저장

def load_json(path, default):
    try:
        with open(path,"r",encoding="utf-8") as f:
            return json.load(f)
    except:
        return default

def save_json(path, data):
    try:
        with open(path,"w",encoding="utf-8") as f:
            json.dump(data,f,ensure_ascii=False,indent=2)
    except:
        pass

def load_local_db():
    return load_json(LOCAL_DB, {})

def save_local_db(d):
    save_json(LOCAL_DB, d)

def load_history():
    return load_json(HISTORY_DB, [])

def save_history(items):
    save_json(HISTORY_DB, items)

# ---------- Google Sheets (optional) ----------
def _gs_client():
    """Create gspread client from Streamlit secrets. Return (client, error)."""
    try:
        import gspread
        from google.oauth2.service_account import Credentials
        sa = st.secrets.get("gcp_service_account")
        if not sa:
            return None, "Streamlit Secrets에 'gcp_service_account'가 없습니다."
        scopes = ["https://www.googleapis.com/auth/spreadsheets",
                  "https://www.googleapis.com/auth/drive"]
        creds = Credentials.from_service_account_info(dict(sa), scopes=scopes)
        gc = gspread.authorize(creds)
        return gc, None
    except Exception as e:
        return None, str(e)

def gsheets_append(df: pd.DataFrame):
    """Append dataframe rows to Google Sheet defined in secrets.gsheets.*"""
    try:
        import gspread
        cfg = st.secrets.get("gsheets", {})
        ssid = cfg.get("spreadsheet_id")
        ws_name = cfg.get("worksheet", "weightbot")
        if not ssid:
            return "Streamlit Secrets 'gsheets.spreadsheet_id'가 없습니다."
        gc, err = _gs_client()
        if err: return err
        sh = gc.open_by_key(ssid)
        try:
            ws = sh.worksheet(ws_name)
        except gspread.WorksheetNotFound:
            ws = sh.add_worksheet(ws_name, rows="2000", cols="40")
        # Header 보장
        existing = ws.get_all_values()
        header = list(df.columns)
        if not existing:
            ws.append_row(header, value_input_option="USER_ENTERED")
        # Append
        rows = df.astype(str).values.tolist()
        ws.append_rows(rows, value_input_option="USER_ENTERED")
        return None
    except Exception as e:
        return str(e)

# ---------- Rules ----------
CATEGORY_KEYWORDS={"small_elec":["드라이기","청소기","电子","small","vacuum","吸尘器"],"rice_cooker":["밥솥","电饭煲"],"kettle":["주전자","电热水壶"],"thermos":["보온병","保温壶"],"air_fryer":["에어프라이어","空气炸锅"],"blender":["믹서기","破壁机"],"shoes":["신발","鞋"],"clothing":["의류","衣服"],"container":["용기","塑料","收纳"],"pot_pan":["냄비","锅"],"beauty":["미용","美容"]}
PRIORS={"rice_cooker":{"shell_per_L":0.90,"inner_per_L":0.20,"base":0.30,"acc":0.10},
        "kettle":{"shell_per_L":0.45,"inner_per_L":0.12,"base":0.15,"acc":0.05},
        "thermos":{"shell_per_L":0.30,"inner_per_L":0.00,"base":0.05,"acc":0.00},
        "air_fryer":{"shell_per_L":0.70,"inner_per_L":0.18,"base":0.35,"acc":0.10},
        "blender":{"shell_per_L":0.55,"inner_per_L":0.10,"base":0.25,"acc":0.10},
        "container":{"thickness":0.03,"avg_density":1.0,"acc":0.05},
        "small_elec":{"base":0.35,"per_cm3_g":0.0009},
        "shoes":{"pair":0.80},"clothing":{"piece":0.35},
        "pot_pan":{"base":1.80},"beauty":{"base":0.40}}
POWER_FACTORS={"small_elec":0.9,"blender":0.8,"air_fryer":0.6,"beauty":0.5,"kettle":0.3,"rice_cooker":0.35}

# ---------- Helpers ----------
def infer_cat(name):
    t=(name or "").lower()
    for c,kws in CATEGORY_KEYWORDS.items():
        if any(kw.lower() in t for kw in kws): return c
    if any(k in t for k in ["l","리터","升"]): return "rice_cooker"
    return "small_elec"

def u2cm(v,unit):
    unit=(unit or "cm").lower()
    if unit in ["mm","毫米"]: return v/10.0
    if unit in ["cm","厘米"]: return v
    if unit in ["m","米"]: return v*100.0
    return v

def extract_capacity_L(txt):
    m=re.search(r'(\d+(?:\.\d+)?)\s*(l|리터|升)',(txt or "").lower())
    if m:
        try: return float(m.group(1))
        except: return 0.0
    m2=re.search(r'(\d+(?:\.\d+)?)\s*(ml|毫升)',(txt or "").lower())
    if m2:
        try: return float(m2.group(1))/1000.0
        except: return 0.0
    return 0.0

def parse_weight(txt):
    t=(txt or "").lower()
    m=re.search(r'(\d+(?:\.\d+)?)\s*(kg|g|斤|千克|公斤|克)',t)
    if not m: return None
    val=float(m.group(1)); u=m.group(2)
    if u in ["g","克"]: val/=1000.0
    elif u in ["斤"]: val*=0.5
    return round(val,2)

def dims_pattern(txt):
    if not txt: return None
    s=txt.replace("×","x").replace("＊","x").replace("X","x").replace("：",":").replace("，",",")
    m=re.search(r'(\d+(?:\.\d+)?)\s*[x\*]\s*(\d+(?:\.\d+)?)\s*[x\*]\s*(\d+(?:\.\d+)?)(\s*(mm|cm|m|毫米|厘米|米))?',s,re.I)
    if m:
        a,b,c=float(m.group(1)),float(m.group(2)),float(m.group(3)); unit=(m.group(5) or "cm")
        L,W,H=sorted([u2cm(a,unit),u2cm(b,unit),u2cm(c,unit)],reverse=True)
        return (L,W,H)
    m2=re.search(r'长\s*(\d+(?:\.\d+)?)\s*(mm|cm|m|毫米|厘米|米)?\s*宽\s*(\d+(?:\.\d+)?)\s*(mm|cm|m|毫米|厘米|米)?\s*高\s*(\d+(?:\.\d+)?)\s*(mm|cm|m|毫米|厘米|米)?',s,re.I)
    if m2:
        L=u2cm(float(m2.group(1)),(m2.group(2) or "cm")); W=u2cm(float(m2.group(3)),(m2.group(4) or "cm")); H=u2cm(float(m2.group(5)),(m2.group(6) or "cm"))
        return (L,W,H)
    return None

def dims_anywhere(txt):
    if not txt: return None
    nums=re.findall(r'(\d+(?:\.\d+)?)\s*(mm|cm|m|毫米|厘米|米)',txt,re.I)
    vals=[u2cm(float(n),u.lower()) for n,u in nums]
    vals=[v for v in vals if 5<=v<=300]
    vals=sorted(vals,reverse=True)
    dedup=[]
    for v in vals:
        if not any(abs(v-d)<1.0 for d in dedup): dedup.append(v)
    return tuple(dedup[:3]) if len(dedup)>=3 else None

def preprocess_for_ocr(img: Image.Image)->Image.Image:
    w,h=img.size
    scale = 1600/w if w<1600 else 1.0
    if scale>1: img = img.resize((int(w*scale), int(h*scale)))
    img = ImageOps.grayscale(img)
    img = ImageEnhance.Contrast(img).enhance(2.0)
    img = ImageEnhance.Sharpness(img).enhance(1.5)
    return img

def build_reader():
    candidates = [['ch_sim','en','ko'], ['ch_sim','en'], ['en']]
    last_err = None
    for langs in candidates:
        try:
            return easyocr.Reader(langs, gpu=False, download_enabled=True, verbose=False)
        except Exception as e:
            last_err = e
            continue
    raise RuntimeError(f"OCR 초기화 실패: {last_err}")

def ocr_text_from_images(files):
    if not (HAS_OCR and files): return "", "OCR 비활성 또는 이미지 없음"
    reader = build_reader()
    chunks=[]
    for f in files:
        try:
            f.seek(0)
            im=Image.open(io.BytesIO(f.read())).convert("RGB")
            pim=preprocess_for_ocr(im)
            arr=np.array(pim)
            text = "
".join(reader.readtext(arr, detail=0, paragraph=True))
            chunks.append(text)
        except Exception:
            chunks.append("")
    return "
".join(chunks), None

def dims_from_ocr(files):     text, _ = ocr_text_from_images(files)     d = dims_pattern(text) or dims_anywhere(text)     return d, textfiles):
    text,_=ocr_text_from_images(files)
    d = dims_pattern(text) or dims_anywhere(text)
    return d, text

def pkg_w(L,W,H):
    if not(L and W and H): return 0.5
    return 0.25 + min(1.5,(L*W*H)*1e-6)

def vol(L,W,H,div):
    return (L*W*H)/div if (L and W and H) else 0

def avg_delta(db,cat):
    ds=[v["delta"] for v in db.values() if v.get("category")==cat and isinstance(v.get("delta"),(int,float))]
    return max(-2,min(2,sum(ds)/len(ds))) if ds else 0.0

def estimate(product_name,cap_L,cat,dims,power_kw=0.0,extra=0.1,net_override=None,db=None):
    PRI=PRIORS; L,W,H=dims; net=0.0
    if net_override is not None: net=net_override
    elif cat in ["rice_cooker","kettle","thermos","air_fryer","blender"]:
        cap=max(0.0,cap_L or 0.0); pr=PRI[cat]; net=pr["shell_per_L"]*cap+pr["inner_per_L"]*cap+pr["base"]+pr["acc"]+extra
    elif cat=="container":
        cap=cap_L or 0.0
        if cap<=0 and all(dims): cap=(L*W*H*0.6)/1000.0
        mass=max(0.05, ((cap*1000.0)*PRI["container"]["thickness"]*PRI["container"]["avg_density"])/1000.0)
        net=mass+extra
    elif cat=="small_elec":
        net=PRI["small_elec"]["base"]+(L or 30)*(W or 30)*(H or 25)*PRI["small_elec"]["per_cm3_g"]/1000.0+extra
    elif cat=="shoes": net=PRI["shoes"]["pair"]
    elif cat=="clothing": net=PRI["clothing"]["piece"]
    elif cat=="pot_pan": net=PRI["pot_pan"]["base"]+extra
    elif cat=="beauty": net=PRI["beauty"]["base"]+extra
    else: net=0.6+extra
    net += max(0.0,power_kw)*POWER_FACTORS.get(cat,0.3)
    delta=avg_delta(db or {},cat); net=max(0.05,net+delta)
    return {"net_kg":round(net,2),"gross_kg":round(net+pkg_w(L,W,H),2),
            "vol_5000":round(vol(L,W,H,5000),2),"vol_6000":round(vol(L,W,H,6000),2),
            "confidence":min(95,70+(10 if cap_L>0 else 0)+(10 if all(dims) else 0)+(5 if power_kw>0 else 0)),
            "category":cat,"delta_applied":round(delta,2),"power_kw":power_kw,"power_factor":POWER_FACTORS.get(cat,0.3)}

# ---------- UI ----------
db=load_local_db()
st.title("⚖️ WeightBot · 이미지 기반 무게 추정 (옵션별 숫자박스 L/W/H)")
st.caption("옵션별 크기가 다르면 각 옵션의 숫자 박스에 L/W/H를 입력하세요. 입력하지 않으면 상품 기본 치수를 사용합니다. Enter 키로 다음 칸으로 자동 이동합니다.")

colA,colB,colC=st.columns([1.2,1.2,1.2])
with colA:
    product_code=st.text_input("상품코드",placeholder="예: A240812")
    product_name=st.text_input("상품명",placeholder="예: 2kW 절단기 / 750x550x640mm 등")
with colB:
    imgs=st.file_uploader("상품/스펙 이미지(여러 장)",type=["png","jpg","jpeg","webp"],accept_multiple_files=True)
    if imgs: st.image(imgs[0],caption="대표 이미지",use_container_width=True)
with colC:
    manual_L=st.number_input("수동 용량(L)",min_value=0.0,step=0.1,value=0.0)
    # 항상 키보드 입력 가능한 숫자칸 + 빠른 선택(1~10)
    if "num_options" not in st.session_state:
        st.session_state["num_options"] = 1
    num_options = st.number_input("옵션 개수(항시 입력 가능)", min_value=1, step=1, value=st.session_state["num_options"], key="num_options")
    quick = st.selectbox("빠른 선택(1~10)", ["선택 안함"] + [str(i) for i in range(1,11)], key="quick_pick")
    if quick != "선택 안함":
        st.session_state["num_options"] = int(quick)
        num_options = st.session_state["num_options"]

st.markdown("---")

# ---- Global box size controls (Default for all options) ----
st.subheader("상품 기본 치수(cm) — 모든 옵션에 기본 적용")
if "boxL" not in st.session_state: st.session_state["boxL"]=0.0; st.session_state["boxW"]=0.0; st.session_state["boxH"]=0.0
c1,c2,c3,c4=st.columns([1,1,1,1])
st.session_state["boxL"]=c1.number_input("가로 L",min_value=0.0,step=0.1,value=st.session_state["boxL"])
st.session_state["boxW"]=c2.number_input("세로 W",min_value=0.0,step=0.1,value=st.session_state["boxW"])
st.session_state["boxH"]=c3.number_input("높이 H",min_value=0.0,step=0.1,value=st.session_state["boxH"])
pad=c4.number_input("사량여유(+cm)",min_value=0.0,step=0.5,value=0.0)

# ---- Options ----
st.subheader("옵션 입력 — 기본 치수를 그대로 사용. 다를 때만 아래 숫자 박스에 입력(선택)")
if "opt_text" not in st.session_state: st.session_state["opt_text"]=""
option_text=st.text_area("옵션명 목록(선택, 한 줄에 하나)",key="opt_text",height=120,placeholder="예: GYJ-80S / 2kW")
option_names=[ln.strip() for ln in option_text.splitlines() if ln.strip()]
total=len(option_names) if option_names else int(num_options)

# 기본 박스 치수
base=(30.0,30.0,25.0)
gL=st.session_state["boxL"] or base[0]
gW=st.session_state["boxW"] or base[1]
gH=st.session_state["boxH"] or base[2]
global_dims=(gL+pad,gW+pad,gH+pad)

auto_cat=infer_cat(product_name)
global_cap=extract_capacity_L(product_name) or manual_L or 0.0

st.write(f"🧠 카테고리=`{auto_cat}`, 기준용량≈`{global_cap} L`, 기본 박스={global_dims[0]:.1f}×{global_dims[1]:.1f}×{global_dims[2]:.1f} cm")

power_choices=["선택 안함"]+[f"{w}W" for w in range(100,1000,100)]+[f"{k}kW" for k in range(1,11)]
def p2kw(t):
    if not t: return 0.0
    s=(t or "").lower().replace(" ","")
    m=re.search(r'(\d+(?:\.\d+)?)\s*kw',s)
    if m:
        try:return float(m.group(1))
        except:return 0.0
    m=re.search(r'(\d+(?:\.\d+)?)\s*w',s)
    if m:
        try:return float(m.group(1))/1000.0
        except:return 0.0
    return 0.0

def estimate_wrap(name,power_choice,dims_local):
    power_kw=p2kw(power_choice) or p2kw(name)
    cap=extract_capacity_L(name) or global_cap
    net_override=parse_weight(name)
    return estimate(product_name,cap,auto_cat,dims_local,power_kw,db=load_local_db())

rows=[]
for idx in range(1,total+1):
    with st.expander(f"옵션 {idx}",expanded=(idx==1)):
        code=f"{product_code}-{idx:02d}" if product_code else f"OPT-{idx:02d}"
        base_name=option_names[idx-1] if option_names else f"(자동){code}"
        st.text_input("옵션코드",value=code,key=f"code_{idx}",disabled=True)
        cN,cP=st.columns([3,1])
        name=cN.text_input("옵션명",value=base_name,key=f"name_{idx}")
        power_choice=cP.selectbox("출력용량",options=power_choices,index=0,key=f"p_{idx}")

        # --- 옵션별 숫자 박스 L/W/H (모두 0이면 기본 치수 사용) ---
        l_col,w_col,h_col = st.columns(3)
        ovL = l_col.number_input(f"가로 L(옵션 {idx})", min_value=0.0, step=0.1, key=f"ovL_{idx}", value=0.0)
        ovW = w_col.number_input(f"세로 W(옵션 {idx})", min_value=0.0, step=0.1, key=f"ovW_{idx}", value=0.0)
        ovH = h_col.number_input(f"높이 H(옵션 {idx})", min_value=0.0, step=0.1, key=f"ovH_{idx}", value=0.0)

        # Enter로 다음 칸 이동 (가로 -> 세로 -> 높이)
        js = f"""
        <script>
        (function() {{
          const labels = [
            "가로 L(옵션 {idx})",
            "세로 W(옵션 {idx})",
            "높이 H(옵션 {idx})"
          ];
          function bind() {{
            try {{
              labels.forEach((lab, i) => {{
                const inp = window.parent.document.querySelector(`input[aria-label="${{lab}}"]`);
                if (inp && !inp.dataset.__wb_bound) {{
                  inp.dataset.__wb_bound = "1";
                  inp.addEventListener('keydown', function(e) {{
                    if (e.key === 'Enter') {{
                      e.preventDefault();
                      const nextLab = labels[i+1];
                      if (nextLab) {{
                        const nx = window.parent.document.querySelector(`input[aria-label="${{nextLab}}"]`);
                        if (nx) nx.focus();
                      }}
                    }}
                  }});
                }}
              }});
            }} catch(e) {{}}
          }}
          setTimeout(bind, 200);
          setTimeout(bind, 800);
          setTimeout(bind, 1600);
        }})();
        </script>
        """
        components.html(js, height=0)

        use_override = ovL>0 and ovW>0 and ovH>0
        dims_used = (ovL, ovW, ovH) if use_override else global_dims
        src = "옵션별" if use_override else "기본"

        r=estimate_wrap(name,power_choice,dims_used)
        st.caption(f"치수({src}): {dims_used[0]:.1f}×{dims_used[1]:.1f}×{dims_used[2]:.1f} cm · 순 {r['net_kg']}kg / 총 {r['gross_kg']}kg · 부피(5000/6000) {r['vol_5000']}/{r['vol_6000']}kg · 신뢰 {r['confidence']}%")

        rows.append({"product_code":product_code,"option_code":code,"option_name":name,"product_name":product_name,
                     "category":r["category"],"capacity_L":extract_capacity_L(name) or global_cap,"power_kW":r["power_kw"],
                     "box_cm":f"{dims_used[0]:.1f}x{dims_used[1]:.1f}x{dims_used[2]:.1f}","dims_source":src,
                     "net_kg":r["net_kg"],"gross_kg":r["gross_kg"],"vol_5000":r["vol_5000"],"vol_6000":r["vol_6000"],
                     "confidence":r["confidence"],"delta_applied":r["delta_applied"],"timestamp":time.strftime("%Y-%m-%d %H:%M:%S")})

st.markdown("---")
if rows:
    df=pd.DataFrame(rows)
    st.dataframe(df,use_container_width=True)

    # 엑셀 다운로드
    out=io.BytesIO()
    with pd.ExcelWriter(out,engine="xlsxwriter") as w: df.to_excel(w,sheet_name="results",index=False)
    st.download_button("결과를 Excel로 저장",data=out.getvalue(),file_name=f"{(product_code or 'results')}_estimate.xlsx")

    # ---------- Auto history: save every run ----------
    history = load_history()
    # 각 행에 세션 고유키와 저장시각 추가
    session_key = st.session_state.get("session_key")
    if not session_key:
        session_key = f"sess_{int(time.time()*1000)}"
        st.session_state["session_key"] = session_key
    df_with_meta = df.copy()
    df_with_meta["__session__"] = session_key
    df_with_meta["saved_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
    history.extend(df_with_meta.to_dict(orient="records"))
    save_history(history)

    st.subheader("자동 저장 기록(앱 내부 파일)")
    st.caption("모든 조회 결과가 앱의 로컬 파일에 자동 저장됩니다. 재시작/재배포 시 초기화될 수 있으니 필요하면 아래에서 내려받으세요.")
    hist_df = pd.DataFrame(history)
    if not hist_df.empty:
        st.dataframe(hist_df.tail(100), use_container_width=True, height=240)
        csv_b = hist_df.to_csv(index=False).encode("utf-8-sig")
        st.download_button("히스토리 전체 CSV 다운로드", data=csv_b, file_name="weightbot_history.csv")
        if st.button("히스토리 모두 삭제(초기화)"):
            save_history([])
            st.warning("히스토리를 삭제했습니다. 새 조회부터 다시 저장됩니다.")

    # ---------- Google Sheets sync (optional) ----------
    if st.secrets.get("gcp_service_account") and st.secrets.get("gsheets"):
        st.subheader("구글시트 동기화")
        st.caption("Secrets가 설정되어 있으면 자동으로 한 번 기록합니다. 필요하면 아래 버튼으로 다시 동기화할 수 있습니다.")
        if "sheets_done" not in st.session_state:
            st.session_state["sheets_done"] = False
        if not st.session_state["sheets_done"]:
            err = gsheets_append(df_with_meta)
            if err:
                st.warning(f"구글시트 자동 기록 실패: {err}")
            else:
                st.success("구글시트로 자동 기록 완료")
                st.session_state["sheets_done"] = True
        if st.button("구글시트로 다시 동기화"):
            err = gsheets_append(df_with_meta)
            if err:
                st.error(f"실패: {err}")
            else:
                st.success("동기화 완료")

    # ---------- Feedback Section (Learning) ----------
    st.subheader("피드백(실측값 입력 → 학습)")
    st.caption("실측 순중량을 입력해주면 카테고리별 평균 보정치가 자동 학습되어 다음 추정에 반영됩니다. (로컬 JSON 저장)")

    # 선택 대상 옵션
    label_list=[f"{i+1}. {r['option_code']} · {r['option_name']}" for i,r in enumerate(rows)]
    pick=st.selectbox("대상 옵션 선택", options=label_list, index=0, key="fb_pick")
    sel_idx=label_list.index(pick)
    sel=rows[sel_idx]

    c1,c2,c3,c4 = st.columns([1,1,1,1])
    actual_net = c1.number_input("실측 순중량(kg)", min_value=0.0, step=0.01, value=0.0, key="fb_net")
    actL = c2.number_input("실측 박스 L(선택)", min_value=0.0, step=0.1, value=0.0, key="fb_L")
    actW = c3.number_input("실측 박스 W(선택)", min_value=0.0, step=0.1, value=0.0, key="fb_W")
    actH = c4.number_input("실측 박스 H(선택)", min_value=0.0, step=0.1, value=0.0, key="fb_H")
    memo = st.text_input("메모(선택)", value="", key="fb_memo")

    if st.button("피드백 저장/학습 적용", type="primary"):
        if actual_net<=0:
            st.warning("실측 순중량(kg)을 입력해 주세요.")
        else:
            db=load_local_db()
            delta = round(actual_net - float(sel["net_kg"]), 3)
            key = f"{sel['option_code']}_{int(time.time())}"
            db[key] = {
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                "product_code": sel["product_code"],
                "option_code": sel["option_code"],
                "option_name": sel["option_name"],
                "category": sel["category"],
                "pred_net": float(sel["net_kg"]),
                "actual_net": float(actual_net),
                "delta": delta,
                "actual_box_cm": f"{actL}x{actW}x{actH}" if (actL and actW and actH) else "",
                "memo": memo,
            }
            save_local_db(db)
            cat_delta = avg_delta(db, sel["category"])
            st.success(f"저장 완료! (보정 Δ={delta:+.2f}kg). 현재 카테고리 평균 보정: {cat_delta:+.2f}kg")
    with st.expander("최근 피드백 5개 보기"):
        dbv = load_local_db()
        if dbv:
            last = list(dbv.items())[-5:]
            view = [{"key":k, **v} for k,v in last]
            st.dataframe(pd.DataFrame(view), use_container_width=True)
        else:
            st.info("아직 저장된 피드백이 없습니다.")
