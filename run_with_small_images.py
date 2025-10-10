# -*- coding: utf-8 -*-
"""
Wrapper launcher for WeightBot that forces ALL image previews (including file-uploader previews)
to render small (about 10% of the container width, capped), without touching the original app.
Usage: set this file as Streamlit "Main file path". It will inject CSS and then import the
original app module so all features stay intact.
"""

import streamlit as st
import importlib

# ---------- CSS: shrink all images safely (uploader + st.image) ----------
SMALL_IMAGE_CSS = """
<style>
/* Generic st.image */
.stImage img {
  width: 10% !important;         /* ~10% of the container width */
  max-width: 200px !important;   /* upper bound to avoid too big on wide screens */
  height: auto !important;
}

/* File uploader dropzone preview */
[data-testid="stFileUploaderDropzone"] img,
[data-testid="stFileUploaderFile"] img {
  width: 10% !important;
  max-width: 200px !important;
  height: auto !important;
}

/* Prevent layout jump from caption below thumbnails */
.stImage figcaption {
  font-size: 0.8rem !important;
}
</style>
"""

st.markdown(SMALL_IMAGE_CSS, unsafe_allow_html=True)

# ---------- Import the original app so nothing breaks ----------
# Change this if your original main filename (without .py) is different.
# By default the user's main file has been: app_streamlit_weightbot.py
_ = importlib.import_module("app_streamlit_weightbot")
