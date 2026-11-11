"""Identidade visual clara (creme + verde institucional) do projeto de apoio ao PRDA."""
from __future__ import annotations

import re
import base64
import html

import plotly.graph_objects as go
import plotly.io as pio
import streamlit as st

from .data import ASSETS

# base
BG = "#FAF5E1"        # creme do emblema
SURFACE = "#FFFDF5"   # cartões
SIDEBAR = "#F1EACE"
NAV = "#EAE3C7"       # faixa das abas e alça da barra lateral
CARD = "#FFFCF5"      # cartões de contexto do topo de cada aba
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
# situação conforme a polaridade do indicador (azul = melhor, vermelho = pior)
MELHOR = GREEN
PIOR = RED

# do menor (claro) ao maior (verde-escuro)
SEQ = ["#E4EEC4", "#A9CF46", "#4DB06A", "#11806A", "#04413C"]
SEQ_CONT = [[0, "#F0F3D2"], [0.35, "#A9CF46"], [0.7, "#11806A"], [1, "#04413C"]]
COLORWAY = [INK, TEAL, ORANGE, BLUE, GREEN, "#D49A12", BROWN, "#8E9A93"]
LEVEL_COLOR = {"Brasil": "#5A6660", "Amazônia Legal": INK, "Grande Região": TEAL,
               "Estado": BLUE, "Município": ORANGE}

PAD = "1.5rem"  # margem lateral do conteúdo; o topo e a faixa das abas vão até a borda
T_MOS = 38      # lado de cada ícone do mosaico do topo, em px

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
/* a barra fixa do topo é transparente e cobre o alto da página ao rolar: só os botões dela recebem o clique */
header[data-testid="stHeader"] {{ background: transparent; height:0; }}
header[data-testid="stHeader"], header[data-testid="stHeader"] * {{ pointer-events: none !important; }}
header[data-testid="stHeader"] :is(button, a, [role="button"]) {{ pointer-events: auto !important; }}
/* menu do Streamlit (canto direito): numa pílula creme, legível sobre o mosaico */
:is([data-testid="stMainMenu"], [data-testid="stToolbarActions"]:not(:empty)) {{ background:rgba(250,245,226,.94);
  border-radius:9px; box-shadow:0 1px 4px rgba(4,65,60,.18); }}
[data-testid="stAppDeployButton"] {{ display:none; }}
.block-container {{ padding:0 {PAD} 3rem !important; max-width:none !important; }}
/* alça da barra lateral: aba bege no meio da borda, sempre visível, com um triângulo para recolher ou abrir.
   will-change faz a barra ser a referência do position:fixed, então a alça acompanha a largura dela e não rola */
section[data-testid="stSidebar"] {{ will-change:transform; }}
[data-testid="stSidebarCollapseButton"] {{ position:fixed; top:calc(50% - 36px); right:-14px; z-index:1000;
  visibility:visible !important; }}
:is([data-testid="stSidebarCollapseButton"] button, [data-testid="stExpandSidebarButton"]) {{
  visibility:visible !important; width:14px; min-width:0; height:72px; min-height:0; padding:0; border:none !important;
  border-radius:0 7px 7px 0; background:{NAV} !important; box-shadow:1px 0 4px rgba(60,50,20,.18);
  display:flex; align-items:center; justify-content:center; }}
[data-testid="stExpandSidebarButton"] {{ position:fixed; left:0; top:calc(50% - 36px); z-index:1000; }}
:is([data-testid="stSidebarCollapseButton"] button, [data-testid="stExpandSidebarButton"]) [data-testid="stIconMaterial"] {{
  display:none; }}
:is([data-testid="stSidebarCollapseButton"] button, [data-testid="stExpandSidebarButton"])::after {{ content:"";
  border-top:7px solid transparent; border-bottom:7px solid transparent; }}
[data-testid="stSidebarCollapseButton"] button::after {{ border-right:8px solid {INK}; margin-left:-1px; }}
[data-testid="stExpandSidebarButton"]::after {{ border-left:8px solid {INK}; margin-left:1px; }}
:is([data-testid="stSidebarCollapseButton"] button, [data-testid="stExpandSidebarButton"]):hover {{ background:#DFD6B4 !important; }}
section[data-testid="stSidebar"] {{ background: {SIDEBAR}; border-right: 1px solid {LINE}; }}
section[data-testid="stSidebar"] h3 {{ color: {INK}; font-size: .8rem; letter-spacing: .12em; text-transform: uppercase; }}
/* barra lateral: rótulos fortes e campos claros com borda, para as opções saltarem do fundo */
section[data-testid="stSidebar"] [data-testid="stWidgetLabel"] p {{ font-weight:700; color:{TEXT}; font-size:.86rem; }}
/* caixas de seleção, campos de texto e botões em todo o painel: fundo claro e borda, para saltarem do fundo bege */
:is([data-testid="stSelectbox"], [data-testid="stMultiSelect"]) [role="group"],
[data-testid="stTextInputRootElement"] {{
  background:{SURFACE} !important; border:1px solid rgba(4,65,60,.30) !important; border-radius:9px !important; }}
:is([data-testid="stSelectbox"], [data-testid="stMultiSelect"]) [role="group"]:hover,
[data-testid="stTextInputRootElement"]:hover, [data-testid="stTextInputRootElement"]:focus-within {{
  border-color:{INK} !important; }}
button[data-testid="stBaseButton-secondary"] {{ background:{SURFACE} !important; border:1px solid {INK} !important;
  color:{INK} !important; border-radius:9px !important; font-weight:600; }}
button[data-testid="stBaseButton-secondary"]:hover:not(:disabled) {{ background:{INK} !important; color:{BG} !important; }}
button[data-testid="stBaseButton-secondary"]:hover:not(:disabled) * {{ color:{BG} !important; }}
button[data-testid="stBaseButton-secondary"]:disabled {{ border-color:rgba(4,65,60,.25) !important;
  color:rgba(4,65,60,.45) !important; }}
section[data-testid="stSidebar"] [role="radiogroup"] label p {{ font-size:.86rem; }}
section[data-testid="stSidebar"] [data-testid="stExpander"] details {{ background:{SURFACE}; border-color:rgba(4,65,60,.28); }}
.sbtopo {{ margin:2px 0 4px; }}
.sbtopo .t {{ font-size:.8rem; font-weight:800; letter-spacing:.14em; text-transform:uppercase; color:{INK}; }}
.sbtopo .aba {{ display:inline-block; margin-top:6px; font-size:.76rem; color:{MUTED}; }}
.sbtopo .aba b {{ background:{INK}; color:{BG}; padding:2px 9px; border-radius:999px; font-weight:700; margin-left:3px;
  display:inline-block; white-space:nowrap; }}
.sbinfo {{ background:rgba(255,253,245,.65); border:1px solid {LINE}; border-radius:10px; padding:8px 11px;
  margin:-4px 0 14px; font-size:.75rem; color:{MUTED}; line-height:1.45; }}
.sbinfo div + div {{ margin-top:3px; }}
.sbinfo b {{ color:{TEXT}; font-weight:700; }}
h1, h2, h3 {{ color: {INK}; }}

/* topo: marca do projeto, título do painel e mosaico da identidade visual com os logos, até a borda direita */
.topo {{ display:flex; align-items:center; margin:-1rem -{PAD} 0 0; min-height:{3 * T_MOS + 7}px; }}
.topo .marca {{ flex:none; display:flex; align-items:center; gap:10px; padding:12px 0; }}
.topo .marca img, .topo .marca svg {{ width:76px; height:76px; flex:0 0 76px; }}
.topo .m1 {{ font-weight:700; font-size:.8rem; line-height:1.22; color:{INK}; padding-bottom:3px;
  border-bottom:1px solid {INK}; }}
.topo .m2 {{ font-size:.5rem; color:{TEXT}; margin-top:3px; letter-spacing:.01em; }}
.topo .sv {{ flex:none; width:1px; align-self:stretch; background:rgba(4,65,60,.35); margin:18px 26px; }}
/* o título cede espaço primeiro (quebra em duas linhas) para o mosaico aparecer inteiro; só em telas estreitas o
   mosaico também encolhe, perdendo os ícones soltos da esquerda */
.topo .titulo {{ flex:0 100 auto; min-width:260px; margin-right:26px; font-weight:700; font-size:1.42rem; line-height:1.2; color:{INK};
  letter-spacing:-.005em; text-wrap:balance; }}
.topo .mos {{ flex:0 1 {round(15.28 * T_MOS)}px; min-width:345px; align-self:flex-start; position:relative; height:{3 * T_MOS + 7}px; overflow:hidden;
  margin-left:auto; max-width:{round(15.28 * T_MOS)}px; }}
.topo .mos > img {{ position:absolute; right:0; top:0; height:100%; width:auto; max-width:none; }}
.topo .assin {{ position:absolute; right:0; top:{round(.9 * T_MOS)}px; height:{round(1.3 * T_MOS)}px;
  width:{round(8.75 * T_MOS)}px; background:{SIDEBAR}; border-radius:12px 0 0 12px; display:flex; align-items:center;
  justify-content:center; box-shadow:0 1px 5px rgba(60,50,20,.18); }}
.topo .assin img {{ height:34px; width:auto; max-width:92%; object-fit:contain; display:block; }}
@media (max-width: 1100px) {{ .topo {{ flex-wrap:wrap; }} .topo .sv {{ display:none; }}
  .topo .titulo {{ flex-basis:100%; order:3; padding:4px 0 12px; }} .topo .mos {{ margin-left:auto; }} }}

/* logos avulsos (rodapé) */
.logos {{ display:flex; align-items:center; gap:22px; }}
.logos img {{ height:44px; width:auto; display:block; }}
.logos img.pnud {{ height:52px; }} .logos img.publix {{ height:24px; }}
.logos span {{ font-weight:800; letter-spacing:.04em; font-size:.95rem; color:{INK}; }}
.logos small {{ display:block; font-weight:500; font-size:.55rem; letter-spacing:.18em; color:{MUTED}; text-align:center; }}
.logos .sep {{ width:1px; height:30px; background:{LINE}; }}
.logos.assinatura img {{ height:50px; max-width:100%; object-fit:contain; }}

/* abas: faixa bege de borda a borda, logo abaixo do topo; a aberta fica em negrito */
.st-key-aba > div > [role="tablist"] {{ background:{NAV}; margin:0 -{PAD}; padding:0 calc({PAD} - 12px); gap:2px;
  border:none; box-shadow:none; }}
.st-key-aba > div > [role="tablist"] > [data-testid="stTab"] {{ padding:9px 12px; margin:0; background:transparent; }}
.st-key-aba > div > [role="tablist"] > [data-testid="stTab"] p {{ font-size:.8rem; font-weight:500; color:{TEXT}; }}
.st-key-aba > div > [role="tablist"] > [data-testid="stTab"]:hover p {{ color:{INK}; }}
.st-key-aba > div > [role="tablist"] > [data-testid="stTab"][aria-selected="true"] p {{ font-weight:800; color:{INK}; }}
.st-key-aba > div > [role="tablist"] .react-aria-SelectionIndicator {{ display:none; }}

/* título da aba aberta, abaixo dos cartões de contexto */
.pagina {{ font-size:2.05rem; font-weight:800; color:{INK}; letter-spacing:-.01em; line-height:1.15; margin:8px 0 4px; }}

/* seções do Perfil do Território: barra de botões, mais visível que abas comuns */
.secoes-tit {{ font-size:.72rem; letter-spacing:.08em; text-transform:uppercase; color:{MUTED}; font-weight:700;
  margin:10px 0 4px; }}
.st-key-terr_sec [role="tablist"] {{ gap:6px; background:rgba(4,65,60,.07); padding:6px; border-radius:14px;
  border:none; width:fit-content; max-width:100%; flex-wrap:wrap; margin-bottom:10px; }}
.st-key-terr_sec [role="tab"] {{ padding:10px 22px; border-radius:10px; background:transparent; cursor:pointer;
  transition:background .15s; }}
.st-key-terr_sec [role="tab"] p {{ font-size:1.02rem; font-weight:700; color:{INK}; }}
.st-key-terr_sec [role="tab"]:hover {{ background:rgba(4,65,60,.12); }}
.st-key-terr_sec [role="tab"][aria-selected="true"] {{ background:{INK}; box-shadow:0 2px 8px rgba(4,65,60,.25); }}
.st-key-terr_sec [role="tab"][aria-selected="true"] p {{ color:{BG}; }}
.st-key-terr_sec .react-aria-SelectionIndicator {{ display:none; }}

/* cards */
.kpi {{ background:{SURFACE}; border:1px solid {LINE}; border-radius:14px; padding:14px 16px; height:100%;
  display:flex; gap:12px; align-items:center; min-height:92px; box-shadow:0 2px 8px rgba(4,65,60,.05); }}
.kpi .ic {{ flex:0 0 40px; height:40px; border-radius:10px; background:rgba(4,65,60,.08); color:{INK};
  display:flex; align-items:center; justify-content:center; font-weight:800; font-size:.7rem; text-align:center; }}
.kpi .lb {{ font-size:.7rem; letter-spacing:.06em; text-transform:uppercase; color:{MUTED}; font-weight:600; }}
/* palavras inteiras (sem "AMAZÔNI-A"); em cartões estreitos (telas de notebook), o ícone sai para sobrar espaço */
.kpi {{ container-type:inline-size; }}
.kpi :is(.lb, .vl, .sb) {{ overflow-wrap:normal; word-break:normal; hyphens:none; }}
@container (max-width: 140px) {{ .kpi .ic {{ display:none; }} .kpi .vl {{ font-size:1.35rem; }} }}
.kpi > div:last-child {{ min-width:0; }}
.kpi .nw {{ white-space:nowrap; }}
.kpi .un {{ font-size:.6em; font-weight:700; }}
.kpi .vl {{ font-size:1.55rem; font-weight:800; color:{TEXT}; line-height:1.15; }}
.kpi .sb {{ font-size:.74rem; color:{MUTED}; }}
.kpi.hi .vl {{ color:{INK}; }}
.kpi.hi .ic {{ background:{INK}; color:{BG}; }}
.kpi.lo .vl {{ color:{RED}; }}
.kpi.sel {{ border:2px solid {INK}; box-shadow:0 3px 12px rgba(4,65,60,.16); }}

/* cartões pequenos com tendência (Visão Geral, eixo a eixo): altura fixa para a grade ficar alinhada */
.mini {{ background:{SURFACE}; border:1px solid {LINE}; border-radius:14px; padding:12px 14px 8px; height:212px;
  display:flex; flex-direction:column; margin-bottom:14px; box-shadow:0 2px 8px rgba(4,65,60,.05); }}
.mini.sel {{ border:2px solid {INK}; box-shadow:0 3px 12px rgba(4,65,60,.16); }}
.mini .lb {{ font-size:.68rem; letter-spacing:.05em; text-transform:uppercase; color:{MUTED}; font-weight:700;
  line-height:1.25; min-height:2.5em; display:-webkit-box; -webkit-line-clamp:2; -webkit-box-orient:vertical;
  overflow:hidden; }}
.mini.sel .lb {{ color:{INK}; }}
.mini .vl {{ font-size:1.45rem; font-weight:800; color:{TEXT}; line-height:1.2; }}
.mini .sb {{ font-size:.86rem; color:{MUTED}; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }}
.mini .dl {{ font-size:.88rem; min-height:1.2em; }}
.mini .dl .rs {{ font-size:.72rem; line-height:1.25; color:{MUTED}; display:-webkit-box; -webkit-line-clamp:2;
                 -webkit-box-orient:vertical; overflow:hidden; }}
.mini .sp {{ margin-top:auto; }}
.mini .sp svg {{ display:block; width:100%; height:38px; overflow:visible; }}
.mini .yr {{ display:flex; justify-content:space-between; font-size:.78rem; color:{MUTED}; gap:6px; }}
.mini .yr b {{ color:{TEXT}; font-weight:700; }}
.mini .yr.c span {{ flex:1; text-align:center; font-weight:600; }}
.mini .bv {{ position:absolute; transform:translate(-50%,-115%); font-size:.84rem; font-weight:700; color:{TEXT}; white-space:nowrap; }}
/* passar o mouse na linha: ponto, guia vertical e etiqueta "ano: valor" (HTML sobre o SVG, sem deformar o ponto) */
.mini .sp {{ position:relative; }}
.mini .hz-area {{ position:absolute; left:0; right:0; top:0; height:38px; }}
.mini .hz {{ position:absolute; top:0; bottom:0; }}
.mini .hz b {{ display:none; position:absolute; top:0; bottom:0; border-left:1px dashed rgba(4,65,60,.45); }}
.mini .hz i {{ display:none; position:absolute; width:9px; height:9px; border-radius:50%; background:{INK};
  border:2px solid {SURFACE}; box-shadow:0 0 0 1px {INK}; transform:translate(-50%,-50%); }}
.mini .hz span {{ display:none; position:absolute; background:{INK}; color:{BG}; font-size:.68rem; font-weight:600;
  padding:2px 7px; border-radius:6px; white-space:nowrap; z-index:5; box-shadow:0 2px 6px rgba(4,65,60,.25); }}
.mini .hz:hover b, .mini .hz:hover i, .mini .hz:hover span {{ display:block; }}
.mini .nota {{ margin-top:auto; height:50px; display:flex; align-items:center; justify-content:center;
  font-size:.7rem; color:{MUTED}; background:rgba(4,65,60,.04); border-radius:8px; text-align:center; padding:0 8px; }}
.up {{ color:{GREEN}; font-weight:700; }} .down {{ color:{RED}; font-weight:700; }}
.neutro {{ color:{TEXT}; font-weight:700; }}

.panel-title {{ font-weight:700; color:{INK}; font-size:.98rem; margin:6px 0 0; }}
.panel-sub {{ color:{MUTED}; font-size:.76rem; margin-bottom:4px; }}
.chip {{ display:inline-block; padding:3px 10px; border:1px solid {LINE}; border-radius:999px;
  font-size:.7rem; color:{INK}; margin-right:6px; background:rgba(4,65,60,.06); }}
.note {{ border-left:3px solid {ORANGE}; background:rgba(238,125,34,.08); padding:8px 12px; border-radius:6px;
  color:{TEXT}; font-size:.8rem; margin:6px 0 10px; }}
.legend {{ display:flex; flex-direction:column; gap:5px; font-size:.72rem; color:{TEXT}; }}
.legend .litens {{ display:flex; gap:6px 14px; flex-wrap:wrap; }}
.legend em {{ color:{MUTED}; font-style:normal; }}
.legend .lnote {{ color:{MUTED}; font-size:.68rem; }}
.legend i {{ display:inline-block; width:11px; height:11px; border-radius:3px; margin-right:5px; vertical-align:-1px;
  border:1px solid {LINE}; }}
/* filtros: grupos da barra lateral e etiqueta de gráfico fixo */

/* "Como ler": explicação curta e leitura dos dados logo abaixo de um gráfico */
.ler {{ background:rgba(4,65,60,.05); border-radius:10px; padding:9px 13px; margin:2px 0 12px; font-size:.82rem;
  color:{TEXT}; line-height:1.55; }}
.ler .lt {{ font-weight:800; color:{INK}; margin-right:4px; }}
.ler .dado {{ display:block; margin-top:4px; color:{INK}; }}

/* cartões de contexto no topo de cada aba: filtros aplicados e ficha resumida do indicador, lado a lado */
.ctxrow {{ display:flex; flex-wrap:wrap; gap:12px; align-items:stretch; margin:0 0 6px; }}
.ctx {{ flex:1 1 420px; background:{CARD}; border-radius:9px; padding:10px 16px 11px;
  box-shadow:0 2px 7px rgba(60,50,20,.16); display:grid; grid-template-columns:auto 1fr; gap:6px 12px;
  align-items:start; }}
.ctx .t {{ font-size:.64rem; font-weight:800; letter-spacing:.08em; text-transform:uppercase; color:{INK};
  padding-top:5px; white-space:nowrap; min-width:118px; }}
.ctx .it {{ display:flex; flex-wrap:wrap; gap:6px; align-items:center; }}
.ctx .c {{ background:rgba(4,65,60,.07); border-radius:999px; padding:3px 11px; font-size:.74rem; color:{MUTED}; }}
.ctx .c b {{ color:{TEXT}; font-weight:700; }}
.ctx .tx {{ flex-basis:100%; font-size:.74rem; color:{MUTED}; line-height:1.5; }}
.ctx .tx b {{ color:{TEXT}; font-weight:700; }}
.ctx .alerta {{ flex-basis:100%; background:#FBEFD9; color:#7A4A12; border-radius:6px; padding:5px 10px;
  font-size:.74rem; line-height:1.45; }}
@media (max-width: 760px) {{ .ctx {{ grid-template-columns:1fr; gap:4px; }} }}
.fgroup {{ display:flex; align-items:center; gap:8px; font-weight:800; color:{INK}; font-size:.78rem;
  letter-spacing:.08em; text-transform:uppercase; margin:18px 0 0; padding-top:14px; border-top:1px solid rgba(4,65,60,.18); }}
.fgroup .n {{ flex:0 0 22px; height:22px; border-radius:50%; background:{INK}; color:{BG}; font-size:.72rem;
  display:flex; align-items:center; justify-content:center; letter-spacing:0; }}
.fhint {{ font-size:.73rem; color:{MUTED}; margin:4px 0 10px; line-height:1.4; }}
.tag {{ display:inline-block; padding:1px 8px; border-radius:999px; font-size:.66rem; font-weight:600;
  background:rgba(238,125,34,.12); color:#9A4D0C; margin-left:6px; vertical-align:1px; }}
.footer {{ display:flex; align-items:center; justify-content:space-between; gap:16px; flex-wrap:wrap;
  color:{MUTED}; font-size:.72rem; padding:22px 0 6px; border-top:1px solid {LINE}; margin-top:30px; }}
.footer .logos img {{ height:30px; }} .footer .logos img.pnud {{ height:36px; }} .footer .logos img.publix {{ height:17px; }}
.footer .logos.assinatura img {{ height:40px; }}

/* widgets */
div[data-testid="stMetric"] {{ background:{SURFACE}; border:1px solid {LINE}; border-radius:12px; padding:10px 14px; }}
/* valores como "R$ 972,0 bi" não podem virar "R$ 9…": fonte menor e sem corte */
div[data-testid="stMetricValue"] {{ font-size:1.55rem; }}
div[data-testid="stMetricValue"] > div, div[data-testid="stMetricLabel"] p {{ overflow:visible; text-overflow:clip; white-space:normal; }}
.stDownloadButton button, .stButton button {{ border-radius:999px; border:1px solid {INK}; color:{INK}; background:transparent; font-weight:600; }}
.stDownloadButton button:hover, .stButton button:hover {{ background:{INK}; color:{BG}; border-color:{INK}; }}
div[data-testid="stDataFrame"] {{ border:1px solid {LINE}; border-radius:12px; }}
[data-testid="stExpander"] {{ border:1px solid {LINE}; border-radius:12px; background:{SURFACE}; }}
hr {{ border-color:{LINE} !important; }}
/* Mapa e Ranking: sentido do indicador, resumo em linha e aviso de que a linha do ranking é clicável */
.sentido {{ display:inline-block; padding:1px 8px; border-radius:999px; font-size:.66rem; font-weight:600;
  border:1px solid {LINE}; color:{TEXT}; background:{SURFACE}; margin-left:6px; vertical-align:1px; }}
.stats {{ display:flex; flex-wrap:wrap; gap:6px 18px; font-size:.8rem; color:{MUTED}; padding:8px 12px;
  background:{SURFACE}; border:1px solid {LINE}; border-radius:10px; margin:2px 0 10px; }}
.stats b {{ color:{TEXT}; font-weight:700; }}
.hint {{ display:flex; align-items:center; gap:10px; font-size:.8rem; color:{TEXT}; padding:8px 12px; margin:4px 0 8px;
  background:rgba(238,125,34,.08); border:1px solid rgba(238,125,34,.35); border-radius:10px; }}
.hint .i {{ flex:0 0 26px; height:26px; border-radius:50%; background:{ORANGE}; color:#FFFFFF; font-weight:800;
  display:flex; align-items:center; justify-content:center; font-size:.85rem; }}
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


ASSINATURA_ALT = ("Instituto Publix, PNUD, SUDAM, Ministério da Integração e do Desenvolvimento Regional e Governo do Brasil")


@st.cache_data(show_spinner=False)
def logos_html() -> str:
    """Assinatura institucional enviada pelo design (assets/logos/assinatura.png, recorte de assina_sudam.png), na ordem
    Publix, PNUD, SUDAM, Ministério da Integração e do Desenvolvimento Regional e bandeira. Sem esse arquivo, cai nas logos
    avulsas de assets/logos/{pnud,sudam,publix}.(svg|png|webp|jpg) e, sem elas, no nome em texto."""
    uri_assinatura = _data_uri(LOGOS / "assinatura")
    if uri_assinatura:
        return f'<div class="logos assinatura"><img src="{uri_assinatura}" alt="{ASSINATURA_ALT}"></div>'
    items = []
    for key, name, sub in (("pnud", "PNUD", "BRASIL"), ("sudam", "SUDAM", "AMAZÔNIA"), ("publix", "PUBLIX", "INSTITUTO")):
        uri = _data_uri(LOGOS / key)
        items.append(f'<img class="{key}" src="{uri}" alt="{name}">' if uri else f"<div><span>{name}</span><small>{sub}</small></div>")
    return '<div class="logos">' + '<div class="sep"></div>'.join(items) + "</div>"


@st.cache_data(show_spinner=False)
def _topo_html() -> str:
    """Topo do painel, como na arte da identidade visual: emblema e nome do projeto, título do painel e, à direita,
    o mosaico de ícones (assets/brand/mosaico_topo.webp, gerado por scripts/mosaico_topo.py) com os logos por cima."""
    mosaico = _data_uri(BRAND / "mosaico_topo")
    assinatura = _data_uri(LOGOS / "assinatura")
    logos = (f'<img src="{assinatura}" alt="{ASSINATURA_ALT}">' if assinatura else logos_html())
    arte = f'<img src="{mosaico}" alt="">' if mosaico else ""
    direita = f'<div class="mos">{arte}<div class="assin">{logos}</div></div>'
    return (f'<div class="topo"><div class="marca">{emblem_html()}<div><div class="m1">Apoio à Execução,<br>'
            'Monitoramento e Gestão do<br>Plano Regional de<br>Desenvolvimento da Amazônia</div>'
            '<div class="m2">Superintendência do Desenvolvimento da Amazônia</div></div></div><div class="sv"></div>'
            f'<div class="titulo">Diagnóstico Quantitativo da Amazônia Legal</div>{direita}</div>')


def header():
    st.markdown(_topo_html(), unsafe_allow_html=True)


def pagina(nome: str):
    """Título da aba aberta (ex.: "Visão Geral"), em destaque abaixo dos cartões de contexto."""
    st.markdown(f'<div class="pagina">{html.escape(nome)}</div>', unsafe_allow_html=True)


def footer():
    st.markdown(f'<div class="footer"><div>Projeto BRA/21/005 · SUDAM · PNUD · Instituto Publix · PRDA · Produto 1'
                f'</div>{logos_html()}</div>', unsafe_allow_html=True)


def kpi(label: str, value: str, sub: str = "", icon: str = "●", cls: str = "") -> str:
    value = re.sub("\u00a0([^\\s<]{4,})", "\u00a0<span class=\"un\">\\1</span>", value)  # unidade longa (pontos): menor, cabe ao lado do número
    return (f'<div class="kpi {cls}"><div class="ic">{icon}</div><div><div class="lb">{label}</div>'
            f'<div class="vl">{value}</div><div class="sb">{sub}</div></div></div>')


def mini(label: str, value: str, sub: str = "", delta: str = "", anos=None, valores=None, nota: str = "",
         sel: bool = False, fmt_valor=str, fmt_ano=lambda a: str(int(a))) -> str:
    """Cartão compacto de um indicador com a tendência desenhada em SVG dentro dele (sem gráfico à parte): todos
    têm a mesma altura. Com 2 anos são duas barras; com 1 só a `nota` no mesmo espaço. O primeiro e o último ano
    aparecem com o valor; passando o mouse sobre a linha, cada ano mostra o seu (`fmt_valor` formata)."""
    esc = lambda t: html.escape(str(t))  # noqa: E731
    if anos is not None and len(anos) >= 3:
        vs = [float(v) for v in valores]
        lo, hi = min(vs), max(vs)
        span = max(hi - lo, .02 * max(abs(hi), abs(lo)), 1e-12)  # variação abaixo de 2% não estica na altura toda
        mid = (hi + lo) / 2
        lo = mid - span / 2
        x0, x1 = float(anos[0]), float(anos[-1])
        pts = [((float(a) - x0) / ((x1 - x0) or 1) * 100, 30 - (v - lo) / span * 26 - 2) for a, v in zip(anos, vs)]
        linha = " ".join(f"{x:.2f},{y:.2f}" for x, y in pts)
        area = f"0,32 {linha} 100,32"
        # uma zona invisível por ano: ao passar o mouse, mostra o ponto, a guia e a etiqueta "ano: valor"
        xs = [x for x, _ in pts]
        bordas = [0] + [(a + b) / 2 for a, b in zip(xs, xs[1:])] + [100]
        zonas = []
        for i, ((x, y), a, v) in enumerate(zip(pts, anos, vs)):
            esq, larg = bordas[i], bordas[i + 1] - bordas[i]
            px, py = (x - esq) / larg * 100, y / 32 * 100  # posição do ponto dentro da zona, em %
            # a etiqueta não sai do cartão: alinhada à esquerda no 1º ano e à direita no último
            desloc = "0" if i == 0 else "-100%" if i == len(pts) - 1 else "-50%"
            zonas.append(f'<div class="hz" style="left:{esq:.2f}%;width:{larg:.2f}%">'
                         f'<b style="left:{px:.1f}%"></b><i style="left:{px:.1f}%;top:{py:.1f}%"></i>'
                         f'<span style="left:{px:.1f}%;top:{py:.1f}%;transform:translate({desloc},-160%)">'
                         f'{esc(fmt_ano(a))}: {esc(fmt_valor(v))}</span></div>')
        grafico = (f'<div class="sp"><svg viewBox="0 0 100 32" preserveAspectRatio="none">'
                   f'<polygon points="{area}" fill="rgba(4,65,60,0.08)"/>'
                   f'<polyline points="{linha}" fill="none" stroke="{INK}" stroke-width="2" '
                   f'vector-effect="non-scaling-stroke" stroke-linejoin="round"/></svg>'
                   f'<div class="hz-area">{"".join(zonas)}</div>'
                   f'<div class="yr"><span>{esc(fmt_ano(x0))}: <b>{esc(fmt_valor(vs[0]))}</b></span>'
                   f'<span>{esc(fmt_ano(x1))}: <b>{esc(fmt_valor(vs[-1]))}</b></span></div></div>')
    elif anos is not None and len(anos) == 2 and min(float(v) for v in valores) >= 0 and max(float(v) for v in valores) > 0:
        # só dois anos: duas barras a partir do zero (a altura é proporcional ao valor), uma por ano
        vs = [float(v) for v in valores]
        topo = max(vs)
        barras, rotulos = [], []
        for i, (a, v) in enumerate(zip(anos, vs)):
            h = max(v / topo * 19, 1.2)  # as barras ocupam 19 das 32 unidades; o resto é espaço para o valor em cima
            barras.append(f'<rect x="{10 + 50 * i}" y="{30 - h:.2f}" width="30" height="{h:.2f}" rx="1.5" '
                          f'fill="{INK if i else "rgba(4,65,60,0.38)"}"/>')
            rotulos.append(f'<div class="bv" style="left:{25 + 50 * i}%;top:{(30 - h) / 32 * 100:.1f}%">'
                           f'{esc(fmt_valor(v))}</div>')
        grafico = (f'<div class="sp"><svg viewBox="0 0 100 32" preserveAspectRatio="none">{"".join(barras)}'
                   f'<line x1="0" y1="30.5" x2="100" y2="30.5" stroke="rgba(4,65,60,0.25)" stroke-width="1" '
                   f'vector-effect="non-scaling-stroke"/></svg><div class="hz-area">{"".join(rotulos)}</div>'
                   f'<div class="yr c"><span>{esc(fmt_ano(anos[0]))}</span><span>{esc(fmt_ano(anos[1]))}</span></div></div>')
    else:
        grafico = f'<div class="nota">{esc(nota)}</div>' if nota else '<div class="nota"></div>'
    return (f'<div class="mini{" sel" if sel else ""}"><div class="lb" title="{esc(label)}">{esc(label)}</div>'
            f'<div class="vl">{value}</div><div class="sb" title="{esc(sub)}">{esc(sub)}</div>'
            f'<div class="dl">{delta or "&nbsp;"}</div>{grafico}</div>')


def como_ler(explica: str, leitura: str = ""):
    """Quadro curto abaixo de um gráfico: como ler (texto fixo do tipo de gráfico) e, se houver, o que os dados
    mostram agora (frase montada com os valores da seleção)."""
    extra = f'<span class="dado">👉 {leitura}</span>' if leitura else ""
    st.markdown(f'<div class="ler"><span class="lt">Como ler:</span>{explica}{extra}</div>', unsafe_allow_html=True)


def title(text: str, sub: str = "", fixo: bool = False):
    """Título e subtítulo de um gráfico; fixo=True marca os que não mudam com os filtros de território."""
    tag = '<span class="tag">não muda com os filtros de território</span>' if fixo else ""
    st.markdown(f'<div class="panel-title">{text}{tag}</div><div class="panel-sub">{sub}</div>', unsafe_allow_html=True)
