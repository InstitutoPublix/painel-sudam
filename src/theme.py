"""Identidade visual clara (creme + verde institucional) do projeto de apoio ao PRDA."""
from __future__ import annotations

import base64
import json
import random

import plotly.graph_objects as go
import plotly.io as pio
import streamlit as st

from .data import ASSETS

# base
BG = "#FAF5E1"        # creme do emblema
SURFACE = "#FFFDF5"   # cartões
SIDEBAR = "#F1EACF"
INK = "#04413C"       # verde do emblema (títulos e destaques)
TEXT = "#1C2B27"
MUTED = "#5B6B65"
LINE = "rgba(4,65,60,0.14)"
GRID = "rgba(4,65,60,0.08)"
# apoio (tons da ilustração)
GREEN = "#00A85A"       # verde SUDAM
TEAL = "#16A3A0"
ORANGE = "#EE7D22"
SUN = "#FDC806"         # amarelo Publix
BLUE = "#0968B1"        # azul PNUD
BROWN = "#9A6A4C"
RED = "#C8462B"
ACCENT = INK

# do menor (claro) ao maior (verde-escuro)
SEQ = ["#E4EEC4", "#A9CF46", "#4DB06A", "#11806A", "#04413C"]
SEQ_CONT = [[0, "#F0F3D2"], [0.35, "#A9CF46"], [0.7, "#11806A"], [1, "#04413C"]]
COLORWAY = [INK, TEAL, ORANGE, BLUE, GREEN, "#D49A12", BROWN, "#8E9A93"]
LEVEL_COLOR = {"Brasil": "#5A6660", "Amazônia Legal": INK, "Grande Região": TEAL,
               "Estado": BLUE, "Município": ORANGE}

FONT = "Montserrat, 'Segoe UI', system-ui, sans-serif"

LOGOS = ASSETS / "logos"
BRAND = ASSETS / "brand"
_MIME = {".svg": "image/svg+xml", ".png": "image/png", ".webp": "image/webp", ".jpg": "image/jpeg",
         ".jpeg": "image/jpeg"}


def text_on(color: str) -> str:
    """Cor de texto legível sobre um fundo hex."""
    r, g, b = (int(color.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4))
    return TEXT if 0.299 * r + 0.587 * g + 0.114 * b > 150 else "#FFFFFF"


def register_plotly():
    t = go.layout.Template()
    t.layout = go.Layout(
        font=dict(family=FONT, color=TEXT, size=12),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        colorway=COLORWAY, margin=dict(l=10, r=10, t=30, b=10),
        xaxis=dict(gridcolor=GRID, zerolinecolor="rgba(4,65,60,0.25)", linecolor="rgba(4,65,60,0.25)",
                   automargin=True),
        yaxis=dict(gridcolor=GRID, zerolinecolor="rgba(4,65,60,0.25)", linecolor="rgba(4,65,60,0.25)",
                   automargin=True),
        legend=dict(bgcolor="rgba(0,0,0,0)", orientation="h", y=-0.18, font=dict(size=11)),
        hoverlabel=dict(bgcolor=SURFACE, bordercolor=INK, font=dict(family=FONT, color=TEXT)),
    )
    pio.templates["sudam"] = t
    pio.templates.default = "sudam"


CSS = f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Montserrat:wght@400;500;600;700;800&display=swap');
html, body, [class*="css"], .stApp {{ font-family: {FONT}; }}
.stApp {{ background: {BG}; color: {TEXT}; }}
header[data-testid="stHeader"] {{ background: transparent; }}
.block-container {{ padding-top: 1.1rem; max-width: 1500px; }}
section[data-testid="stSidebar"] {{ background: {SIDEBAR}; border-right: 1px solid {LINE}; }}
section[data-testid="stSidebar"] h3 {{ color: {INK}; font-size: .8rem; letter-spacing: .12em; text-transform: uppercase; }}
h1, h2, h3 {{ color: {INK}; }}

/* topo */
.topbar {{ display:flex; align-items:center; justify-content:space-between; gap:24px; padding:6px 4px 14px;
  border-bottom:1px solid {LINE}; margin-bottom:6px; flex-wrap:wrap; }}
.brand {{ display:flex; align-items:center; gap:14px; }}
.brand svg, .brand img {{ width:54px; height:54px; flex:0 0 54px; }}
.brand .t1 {{ font-weight:800; font-size:1.12rem; color:{INK}; line-height:1.2; }}
.brand .t2 {{ font-size:.78rem; color:{MUTED}; margin-top:3px; padding-top:3px; border-top:1px solid {INK}; }}
.logos {{ display:flex; align-items:center; gap:22px; }}
.logos img {{ height:44px; width:auto; display:block; }}
.logos img.pnud {{ height:52px; }} .logos img.publix {{ height:24px; }}
.logos span {{ font-weight:800; letter-spacing:.04em; font-size:.95rem; color:{INK}; }}
.logos small {{ display:block; font-weight:500; font-size:.55rem; letter-spacing:.18em; color:{MUTED}; text-align:center; }}
.logos .sep {{ width:1px; height:30px; background:{LINE}; }}

/* abas */
div[data-baseweb="tab-list"] {{ gap:4px; border-bottom:1px solid {LINE}; }}
button[data-baseweb="tab"] {{ background:transparent; padding:10px 16px; border-radius:8px 8px 0 0; }}
button[data-baseweb="tab"] p {{ font-weight:600; font-size:.88rem; color:{MUTED}; }}
button[data-baseweb="tab"][aria-selected="true"] p {{ color:{INK}; font-weight:700; }}
div[data-baseweb="tab-highlight"] {{ background:{INK}; height:3px; }}

/* capa */
.hero {{ display:grid; grid-template-columns: minmax(240px, 34%) 1fr; margin:14px 0 18px;
  border:1px solid {LINE}; border-radius:20px; overflow:hidden; background:{SURFACE}; }}
.hero .art {{ position:relative; min-height:300px; background:{INK}; }}
.hero .art > img, .hero .art > svg.mosaic {{ position:absolute; inset:0; width:100%; height:100%; object-fit:cover; }}
.hero .art .globe {{ position:absolute; left:50%; top:50%; transform:translate(-50%,-50%); width:62%;
  max-width:240px; aspect-ratio:1; border-radius:50%; background:{BG}; padding:6%;
  box-shadow:0 10px 30px rgba(0,0,0,.25); }}
.hero .art .globe svg {{ width:100%; height:100%; }}
.hero .txt {{ padding:30px 34px; display:flex; flex-direction:column; justify-content:center; }}
.hero h1 {{ font-size:2.5rem; font-weight:800; margin:0; line-height:1.12; color:{INK}; letter-spacing:-.02em; padding:0; }}
.hero .rule {{ height:2px; background:{INK}; margin:14px 0 8px; max-width:640px; }}
.hero .sub {{ font-size:1rem; font-weight:500; color:{TEXT}; margin-bottom:4px; }}
.hero .sub2 {{ color:{MUTED}; font-size:.85rem; margin-bottom:14px; }}
.hero p {{ color:{TEXT}; font-size:.9rem; max-width:760px; margin:0; }}
@media (max-width: 900px) {{ .hero {{ grid-template-columns:1fr; }} .hero .art {{ min-height:220px; }}
  .hero h1 {{ font-size:1.9rem; }} }}

/* cards */
.kpi {{ background:{SURFACE}; border:1px solid {LINE}; border-radius:14px; padding:14px 16px; height:100%;
  display:flex; gap:12px; align-items:center; min-height:92px; box-shadow:0 2px 8px rgba(4,65,60,.05); }}
.kpi .ic {{ flex:0 0 40px; height:40px; border-radius:10px; background:rgba(4,65,60,.08); color:{INK};
  display:flex; align-items:center; justify-content:center; font-weight:800; font-size:.7rem; text-align:center; }}
.kpi .lb {{ font-size:.7rem; letter-spacing:.06em; text-transform:uppercase; color:{MUTED}; font-weight:600; }}
.kpi .vl {{ font-size:1.55rem; font-weight:800; color:{TEXT}; line-height:1.15; }}
.kpi .sb {{ font-size:.74rem; color:{MUTED}; }}
.kpi.hi .vl {{ color:{INK}; }}
.kpi.hi .ic {{ background:{INK}; color:{BG}; }}
.kpi.lo .vl {{ color:{RED}; }}
.up {{ color:{GREEN}; font-weight:700; }} .down {{ color:{RED}; font-weight:700; }}

.panel-title {{ font-weight:700; color:{INK}; font-size:.98rem; margin:6px 0 0; }}
.panel-sub {{ color:{MUTED}; font-size:.76rem; margin-bottom:4px; }}
.chip {{ display:inline-block; padding:3px 10px; border:1px solid {LINE}; border-radius:999px;
  font-size:.7rem; color:{INK}; margin-right:6px; background:rgba(4,65,60,.06); }}
.note {{ border-left:3px solid {ORANGE}; background:rgba(238,125,34,.08); padding:8px 12px; border-radius:6px;
  color:{TEXT}; font-size:.8rem; margin:6px 0 10px; }}
.legend {{ display:flex; gap:12px; flex-wrap:wrap; font-size:.72rem; color:{TEXT}; }}
.legend em {{ color:{MUTED}; font-style:normal; }}
.legend .lnote {{ color:{MUTED}; font-size:.68rem; }}
.legend i {{ display:inline-block; width:11px; height:11px; border-radius:3px; margin-right:5px; vertical-align:-1px;
  border:1px solid {LINE}; }}
/* filtros: faixa "aplicados nesta página", grupos da barra lateral e etiqueta de gráfico fixo */
.fbar {{ display:flex; flex-wrap:wrap; gap:4px 16px; align-items:center; font-size:.76rem; color:{MUTED};
  padding:8px 14px; background:{SURFACE}; border:1px solid {LINE}; border-radius:10px; margin:6px 0 14px; }}
.fbar .t {{ font-weight:700; color:{INK}; text-transform:uppercase; letter-spacing:.06em; font-size:.68rem; }}
.fbar b {{ color:{TEXT}; font-weight:600; }}
.fgroup {{ font-weight:700; color:{INK}; font-size:.74rem; letter-spacing:.08em; text-transform:uppercase;
  margin:16px 0 0; padding-top:10px; border-top:1px solid {LINE}; }}
.fhint {{ font-size:.72rem; color:{MUTED}; margin:2px 0 8px; line-height:1.35; }}
.tag {{ display:inline-block; padding:1px 8px; border-radius:999px; font-size:.66rem; font-weight:600;
  background:rgba(238,125,34,.12); color:#9A4D0C; margin-left:6px; vertical-align:1px; }}
.footer {{ display:flex; align-items:center; justify-content:space-between; gap:16px; flex-wrap:wrap;
  color:{MUTED}; font-size:.72rem; padding:22px 0 6px; border-top:1px solid {LINE}; margin-top:30px; }}
.footer .logos img {{ height:30px; }} .footer .logos img.pnud {{ height:36px; }} .footer .logos img.publix {{ height:17px; }}

/* widgets */
div[data-testid="stMetric"] {{ background:{SURFACE}; border:1px solid {LINE}; border-radius:12px; padding:10px 14px; }}
.stDownloadButton button, .stButton button {{ border-radius:999px; border:1px solid {INK}; color:{INK}; background:transparent; font-weight:600; }}
.stDownloadButton button:hover, .stButton button:hover {{ background:{INK}; color:{BG}; border-color:{INK}; }}
div[data-testid="stDataFrame"] {{ border:1px solid {LINE}; border-radius:12px; }}
[data-testid="stExpander"] {{ border:1px solid {LINE}; border-radius:12px; background:{SURFACE}; }}
hr {{ border-color:{LINE} !important; }}
</style>
"""


def inject():
    register_plotly()
    st.markdown(CSS, unsafe_allow_html=True)


# --------------------------------------------------------------------------- #
# marca
# --------------------------------------------------------------------------- #
def emblem_svg(color: str = INK) -> str:
    """Emblema do projeto (rio e folhas num quadrado arredondado), redesenhado a partir da capa."""
    leaves = [(22, 22, 30), (34, 14, -20), (48, 22, 40), (70, 14, -30), (84, 26, 20), (20, 40, -35), (36, 34, 25),
              (78, 42, -15), (88, 62, 35), (24, 76, 30), (16, 88, -25), (34, 86, 20), (52, 88, -30), (76, 74, 25),
              (86, 86, -20), (60, 48, 30), (46, 60, -25), (68, 66, -40)]
    el = "".join(f'<ellipse cx="{x}" cy="{y}" rx="3" ry="4.8" transform="rotate({r} {x} {y})"/>' for x, y, r in leaves)
    return (f'<svg viewBox="0 0 100 100" xmlns="http://www.w3.org/2000/svg" aria-label="Emblema PRDA">'
            f'<defs><clipPath id="em"><rect x="6" y="6" width="88" height="88" rx="18"/></clipPath></defs>'
            f'<g clip-path="url(#em)" fill="none" stroke="{color}" stroke-width="4.5" stroke-linecap="round">'
            f'<path d="M2 58 C22 56 30 44 44 40 S70 34 74 20 S84 4 98 2"/>'
            f'<path d="M44 40 C40 30 30 26 26 8"/>'
            f'<path d="M30 100 C34 80 46 72 60 68 S86 58 100 50"/>'
            f'<path d="M60 68 C58 78 64 88 70 100"/></g>'
            f'<g fill="{color}" clip-path="url(#em)">{el}</g>'
            f'<rect x="6" y="6" width="88" height="88" rx="18" fill="none" stroke="{color}" stroke-width="6"/></svg>')


def emblem_html() -> str:
    """Emblema original (assets/logos/emblema.png); sem o arquivo, usa o redesenho em SVG."""
    uri = _data_uri(LOGOS / "emblema")
    return f'<img src="{uri}" alt="Emblema PRDA">' if uri else emblem_svg()


def _data_uri(stem) -> str | None:
    for ext, mime in _MIME.items():
        p = stem.with_suffix(ext)
        if p.exists():
            return f"data:{mime};base64,{base64.b64encode(p.read_bytes()).decode()}"
    return None


@st.cache_data(show_spinner=False)
def logos_html() -> str:
    """Logos de assets/logos/{pnud,sudam,publix}.(svg|png|webp|jpg); sem arquivo, mostra o nome em texto."""
    items = []
    for key, name, sub in (("pnud", "PNUD", "BRASIL"), ("sudam", "SUDAM", "AMAZÔNIA"), ("publix", "PUBLIX", "INSTITUTO")):
        uri = _data_uri(LOGOS / key)
        items.append(f'<img class="{key}" src="{uri}" alt="{name}">' if uri else f"<div><span>{name}</span><small>{sub}</small></div>")
    return '<div class="logos">' + '<div class="sep"></div>'.join(items) + "</div>"


def header():
    st.markdown(
        f"""<div class="topbar">
          <div class="brand">{emblem_html()}
            <div><div class="t1">Diagnóstico Quantitativo da Amazônia Legal</div>
            <div class="t2">Plano Regional de Desenvolvimento da Amazônia · PRDA</div></div></div>
          {logos_html()}</div>""",
        unsafe_allow_html=True)


def footer():
    st.markdown(f'<div class="footer"><div>Projeto BRA/21/005 · SUDAM · PNUD · Instituto Publix · PRDA · Produto 1'
                f'</div>{logos_html()}</div>', unsafe_allow_html=True)


# --------------------------------------------------------------------------- #
# capa
# --------------------------------------------------------------------------- #
@st.cache_data(show_spinner=False)
def mosaic_svg(cols: int = 6, rows: int = 8, seed: int = 7) -> str:
    """Mosaico geométrico nas cores da ilustração (usado enquanto não houver a arte em assets/brand)."""
    rnd = random.Random(seed)
    pal = [INK, "#11806A", GREEN, "#A9CF46", TEAL, BLUE, SUN, ORANGE]
    s, out = 50, []
    for r in range(rows):
        for c in range(cols):
            x, y = c * s, r * s
            out.append(f'<rect x="{x}" y="{y}" width="{s}" height="{s}" fill="{rnd.choice(pal)}"/>')
            k, fg = rnd.random(), rnd.choice(pal)
            if k < .3:
                out.append(f'<path d="M{x} {y + s} L{x + s} {y} L{x + s} {y + s}Z" fill="{fg}"/>')
            elif k < .55:
                out.append(f'<path d="M{x} {y + s} A{s} {s} 0 0 1 {x + s} {y + s}Z" fill="{fg}" '
                           f'transform="rotate({rnd.choice([0, 90, 180, 270])} {x + s / 2} {y + s / 2})"/>')
            elif k < .7:
                out.append("".join(f'<rect x="{x}" y="{y + i * 10 + 2}" width="{s}" height="5" fill="{fg}"/>'
                                   for i in range(5)))
            elif k < .82:
                out.append(f'<ellipse cx="{x + s / 2}" cy="{y + s / 2}" rx="9" ry="17" fill="{fg}" '
                           f'transform="rotate({rnd.choice([-35, 35])} {x + s / 2} {y + s / 2})"/>')
    return (f'<svg class="mosaic" viewBox="0 0 {cols * s} {rows * s}" preserveAspectRatio="xMidYMid slice" '
            f'xmlns="http://www.w3.org/2000/svg">{"".join(out)}</svg>')


@st.cache_data(show_spinner=False)
def dotted_brazil_svg(al_codes: tuple[str, ...], step: float = 0.6) -> str:
    """Mapa do Brasil em pontos, com a Amazônia Legal em verde institucional."""
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
    for m, color, r in ((in_rest, "#B9CDB4", 2.0), (in_al, INK, 2.3)):
        for x, y in zip(xs[m], ys[m]):
            dots.append(f'<circle cx="{px(x):.1f}" cy="{py(y):.1f}" r="{r}" fill="{color}"/>')
    return f'<svg viewBox="0 0 {W:.0f} {H:.0f}" xmlns="http://www.w3.org/2000/svg">{"".join(dots)}</svg>'


def hero(al_codes: tuple[str, ...], n_mun: int, n_ufs: int):
    art = _data_uri(BRAND / "ilustracao")
    left = (f'<img src="{art}" alt="">' if art else
            f'{mosaic_svg()}<div class="globe">{dotted_brazil_svg(al_codes)}</div>')
    st.markdown(
        f"""<div class="hero"><div class="art">{left}</div><div class="txt">
        <h1>Diagnóstico Quantitativo da Amazônia Legal</h1>
        <div class="rule"></div>
        <div class="sub">Superintendência de Desenvolvimento da Amazônia</div>
        <div class="sub2">{n_ufs} estados · {n_mun} municípios · Projeto BRA/21/005 · SUDAM · PNUD · Instituto Publix</div>
        <p>Explore os indicadores por <b>Brasil, Amazônia Legal, Grandes Regiões, Estados e Municípios</b>:
        mapas temáticos, séries históricas, rankings e comparações entre territórios e escalas.</p>
        </div></div>""",
        unsafe_allow_html=True)


def kpi(label: str, value: str, sub: str = "", icon: str = "●", cls: str = "") -> str:
    return (f'<div class="kpi {cls}"><div class="ic">{icon}</div><div><div class="lb">{label}</div>'
            f'<div class="vl">{value}</div><div class="sb">{sub}</div></div></div>')


def title(text: str, sub: str = "", fixo: bool = False):
    """Título e subtítulo de um gráfico; fixo=True marca os que não mudam com os filtros de território."""
    tag = '<span class="tag">não muda com os filtros de território</span>' if fixo else ""
    st.markdown(f'<div class="panel-title">{text}{tag}</div><div class="panel-sub">{sub}</div>', unsafe_allow_html=True)
