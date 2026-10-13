"""Identidade visual (verde-escuro + lima) inspirada no painel ICG."""
from __future__ import annotations

import json

import plotly.graph_objects as go
import plotly.io as pio
import streamlit as st

from .data import ASSETS

BG = "#04140B"
PANEL = "rgba(255,255,255,0.045)"
LINE = "rgba(198,244,50,0.16)"
LIME = "#C6F432"
GREEN = "#1FAE4B"
TEXT = "#EAF5EC"
MUTED = "#8FAF9A"
# do menor (escuro) ao maior (lima)
SEQ = ["#0E4D27", "#17803B", "#34B04A", "#8FD23C", "#D4F73A"]
SEQ_CONT = [[0, "#0B3A1E"], [0.35, "#17803B"], [0.7, "#8FD23C"], [1, "#E4FF4A"]]
COLORWAY = [LIME, "#19D3A2", "#F9C80E", "#3FA7FF", "#F58220", "#A98BFF", "#FF6B9A", "#9AA7A0"]
LEVEL_COLOR = {"Brasil": "#FFFFFF", "Amazônia Legal": LIME, "Grande Região": "#19D3A2",
               "Estado": "#3FA7FF", "Município": "#F9C80E"}

FONT = "Montserrat, 'Segoe UI', system-ui, sans-serif"


def register_plotly():
    t = go.layout.Template()
    t.layout = go.Layout(
        font=dict(family=FONT, color=TEXT, size=12),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        colorway=COLORWAY, margin=dict(l=10, r=10, t=30, b=10),
        xaxis=dict(gridcolor="rgba(255,255,255,0.07)", zerolinecolor="rgba(255,255,255,0.15)",
                   linecolor="rgba(255,255,255,0.18)", automargin=True),
        yaxis=dict(gridcolor="rgba(255,255,255,0.07)", zerolinecolor="rgba(255,255,255,0.15)",
                   linecolor="rgba(255,255,255,0.18)", automargin=True),
        legend=dict(bgcolor="rgba(0,0,0,0)", orientation="h", y=-0.18, font=dict(size=11)),
        hoverlabel=dict(bgcolor="#0A2415", bordercolor=LIME, font=dict(family=FONT, color=TEXT)),
    )
    pio.templates["sudam"] = t
    pio.templates.default = "sudam"


CSS = f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Montserrat:wght@400;500;600;700;800&display=swap');
html, body, [class*="css"], .stApp {{ font-family: {FONT}; }}
.stApp {{
  background:
    radial-gradient(1100px 520px at 12% -8%, rgba(31,174,75,.28), transparent 60%),
    radial-gradient(900px 500px at 100% 0%, rgba(198,244,50,.10), transparent 55%),
    {BG};
}}
header[data-testid="stHeader"] {{ background: transparent; }}
.block-container {{ padding-top: 1.1rem; max-width: 1500px; }}
section[data-testid="stSidebar"] {{ background: #061c10; border-right: 1px solid {LINE}; }}
section[data-testid="stSidebar"] h3 {{ color: {LIME}; font-size: .8rem; letter-spacing: .12em; text-transform: uppercase; }}

/* topo */
.topbar {{ display:flex; align-items:center; justify-content:space-between; gap:24px; padding:6px 4px 14px;
  border-bottom:1px solid {LINE}; margin-bottom:6px; flex-wrap:wrap; }}
.brand {{ display:flex; align-items:center; gap:14px; }}
.brand .mark {{ font-weight:800; font-size:2.1rem; letter-spacing:-.02em; color:#fff; line-height:1; }}
.brand .mark em {{ font-style:normal; color:{LIME}; }}
.brand .t1 {{ font-weight:700; font-size:1.05rem; color:#fff; }}
.brand .t2 {{ font-size:.78rem; color:{LIME}; }}
.logos {{ display:flex; align-items:center; gap:22px; color:#fff; opacity:.92; }}
.logos span {{ font-weight:800; letter-spacing:.04em; font-size:.95rem; }}
.logos small {{ display:block; font-weight:500; font-size:.55rem; letter-spacing:.18em; color:{MUTED}; text-align:center; }}
.logos .sep {{ width:1px; height:26px; background:{LINE}; }}

/* abas */
div[data-baseweb="tab-list"] {{ gap:4px; border-bottom:1px solid {LINE}; }}
button[data-baseweb="tab"] {{ background:transparent; padding:10px 16px; border-radius:8px 8px 0 0; }}
button[data-baseweb="tab"] p {{ font-weight:600; font-size:.88rem; color:#cfe3d4; }}
button[data-baseweb="tab"][aria-selected="true"] p {{ color:{LIME}; }}
div[data-baseweb="tab-highlight"] {{ background:{LIME}; height:3px; }}

/* hero */
.hero {{ display:grid; grid-template-columns: 300px 1fr; gap:34px; align-items:center; padding:22px 26px;
  margin:14px 0 18px; border:1px solid {LINE}; border-radius:20px;
  background: linear-gradient(120deg, rgba(31,174,75,.18), rgba(4,20,11,.2) 55%); }}
.hero svg {{ width:100%; height:auto; }}
.hero h1 {{ font-size:3.6rem; font-weight:800; margin:0; line-height:1; color:#fff; letter-spacing:-.03em; }}
.hero h1 em {{ font-style:normal; color:{LIME}; }}
.hero .sub {{ font-size:1.15rem; font-weight:600; margin:.5rem 0 .15rem; color:#fff; }}
.hero .sub2 {{ color:{LIME}; font-size:.9rem; margin-bottom:14px; }}
.hero p {{ color:#c4dacb; font-size:.9rem; max-width:760px; margin:0; }}
@media (max-width: 900px) {{ .hero {{ grid-template-columns:1fr; }} .hero h1 {{ font-size:2.6rem; }} }}

/* cards */
.kpi {{ background:{PANEL}; border:1px solid {LINE}; border-radius:14px; padding:14px 16px; height:100%;
  display:flex; gap:12px; align-items:center; min-height:92px; }}
.kpi .ic {{ flex:0 0 40px; height:40px; border-radius:10px; background:rgba(198,244,50,.12); color:{LIME};
  display:flex; align-items:center; justify-content:center; font-weight:800; font-size:.7rem; text-align:center; }}
.kpi .lb {{ font-size:.7rem; letter-spacing:.06em; text-transform:uppercase; color:{MUTED}; font-weight:600; }}
.kpi .vl {{ font-size:1.55rem; font-weight:800; color:#fff; line-height:1.15; }}
.kpi .sb {{ font-size:.74rem; color:#b6cdbc; }}
.kpi.hi .vl {{ color:{LIME}; }}
.kpi.lo .vl {{ color:#FF7A59; }}
.up {{ color:{LIME}; font-weight:700; }} .down {{ color:#FF7A59; font-weight:700; }}

.panel-title {{ font-weight:700; color:#fff; font-size:.98rem; margin:6px 0 0; }}
.panel-sub {{ color:{MUTED}; font-size:.76rem; margin-bottom:4px; }}
.chip {{ display:inline-block; padding:3px 10px; border:1px solid {LINE}; border-radius:999px;
  font-size:.7rem; color:{LIME}; margin-right:6px; background:rgba(198,244,50,.06); }}
.note {{ border-left:3px solid {LIME}; background:rgba(198,244,50,.06); padding:8px 12px; border-radius:6px;
  color:#cfe3d4; font-size:.8rem; margin:6px 0 10px; }}
.legend {{ display:flex; gap:12px; flex-wrap:wrap; font-size:.72rem; color:#cfe3d4; }}
.legend i {{ display:inline-block; width:11px; height:11px; border-radius:3px; margin-right:5px; vertical-align:-1px; }}
.footer {{ text-align:center; color:{MUTED}; font-size:.72rem; padding:26px 0 6px; border-top:1px solid {LINE}; margin-top:30px; }}

/* widgets */
div[data-testid="stMetric"] {{ background:{PANEL}; border:1px solid {LINE}; border-radius:12px; padding:10px 14px; }}
.stDownloadButton button, .stButton button {{ border-radius:999px; border:1px solid {LIME}; color:{LIME}; background:transparent; font-weight:600; }}
.stDownloadButton button:hover, .stButton button:hover {{ background:{LIME}; color:#04140B; border-color:{LIME}; }}
div[data-testid="stDataFrame"] {{ border:1px solid {LINE}; border-radius:12px; }}
[data-testid="stExpander"] {{ border:1px solid {LINE}; border-radius:12px; background:{PANEL}; }}
</style>
"""


def inject():
    register_plotly()
    st.markdown(CSS, unsafe_allow_html=True)


def header():
    st.markdown(
        """<div class="topbar">
          <div class="brand"><div class="mark">PR<em>DA</em></div>
            <div><div class="t1">Diagnóstico Quantitativo da Amazônia Legal</div>
            <div class="t2">Painel interativo de indicadores territoriais</div></div></div>
          <div class="logos"><div><span>PNUD</span><small>BRASIL</small></div><div class="sep"></div>
            <div><span>SUDAM</span><small>AMAZÔNIA</small></div><div class="sep"></div>
            <div><span>PUBLIX</span><small>INSTITUTO</small></div></div></div>""",
        unsafe_allow_html=True)


@st.cache_data(show_spinner=False)
def dotted_brazil_svg(al_codes: tuple[str, ...], step: float = 0.6) -> str:
    """Mapa do Brasil em pontos (Amazônia Legal em lima), como na capa do ICG."""
    import numpy as np
    import shapely
    from shapely.geometry import shape
    from shapely.ops import unary_union

    gj = json.loads((ASSETS / "geo" / "uf.json").read_text())
    al, rest = [], []
    for f in gj["features"]:
        (al if f["properties"]["codarea"] in al_codes else rest).append(shape(f["geometry"]))
    g_al, g_rest = unary_union(al), unary_union(rest)
    x0, x1, y0, y1 = -74.2, -34.5, -33.9, 5.4
    xs, ys = np.meshgrid(np.arange(x0, x1, step), np.arange(y0, y1, step))
    xs, ys = xs.ravel(), ys.ravel()
    in_al, in_rest = shapely.contains_xy(g_al, xs, ys), shapely.contains_xy(g_rest, xs, ys)
    W, H = 300, 300 * (y1 - y0) / (x1 - x0)
    px = lambda x: (x - x0) / (x1 - x0) * W  # noqa: E731
    py = lambda y: (y1 - y) / (y1 - y0) * H  # noqa: E731
    dots = []
    for m, color, r, op in ((in_rest, "#2f8a4d", 2.0, .55), (in_al, LIME, 2.3, 1)):
        for x, y in zip(xs[m], ys[m]):
            dots.append(f'<circle cx="{px(x):.1f}" cy="{py(y):.1f}" r="{r}" fill="{color}" opacity="{op}"/>')
    ring = f'<circle cx="{W/2}" cy="{H/2}" r="{min(W,H)/2-3:.0f}" fill="none" stroke="{LIME}" stroke-opacity=".35"/>'
    return f'<svg viewBox="0 0 {W:.0f} {H:.0f}" xmlns="http://www.w3.org/2000/svg">{ring}{"".join(dots)}</svg>'


def hero(al_codes: tuple[str, ...], n_mun: int, n_ufs: int):
    svg = dotted_brazil_svg(al_codes)
    st.markdown(
        f"""<div class="hero"><div>{svg}</div><div>
        <h1>PR<em>DA</em></h1>
        <div class="sub">Diagnóstico Quantitativo da Amazônia Legal</div>
        <div class="sub2">{n_ufs} estados · {n_mun} municípios · Projeto BRA/21/005 · SUDAM · PNUD · Instituto Publix</div>
        <p>Explore os indicadores por <b>Brasil, Amazônia Legal, Grandes Regiões, Estados e Municípios</b>:
        mapas temáticos, séries históricas, rankings e comparações entre territórios e escalas.</p>
        </div></div>""",
        unsafe_allow_html=True)


def kpi(label: str, value: str, sub: str = "", icon: str = "●", cls: str = "") -> str:
    return (f'<div class="kpi {cls}"><div class="ic">{icon}</div><div><div class="lb">{label}</div>'
            f'<div class="vl">{value}</div><div class="sb">{sub}</div></div></div>')


def title(text: str, sub: str = ""):
    st.markdown(f'<div class="panel-title">{text}</div><div class="panel-sub">{sub}</div>', unsafe_allow_html=True)
