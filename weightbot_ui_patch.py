
# -*- coding: utf-8 -*-
"""
weightbot_ui_patch.py
---------------------
보조 모듈: (1) 입력칸 너비 축소, (2) 엔터키로 다음 칸 이동, (3) 현실적인 무게 추정식.
기존 앱을 크게 바꾸지 않고 import 후 함수 1~2개만 호출해서 사용할 수 있도록 분리했습니다.
"""
from __future__ import annotations
from typing import Dict, Tuple

import streamlit as st
import streamlit.components.v1 as components

_STYLE_INJECTED_KEY = "_wb_style_injected"
_JS_INJECTED_KEY = "_wb_js_injected"

def enable_enter_to_next_and_shorten(input_width_px: int = 220) -> None:
    """
    - 모든 텍스트/숫자 입력칸의 가로폭을 줄이고
    - 입력칸에서 Enter를 누르면 다음 입력칸으로 포커스가 이동하도록 JS/CSS를 주입합니다.
    """
    if not st.session_state.get(_STYLE_INJECTED_KEY, False):
        st.markdown(
            '<style>\n'
            '/* 입력 위젯 가로폭 줄이기 */\n'
            '.stTextInput > div > div > input, .stNumberInput input {max-width: 220px !important; width: 220px !important;}\n'
            '/* selectbox도 폭 축소 */\n'
            '.stSelectbox > div > div {max-width: 220px !important;}\n'
            '</style>',
            unsafe_allow_html=True
        )
        st.session_state[_STYLE_INJECTED_KEY] = True

    if not st.session_state.get(_JS_INJECTED_KEY, False):
        components.html(
            '<script>\n'
            'function attachEnterNav(){\n'
            '  const inputs = Array.from(window.parent.document.querySelectorAll("input[type=\\"text\\"], input[type=\\"number\\"]"));\n'
            '  inputs.forEach((el, idx) => {\n'
            '    el.addEventListener("keydown", (e) => {\n'
            '      if (e.key === "Enter") {\n'
            '        e.preventDefault();\n'
            '        const next = inputs[idx + 1];\n'
            '        if (next) next.focus();\n'
            '      }\n'
            '    }, { once:false });\n'
            '  });\n'
            '}\n'
            'setTimeout(attachEnterNav, 400);\n'
            '</script>',
            height=0
        )
        st.session_state[_JS_INJECTED_KEY] = True

# -------------------------
# 현실적인 무게 추정식
# -------------------------
_CATEGORY_DEFAULTS = {
    "small_elec": {"density": 0.0009, "fill": 0.12, "motor": 2.0},
    "metal_tool": {"density": 0.0012, "fill": 0.20, "motor": 2.5},
    "plastic":    {"density": 0.0007, "fill": 0.14, "motor": 1.0},
}

def _box_with_clearance(L: float, W: float, H: float, c: float) -> Tuple[float,float,float]:
    return L + c*2, W + c*2, H + c*2

def estimate_weight(L: float, W: float, H: float, *, clearance_cm: float = 2.5,
                    power_kw: float | None = None, category: str = "small_elec") -> Dict[str, object]:
    """치수/카테고리/출력용량을 받아 현실 범위의 무게를 추정한다.
    반환: dict(net_kg, gross_kg, box_cm(str), details(dict))
    """
    try:
        L = float(L or 0); W = float(W or 0); H = float(H or 0)
    except Exception:
        L=W=H=0.0
    clearance_cm = float(clearance_cm or 0)
    power_kw = float(power_kw or 0.0) if power_kw is not None else 0.0

    Lb, Wb, Hb = _box_with_clearance(L, W, H, clearance_cm)

    cfg = _CATEGORY_DEFAULTS.get(category, _CATEGORY_DEFAULTS["small_elec"])
    density = cfg["density"]; fill = cfg["fill"]; motor = cfg["motor"]

    vol_cm3 = L * W * H
    content_kg = vol_cm3 * density * fill
    motor_kg = motor * power_kw if power_kw > 0 else 0.0
    net_kg = content_kg + motor_kg

    net_kg = max(net_kg, 3.0)
    net_kg = min(net_kg, 400.0)

    gross_kg = net_kg * 1.08 + 1.0

    return {
        "net_kg": round(net_kg, 2),
        "gross_kg": round(gross_kg, 2),
        "box_cm": f"{round(Lb,1)}x{round(Wb,1)}x{round(Hb,1)}",
        "details": {"vol_cm3": vol_cm3, "density": density, "fill": fill, "motor_kg": motor_kg},
    }
