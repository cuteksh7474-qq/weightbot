
# -*- coding: utf-8 -*-
import streamlit as st
from PIL import Image, ImageOps, ImageEnhance
import io, json, time, re
import pandas as pd

# ---------- Optional OCR ----------
HAS_OCR=False
try:
    import easyocr, numpy as np
    HAS_OCR=True
except Exception:
    HAS_OCR=False

st.set_page_config(page_title="WeightBot · 이미지 기반 무게 추정", page_icon="⚖️", layout="wide")

# ---------- Storage ----------
LOCAL_DB="feedback_db.json"
def load_local_db():
    try:
        with open(LOCAL_DB,"r",encoding="utf-8") as f:return json.load(f)
    except: return {}
def save_local_db(d):
    try:
        with open(LOCAL_DB,"w",encoding="utf-8") as f: json.dump(d,f,ensure_ascii=False,indent=2)
    except: pass

# ---------- Rules ----------
CATEGORY_KEYWORDS={"small_elec":["드라이기","청소기","电子","small","vacuum","吸尘器"],"rice_cooker":["밥솥","电饭煲"],"kettle":["주전자","电热水壶"],"thermos":["보온병","保温壶"],"air_fryer":["에어프라이어","空气炸锅"],"blender":["믹서기","破壁机"],"shoes":["신발","鞋"],"clothing":["의류","衣服"],"container":["용기","塑料","收纳"],"pot_pan":["냄비","锅"],"beauty":["미용","美容"]}
PRIORS={"rice_cooker":{"shell_per_L":0.90,"inner_per_L":0.20,"base":0.30,"acc":0.10},
        "kettle":{"shell_per_L":0.45,"inner_per_L":0.12,"base":0.15,"acc":0.05},
        "thermos":{"shell_per_L":0.30,"inner_per_L":0.00,"base":0.05,"acc":0.00},
        "air_fryer":{"shell_per_L":0.70,"inner_per_L":0.18,"base":0.35,"acc":0.10},
        "blender":{"shell_per_L":0.55,"inner_per_L":0.10,"base":0.25,"acc":0.10},
        "container":{"thickness":0.03,"avg_density":1.0,"acc":0.05},
        "small_elec":{"base":0.35,"per_cm3_g":0.0009},
        "shoes":{"pair":0.80},"clothing":{"piece":0.35},"pot_pan":{"base":1.80},"beauty":{"base":0.40}}
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
    m=re.search(r'(\\d+(?:\\.\\d+)?)\\s*(l|리터|升)',(txt or "").lower())
    if m:
        try: return float(m.group(1))
        except: return 0.0
    m2=re.search(r'(\\d+(?:\\.\\d+)?)\\s*(ml|毫升)',(txt or "").lower())
    if m2:
        try: return float(m2.group(1))/1000.0
        except: return 0.0
    return 0.0

def parse_weight(txt):
    t=(txt or "").lower()
    m=re.search(r'(\\d+(?:\\.\\d+)?)\\s*(kg|g|斤|千克|公斤|克)',t)
    if not m: return None
    val=float(m.group(1)); u=m.group(2)
    if u in ["g","克"]: val/=1000.0
    elif u in ["斤"]: val*=0.5
    return round(val,2)

def dims_pattern(txt):
    if not txt: return None
    s=txt.replace("×","x").replace("＊","x").replace("X","x").replace("：",":").replace("，",",")
    m=re.search(r'(\\d+(?:\\.\\d+)?)\\s*[x\\*]\\s*(\\d+(?:\\.\\d+)?)\\s*[x\\*]\\s*(\\d+(?:\\.\\d+)?)(\\s*(mm|cm|m|毫米|厘米|米))?',s,re.I)
    if m:
        a,b,c=float(m.group(1)),float(m.group(2)),float(m.group(3)); unit=(m.group(5) or "cm")
        L,W,H=sorted([u2cm(a,unit),u2cm(b,unit),u2cm(c,unit)],reverse=True)
        return (L,W,H)
    # 长…宽…高…
    m2=re.search(r'长\\s*(\\d+(?:\\.\\d+)?)\\s*(mm|cm|m|毫米|厘米|米)?\\s*宽\\s*(\\d+(?:\\.\\d+)?)\\s*(mm|cm|m|毫米|厘米|米)?\\s*高\\s*(\\d+(?:\\.\\d+)?)\\s*(mm|cm|m|毫米|厘米|米)?',s,re.I)
    if m2:
        L=u2cm(float(m2.group(1)),(m2.group(2) or "cm")); W=u2cm(float(m2.group(3)),(m2.group(4) or "cm")); H=u2cm(float(m2.group(5)),(m2.group(6) or "cm"))
        return (L,W,H)
    return None

def dims_anywhere(txt):
    if not txt: return None
    nums=re.findall(r'(\\d+(?:\\.\\d+)?)\\s*(mm|cm|m|毫米|厘米|米)',txt,re.I)
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
    # Robust fallback: try ko 포함 -> ko 제거 -> en만
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
            text = "\\n".join(reader.readtext(arr, detail=0, paragraph=True))
            chunks.append(text)
        except Exception as e:
            chunks.append("")
    return "\\n".join(chunks), None

def dims_from_ocr(files):
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
st.title("⚖️ WeightBot · 이미지 기반 무게 추정")
st.caption("치수 자동(OCR) 실패 시 **보조 입력** 또는 **수동 입력**을 사용하세요.")

colA,colB,colC=st.columns([1.2,1.2,1.2])
with colA:
    product_code=st.text_input("상품코드",placeholder="예: A240812")
    product_name=st.text_input("상품명",placeholder="예: 2kW 절단기 / 750x550x640mm 등")
with colB:
    imgs=st.file_uploader("상품/스펙 이미지(여러 장)",type=["png","jpg","jpeg","webp"],accept_multiple_files=True)
    if imgs: st.image(imgs[0],caption="대표 이미지",use_column_width=True)
with colC:
    manual_L=st.number_input("수동 용량(L)",min_value=0.0,step=0.1,value=0.0)
    num_options=st.number_input("옵션 개수(옵션명 없을 때)",min_value=1,step=1,value=1)

st.markdown("---")

# ---- Box size controls ----
st.subheader("치수(cm)")
if "boxL" not in st.session_state: st.session_state["boxL"]=0.0; st.session_state["boxW"]=0.0; st.session_state["boxH"]=0.0
c1,c2,c3,c4=st.columns([1,1,1,1])
st.session_state["boxL"]=c1.number_input("가로 L",min_value=0.0,step=0.1,value=st.session_state["boxL"])
st.session_state["boxW"]=c2.number_input("세로 W",min_value=0.0,step=0.1,value=st.session_state["boxW"])
st.session_state["boxH"]=c3.number_input("높이 H",min_value=0.0,step=0.1,value=st.session_state["boxH"])
pad=c4.number_input("사량여유(+cm)",min_value=0.0,step=0.5,value=0.0)

colx, coly = st.columns([1,1])
with colx:
    if st.button("🧠 OCR로 기록(강화)"):
        d, otext = dims_from_ocr(imgs)
        st.session_state["__ocr_text__"] = otext or ""
        if d:
            L,W,H=sorted(d,reverse=True)
            st.session_state["boxL"],st.session_state["boxW"],st.session_state["boxH"]=round(L,1),round(W,1),round(H,1)
            st.success(f"OCR 치수 적용: {L:.1f} x {W:.1f} x {H:.1f} cm")
        else:
            st.error("OCR에서 치수 미검출. 오른쪽 '강제 적용'을 사용하세요.")
with coly:
    force_txt = st.text_input("입력하세요(예: 750mm, 640mm, 550mm / 75cm,55cm,64cm)")
    if st.button("➡ 강제 적용"):
        nums=re.findall(r'(\\d+(?:\\.\\d+)?)\\s*(mm|cm|m)', force_txt or "", re.I)
        vals=[u2cm(float(n),u.lower()) for n,u in nums if 5<=u2cm(float(n),u.lower())<=300]
        if len(vals)>=3:
            L,W,H=sorted(vals,reverse=True)[:3]
            st.session_state["boxL"],st.session_state["boxW"],st.session_state["boxH"]=round(L,1),round(W,1),round(H,1)
            st.success(f"강제 적용: {L:.1f} x {W:.1f} x {H:.1f} cm")
        else:
            st.error("숫자 3개(단위 포함)를 인식하지 못했습니다.")

with st.expander("🔎 OCR 번역/진단 보기"):
    st.write(f"OCR 가능 여부 : {HAS_OCR}")
    st.text(st.session_state.get("__ocr_text__", "아직 실행되지 않았습니다."))

# ---- Options ----
st.subheader("옵션명(선택, 한 줄에 하나) + 출력 용량 선택")
if "opt_text" not in st.session_state: st.session_state["opt_text"]=""
opt_text=st.text_area("옵션명 목록",key="opt_text",height=120,placeholder="예: GYJ-80S / 2kW")
option_names=[ln.strip() for ln in (st.session_state.get("opt_text") or "").splitlines() if ln.strip()]
total=len(option_names) if option_names else int(num_options)

auto_cat=infer_cat(product_name)
global_cap=extract_capacity_L(product_name) or manual_L or 0.0

# 박스 치수 최종
base=(30.0,30.0,25.0)
L=st.session_state["boxL"] or base[0]
W=st.session_state["boxW"] or base[1]
H=st.session_state["boxH"] or base[2]
dims_used=(L+pad,W+pad,H+pad)

st.write(f"🧠 카테고리=`{auto_cat}`, 기준용량≈`{global_cap} L`, 박스={dims_used[0]:.1f}×{dims_used[1]:.1f}×{dims_used[2]:.1f} cm")

power_choices=["선택 안함"]+[f"{w}W" for w in range(100,1000,100)]+[f"{k}kW" for k in range(1,11)]
def p2kw(t):
    if not t: return 0.0
    s=(t or "").lower().replace(" ","")
    m=re.search(r'(\\d+(?:\\.\\d+)?)\\s*kw',s)
    if m:
        try:return float(m.group(1))
        except:return 0.0
    m=re.search(r'(\\d+(?:\\.\\d+)?)\\s*w',s)
    if m:
        try:return float(m.group(1))/1000.0
        except:return 0.0
    return 0.0

def estimate_wrap(name, power_choice):
    power_kw=p2kw(power_choice) or p2kw(name)
    cap=extract_capacity_L(name) or global_cap
    net_override=parse_weight(name)
    return estimate(product_name,cap,auto_cat,dims_used,power_kw,db=load_local_db())

rows=[]
for idx in range(1,total+1):
    with st.expander(f"옵션 {idx}",expanded=(idx==1)):
        code=f"{product_code}-{idx:02d}" if product_code else f"OPT-{idx:02d}"
        base_name=option_names[idx-1] if option_names else f"(자동){code}"
        st.text_input("옵션코드",value=code,key=f"code_{idx}",disabled=True)
        cN,cP=st.columns([3,1])
        name=cN.text_input("옵션명",value=base_name,key=f"name_{idx}")
        power_choice=cP.selectbox("출력용량",options=power_choices,index=0,key=f"p_{idx}")
        r=estimate_wrap(name,power_choice)
        st.caption(f"순 {r['net_kg']}kg / 총 {r['gross_kg']}kg · 부피 5000/6000 = {r['vol_5000']}/{r['vol_6000']}kg · 신뢰 {r['confidence']}%")
        rows.append({"product_code":product_code,"option_code":code,"option_name":name,"product_name":product_name,"category":r["category"],"capacity_L":extract_capacity_L(name) or global_cap,"power_kW":r["power_kw"],"box_cm":f"{dims_used[0]:.1f}x{dims_used[1]:.1f}x{dims_used[2]:.1f}","net_kg":r["net_kg"],"gross_kg":r["gross_kg"],"vol_5000":r["vol_5000"],"vol_6000":r["vol_6000"],"confidence":r["confidence"],"delta_applied":r["delta_applied"],"timestamp":time.strftime("%Y-%m-%d %H:%M:%S")})

st.markdown("---")
if rows:
    df=pd.DataFrame(rows)
    st.dataframe(df,use_container_width=True)
    out=io.BytesIO()
    with pd.ExcelWriter(out,engine="xlsxwriter") as w: df.to_excel(w,sheet_name="results",index=False)
    st.download_button("결과를 Excel로 저장",data=out.getvalue(),file_name=f"{(product_code or 'results')}_estimate.xlsx")
