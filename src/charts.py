"""Gráficos Plotly do painel."""
from __future__ import annotations

import json
import math
from dataclasses import replace

import numpy as np
import pandas as pd
import plotly.graph_objects as go

from . import fmt
from .data import ASSETS, Indicator, band_ranges, bands, n_bands
from .theme import (ACCENT, BG, BLUE, BROWN, COLORWAY, LEVEL_COLOR, MELHOR, MUTED, ORANGE, PIOR, RED, SEQ, SEQ_CONT,
                    SEQ_CONT_PIOR, SEQ_PIOR, SURFACE, TEXT, text_on)


# --------------------------------------------------------------------------- #
# utilidades
# --------------------------------------------------------------------------- #
def _tick_text(ind: Indicator, v: float) -> str:
    """Rótulo de um tick; abaixo de 1 (na unidade exibida) ganha as casas decimais que faltam para não virar '0'."""
    x = abs(v * ind.scale)
    if 0 < x < 1:
        return replace(ind, decimals=max(ind.decimals, math.ceil(-math.log10(x)))).fmt(v)
    return ind.fmt(v)


def _ticks(ind: Indicator, lo: float, hi: float, log: bool = False, n: int = 5):
    if log and lo > 0:
        vals = [10 ** k for k in range(math.floor(math.log10(lo)), math.ceil(math.log10(hi)) + 1)]
    else:
        vals = list(np.linspace(lo, hi, n))
    return vals, [_tick_text(ind, v) for v in vals]


def value_axis(fig: go.Figure, ind: Indicator, lo: float, hi: float, axis: str = "y", log: bool = False, **kw):
    """Eixo de valores com rótulos compactos em pt-BR (ex.: 'R$ 5,9 tri')."""
    vals, txt = _ticks(ind, lo, hi, log)
    upd = fig.update_yaxes if axis == "y" else fig.update_xaxes
    upd(tickvals=vals, ticktext=txt, type="log" if log else "linear", **kw)


def _colors(labels_levels: list[tuple[str, str]]) -> dict[str, str]:
    pool = [c for c in COLORWAY if c not in (ACCENT,)]
    out, i = {}, 0
    for lab, nivel in labels_levels:
        if nivel == "Brasil":
            out[lab] = LEVEL_COLOR["Brasil"]
        elif nivel == "Amazônia Legal":
            out[lab] = ACCENT
        else:
            out[lab] = pool[i % len(pool)]
            i += 1
    return out


def low(text: str) -> str:
    """Primeira letra minúscula para usar no meio da frase, preservando siglas ('PIB municipal')."""
    return text[0].lower() + text[1:] if len(text) > 1 and text[1].islower() else text


def axis_label(ind: Indicator) -> str:
    """Nome do indicador com a unidade, para títulos de eixo e de legenda."""
    return f"{ind.label} · {ind.unit}" if "(" in ind.unit else f"{ind.label} ({ind.unit})"


def seq(ind: Indicator) -> list[str]:
    """Faixas do menor ao maior valor: sempre mais escuro = valor maior. Verde quando maior é melhor (ou sem
    polaridade); tons quentes quando menor é melhor, para o valor alto ser lido como situação ruim."""
    return SEQ_PIOR if ind.polarity < 0 else SEQ


def band_colors(ind: Indicator, m: int) -> list[str]:
    """m cores espaçadas ao longo da paleta de 5 (m < 5 quando valores repetidos reduzem as faixas)."""
    base = seq(ind)
    return [base[int(round(i))] for i in np.linspace(0, len(base) - 1, m)] if m > 1 else [base[2]]


def seq_cont(ind: Indicator) -> list:
    return SEQ_CONT_PIOR if ind.polarity < 0 else SEQ_CONT


def continuous_colors(values: pd.Series, ind: Indicator) -> list[str]:
    """Cor de cada valor na escala contínua do mapa (logarítmica se o indicador pedir), para pintar a tabela
    com as mesmas cores do mapa."""
    v = values.astype(float)
    if ind.log:
        v = np.log10(v.clip(lower=positive_min(v)))
    lo, hi = float(v.min()), float(v.max())
    t = ((v - lo) / (hi - lo)).fillna(0).values if hi > lo else np.zeros(len(v))
    pts = seq_cont(ind)
    ps = [p for p, _ in pts]
    rgb = np.array([[int(c.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4)] for _, c in pts], dtype=float)
    cols = np.column_stack([np.interp(t, ps, rgb[:, k]) for k in range(3)]).round().astype(int)
    return [f"#{r:02X}{g:02X}{b:02X}" for r, g, b in cols]


def positive_min(s: pd.Series, default: float = 1) -> float:
    s = s[s > 0]
    return float(s.min()) if len(s) else default


_GEO: dict[str, dict] = {}


def geojson(level: str) -> dict:
    """Malhas do IBGE (arquivos em assets/geo), com coordenadas arredondadas."""
    key = {"Estado": "uf", "Grande Região": "rg"}.get(level, "mun")
    if key not in _GEO:
        gj = json.loads((ASSETS / "geo" / f"{key}.json").read_text())

        def rnd(c):
            return [round(c[0], 3), round(c[1], 3)] if isinstance(c[0], (int, float)) else [rnd(x) for x in c]

        for f in gj["features"]:
            f["geometry"]["coordinates"] = rnd(f["geometry"]["coordinates"])
            f["id"] = f["properties"]["codarea"]
        _GEO[key] = gj
    return _GEO[key]


# --------------------------------------------------------------------------- #
# mapa
# --------------------------------------------------------------------------- #
_CENTRO: dict[str, tuple[float, float]] = {}


def _centro(feature: dict) -> tuple[float, float]:
    """(lat, lon) do centroide do maior polígono de uma feição (fórmula da área de Gauss)."""
    if feature["id"] not in _CENTRO:
        g = feature["geometry"]
        rings = [p[0] for p in (g["coordinates"] if g["type"] == "MultiPolygon" else [g["coordinates"]])]
        best, area_best = rings[0], -1.0
        for r in rings:
            xs, ys = np.array([c[0] for c in r]), np.array([c[1] for c in r])
            a = abs(np.dot(xs, np.roll(ys, -1)) - np.dot(ys, np.roll(xs, -1))) / 2
            if a > area_best:
                best, area_best = r, a
        xs, ys = np.array([c[0] for c in best]), np.array([c[1] for c in best])
        cross = xs * np.roll(ys, -1) - np.roll(xs, -1) * ys
        a6 = cross.sum() * 3
        cx = ((xs + np.roll(xs, -1)) * cross).sum() / a6 if a6 else xs.mean()
        cy = ((ys + np.roll(ys, -1)) * cross).sum() / a6 if a6 else ys.mean()
        _CENTRO[feature["id"]] = (float(cy), float(cx))
    return _CENTRO[feature["id"]]


def choropleth(df: pd.DataFrame, ind: Indicator, level: str, mode: str = "faixas",
               zoom: float = 3.2, center=(-9.0, -54.0), height: int = 560, rotulos: bool = True,
               destaque_al: bool = False, al_parcial: tuple = ()) -> go.Figure:
    """df: cod, label, valor (e uf, al). mode: 'faixas' (quantis) ou 'continua' (log se o indicador pedir).
    rotulos: siglas das UFs sobre o mapa de estados (quando há poucos estados ou o mapa é grande).
    destaque_al: contorno mais forte nos territórios da Amazônia Legal, quando o mapa traz também os de fora.
    al_parcial: UFs só em parte na Amazônia Legal; ficam sem o contorno forte, pois o estado inteiro não pertence a ela.
    O contorno forte desses estados é desenhado só em volta da parte que fica na região (assets/geo/al_parcial.json)."""
    gj_all = geojson(level)
    larg = {"Estado": 2, "Grande Região": 1}.get(level, 7)  # dígitos do código IBGE em cada nível
    ids = set(df.cod.astype(str).str.zfill(larg))
    sub = {"type": "FeatureCollection", "features": [f for f in gj_all["features"] if f["id"] in ids]}
    fig = go.Figure()

    # contexto: contorno de todas as UFs
    uf = geojson("Estado")
    fig.add_trace(go.Choroplethmap(
        geojson=uf, locations=[f["id"] for f in uf["features"]], z=[0] * len(uf["features"]),
        colorscale=[[0, "rgba(4,65,60,0.03)"], [1, "rgba(4,65,60,0.03)"]], showscale=False,
        marker_line_color="rgba(4,65,60,0.45)", marker_line_width=0.7, hoverinfo="skip"))

    codes = df.cod.astype(str).str.zfill(larg)
    hover = df.label + "<br><b>" + df.valor.map(ind.fmt) + "</b>"
    if mode == "faixas":
        b = bands(df.valor).astype(int)
        m = int(b.max()) + 1
        scale = []
        for i, c in enumerate(band_colors(ind, m)):
            scale += [[i / m, c], [(i + 1) / m, c]]
        fig.add_trace(go.Choroplethmap(
            geojson=sub, locations=codes, z=b + 0.5, zmin=0, zmax=m, colorscale=scale, showscale=False,
            text=hover, hovertemplate="%{text}<extra></extra>",
            marker_line_color="rgba(255,253,247,0.9)", marker_line_width=0.25 if level == "Município" else 0.8))
    else:
        if ind.log:
            lo = positive_min(df.valor)
            z = np.log10(df.valor.clip(lower=lo))
            vals, txt = _ticks(ind, lo, df.valor.max(), log=True)
            tickvals = [math.log10(v) for v in vals]
        else:
            z = df.valor
            tickvals, txt = _ticks(ind, df.valor.min(), df.valor.max())
        fig.add_trace(go.Choroplethmap(
            geojson=sub, locations=codes, z=z, colorscale=seq_cont(ind), text=hover,
            hovertemplate="%{text}<extra></extra>",
            marker_line_color="rgba(255,253,247,0.9)", marker_line_width=0.25 if level == "Município" else 0.8,
            colorbar=dict(tickvals=tickvals, ticktext=txt, len=0.6, thickness=10, title=dict(text=ind.unit, side="right"),
                          tickfont=dict(size=10, color=MUTED), outlinewidth=0)))
    if destaque_al and "al" in df:
        em_al = df.al.fillna(False).astype(bool).values
        if level == "Estado" and al_parcial and "uf" in df:
            em_al = em_al & ~df.uf.isin(al_parcial).values
        if em_al.any() and not em_al.all():
            fig.add_trace(go.Choroplethmap(
                geojson=sub, locations=codes[em_al], z=[0] * int(em_al.sum()), showscale=False, hoverinfo="skip",
                colorscale=[[0, "rgba(0,0,0,0)"], [1, "rgba(0,0,0,0)"]],
                marker_line_color=TEXT, marker_line_width=2.2 if level == "Estado" else 0.9))
    if level == "Estado" and al_parcial and "uf" in df and df.uf.isin(al_parcial).any():
        # contorno só da parte do estado que fica na Amazônia Legal (gerado por scripts/geo_al_parcial.py)
        arq = ASSETS / "geo" / "al_parcial.json"
        if arq.exists():
            gp = json.loads(arq.read_text())
            gp["features"] = [f for f in gp["features"] if f["properties"]["uf"] in set(df.uf)]
            fig.add_trace(go.Choroplethmap(
                geojson=gp, locations=[f["id"] for f in gp["features"]], z=[0] * len(gp["features"]), showscale=False,
                hoverinfo="skip", colorscale=[[0, "rgba(0,0,0,0)"], [1, "rgba(0,0,0,0)"]],
                marker_line_color=TEXT, marker_line_width=2.2))
    if level == "Grande Região" and rotulos:
        feats = {f["id"]: f for f in sub["features"]}
        ok = [i for i, c in enumerate(codes) if c in feats]
        b = bands(df.valor).astype(int).values
        cores_b = band_colors(ind, int(b.max()) + 1)
        for i in ok:
            la, lo = _centro(feats[codes.iloc[i]])
            fig.add_trace(go.Scattermap(
                lat=[la], lon=[lo], mode="text", showlegend=False, hoverinfo="skip", text=[str(df.label.iloc[i])],
                textfont=dict(size=12, color=text_on(cores_b[b[i]]))))
    if level == "Estado" and rotulos and "uf" in df and (len(df) <= 12 or height >= 560):
        feats = {f["id"]: f for f in sub["features"]}
        ok = [i for i, c in enumerate(codes) if c in feats]
        centros = [_centro(feats[codes.iloc[i]]) for i in ok]
        b = bands(df.valor).astype(int).values
        cores_b = band_colors(ind, int(b.max()) + 1)
        tcor = [text_on(cores_b[b[i]]) for i in ok]
        for cor in dict.fromkeys(tcor):  # a cor do texto não aceita lista: um traço por cor (claro ou escuro)
            idx = [j for j, c in enumerate(tcor) if c == cor]
            fig.add_trace(go.Scattermap(
                lat=[centros[j][0] for j in idx], lon=[centros[j][1] for j in idx], mode="text", showlegend=False,
                hoverinfo="skip", text=[str(df.uf.iloc[ok[j]]) for j in idx], textfont=dict(size=11, color=cor)))
    fig.update_layout(map=dict(style="carto-positron", zoom=zoom, center=dict(lat=center[0], lon=center[1])),
                      margin=dict(l=0, r=0, t=0, b=0), height=height)
    return fig


def legend_html(df: pd.DataFrame, ind: Indicator) -> str:
    """Uma entrada por faixa existente: intervalo de valores (um só valor quando a faixa é de valores iguais)
    e quantos territórios ela reúne."""
    rng = band_ranges(df.valor)
    limites = [x for lo, hi, _ in rng for x in (lo, hi)]
    txt = dict(zip(limites, ind.fmt_col(limites)))  # todos os limites na mesma escala
    def faixa(lo, hi):
        return txt[lo] if txt[lo] == txt[hi] else f"{txt[lo]} – {txt[hi]}"
    items = "".join(f'<span><i style="background:{c}"></i>{faixa(lo, hi)} <em>({n})</em></span>'
                    for c, (lo, hi, n) in zip(band_colors(ind, len(rng)), rng))
    nota = ""
    if len(rng) < n_bands(len(df)):
        nota = '<span class="lnote">Valores repetidos agruparam as faixas; por isso há menos de ' \
               f'{n_bands(len(df))}.</span>'
    # título e explicação na primeira linha; todas as faixas juntas na linha de baixo
    return (f'<div class="legend"><div class="ltit"><b>Faixas de {low(axis_label(ind))}</b> '
            f'<span class="lnote">(menor → maior · entre parênteses, nº de territórios)</span></div>'
            f'<div class="litens">{items}</div>{nota}</div>')


# --------------------------------------------------------------------------- #
# distribuição / ranking
# --------------------------------------------------------------------------- #
def histogram(df: pd.DataFrame, ind: Indicator, log: bool = False, ref: tuple[str, float] | None = None,
              height: int = 300) -> go.Figure:
    """Distribuição dos territórios; marca a mediana e, se dado, um valor de referência (ex.: Brasil).
    Em escala logarítmica os intervalos são calculados nos logaritmos e o eixo recebe os rótulos reais.
    Com cauda muito longa (máximo bem acima do percentil 99), o eixo para no percentil 99 e o gráfico
    avisa quantos territórios ficaram além dele."""
    v = df.valor.astype(float)
    log = log and (v > 0).all()
    fora = 0
    if not log:
        p99 = float(v.quantile(.99))
        if p99 > v.min() and v.max() > 1.5 * p99:
            fora = int((v > p99).sum())
            v = v[v <= p99]
    t = np.log10(v) if log else v
    n = int(np.clip(np.sqrt(len(v)), 8, 30))
    cnt, edges = np.histogram(t, bins=n)
    mid, w = (edges[:-1] + edges[1:]) / 2, np.diff(edges)
    f = (lambda x: 10 ** x) if log else (lambda x: x)
    lo_t, hi_t = f(edges[:-1]), f(edges[1:])
    fig = go.Figure(go.Bar(
        x=mid, y=cnt, width=w * .94, marker=dict(color=ACCENT, cornerradius=2),
        customdata=np.column_stack([[ind.fmt(a) for a in lo_t], [ind.fmt(b) for b in hi_t]]),
        hovertemplate="%{customdata[0]} – %{customdata[1]}<br><b>%{y}</b> municípios<extra></extra>"))
    g = (lambda x: float(np.log10(x))) if log else float
    marks = [("Mediana", float(df.valor.median()), ORANGE)] \
        + ([(ref[0], ref[1], RED)] if ref and not fmt.isna(ref[1]) else [])
    for nome, x, cor in marks:
        if (log and x <= 0) or not edges[0] - w[0] <= g(x) <= edges[-1] + w[-1]:
            continue  # fora do trecho desenhado (ex.: Brasil acima do percentil 99)
        fig.add_vline(x=g(x), line=dict(color=cor, width=2, dash="dash"))
    top = float(cnt.max()) * 1.32
    for i, (nome, x, cor) in enumerate(marks):  # rótulos numa faixa acima das barras, um sobre o outro
        if (log and x <= 0) or not edges[0] - w[0] <= g(x) <= edges[-1] + w[-1]:
            continue
        fig.add_annotation(x=g(x), y=top * (1 - .1 * i), yref="y", text=f"{nome}: {ind.fmt(x)}", showarrow=False,
                           xanchor="left", xshift=4, font=dict(color=cor, size=11), bgcolor="rgba(255,255,255,.8)")
    ticks = _ticks(ind, float(v.min()), float(v.max()), log)[0]
    ticks = [x for x in ticks if not log or x > 0]
    fig.update_xaxes(tickvals=[g(x) for x in ticks], ticktext=[ind.fmt(x) for x in ticks], title=axis_label(ind),
                     range=[edges[0] - w[0], edges[-1] + w[-1]])
    fig.update_yaxes(title="Nº de municípios", range=[0, top * 1.05])
    if fora:
        fig.add_annotation(x=1, y=1.0, xref="paper", yref="paper", xanchor="right", yanchor="bottom", showarrow=False,
                           text=f"{fora} municípios acima de {ind.fmt(float(v.max()))} não aparecem",
                           font=dict(size=10, color=MUTED))
    fig.update_layout(height=height, bargap=0, margin=dict(l=0, r=0, t=22, b=6))
    return fig


def hbar(df: pd.DataFrame, ind: Indicator, n: int = 10, highlight: str | None = None,
         ascending: bool = False, height: int | None = None, color: str = ACCENT) -> go.Figure:
    d = df.nsmallest(n, "valor") if ascending else df.nlargest(n, "valor")
    d = d.iloc[::-1]
    cols = [ORANGE if highlight and l == highlight else color for l in d.label]
    if highlight is None:
        cols = [color] * len(d)
    fig = go.Figure(go.Bar(
        x=d.valor, y=d.label, orientation="h", marker=dict(color=cols, cornerradius=4),
        text=ind.fmt_col(d.valor), textposition="outside", cliponaxis=False,
        hovertemplate="%{y}<br><b>%{text}</b><extra></extra>"))
    fig.update_layout(height=height or max(240, 30 * len(d) + 40), margin=dict(l=0, r=70, t=6, b=6),
                      yaxis=dict(automargin=True, tickfont=dict(size=11)), xaxis=dict(visible=False))
    return fig


def benchmark(df: pd.DataFrame, ind: Indicator, log: bool = False, height: int | None = None) -> go.Figure:
    """df: label, nivel, valor — barras horizontais coloridas por granularidade."""
    d = df.sort_values("valor")
    d = d.assign(_t=ind.fmt_col(d.valor))  # rótulos na mesma escala em todas as barras
    fig = go.Figure()
    for nivel, g in d.groupby("nivel", sort=False):
        fig.add_trace(go.Bar(
            x=g.valor, y=g.label, orientation="h", name=nivel, marker=dict(color=LEVEL_COLOR.get(nivel, MUTED),
                                                                          cornerradius=3),
            text=g._t, textposition="outside", cliponaxis=False,
            hovertemplate="%{y} · " + nivel + "<br><b>%{text}</b><extra></extra>"))
    fig.update_layout(height=height or max(360, 22 * len(d) + 80), barmode="overlay",
                      margin=dict(l=0, r=70, t=34, b=6),
                      legend=dict(orientation="h", x=0, y=1, yanchor="bottom", title_text="Nível:", traceorder="reversed"))
    fig.update_xaxes(type="log" if log else "linear", visible=False)
    fig.update_yaxes(categoryorder="array", categoryarray=list(d.label), tickfont=dict(size=11))
    return fig


def tipico_por_uf(df: pd.DataFrame, ind: Indicator | None = None) -> str:
    """Medida que resume os municípios de cada UF: 'media' quando o indicador só tem 0 e 100 (sim/não por município,
    em que a média é o % de municípios); 'soma' (total da UF) nos somáveis em que a maioria dos municípios tem zero
    (ex.: garimpo, açaí), pois aí o município do meio vale zero em quase toda UF; 'mediana' nos demais casos."""
    if set(df.valor.dropna().unique()) <= {0.0, 100.0}:
        return "media"
    if ind is not None and ind.additive and (esparso(df) or binario(df)):
        return "soma"  # 0/1 somável: o total da UF é o nº de municípios com o item
    return "mediana"


def binario(df: pd.DataFrame) -> bool:
    """Indicador sim/não por município: só 0 e 1, ou só 0 e 100 (% já aplicado)."""
    v = set(df.valor.dropna().unique())
    return bool(v) and (v <= {0.0, 1.0} or v <= {0.0, 100.0})


def esparso(df: pd.DataFrame) -> bool:
    """Metade ou mais dos territórios com valor zero (ex.: área de garimpo, produção de açaí)."""
    return len(df) > 0 and float((df.valor == 0).mean()) >= 0.5


def bars_by_uf(df: pd.DataFrame, ind: Indicator, height: int | None = None) -> go.Figure:
    """Barras com o valor do município típico de cada UF (mediana; média nos indicadores sim/não), da maior para a
    menor. Ao passar o mouse: o maior e o menor município da UF e quantos municípios ela tem. df: label, uf, valor."""
    medida = tipico_por_uf(df, ind)
    g = df.groupby("uf").valor
    r = pd.DataFrame({"v": {"mediana": g.median, "media": g.mean, "soma": g.sum}[medida](), "n": g.size(),
                      "min": g.min(), "max": g.max()})
    r["menor"] = df.loc[g.idxmin()].set_index("uf").label
    r["maior"] = df.loc[g.idxmax()].set_index("uf").label
    r = r.sort_values("v", ascending=False).iloc[::-1]
    nome = {"mediana": "Município típico (mediana)", "media": "% dos municípios", "soma": "Total da UF"}[medida]
    fig = go.Figure(go.Bar(
        x=r.v, y=r.index, orientation="h", marker=dict(color=ACCENT, cornerradius=4),
        text=ind.fmt_col(r.v), textposition="outside", cliponaxis=False,
        customdata=np.column_stack([r.n, r["menor"], r["min"].map(ind.fmt), r["maior"], r["max"].map(ind.fmt)]),
        hovertemplate="<b>%{y}</b> · %{customdata[0]} municípios<br>" + nome + ": <b>%{text}</b><br>"
                      "Menor: %{customdata[1]} (%{customdata[2]})<br>Maior: %{customdata[3]} (%{customdata[4]})"
                      "<extra></extra>"))
    fig.update_layout(height=height or int(np.clip(24 * len(r) + 50, 300, 560)), margin=dict(l=0, r=70, t=6, b=6),
                      yaxis=dict(automargin=True, tickfont=dict(size=12)), xaxis=dict(visible=False))
    return fig


def box_by_uf(df: pd.DataFrame, ind: Indicator, log: bool = True) -> go.Figure:
    order = df.groupby("uf").valor.median().sort_values(ascending=False).index
    fig = go.Figure()
    for i, uf in enumerate(order):
        g = df[df.uf == uf]
        fig.add_trace(go.Box(
            y=g.valor, name=uf, boxpoints="outliers", marker=dict(color=COLORWAY[i % len(COLORWAY)], size=3),
            line=dict(width=1.3), text=g.label, hovertemplate="%{text}<br><b>%{customdata}</b><extra></extra>",
            customdata=g.valor.map(ind.fmt), showlegend=False))
    fig.update_layout(height=420, xaxis_title="UF (da maior para a menor mediana)")
    value_axis(fig, ind, positive_min(df.valor) if log else df.valor.min(), df.valor.max(), "y", log,
               title=axis_label(ind))
    return fig


def scatter(df: pd.DataFrame, xi: Indicator, yi: Indicator, log: bool = True, fit: bool = True,
            size_col: str | None = None, height: int = 480) -> go.Figure:
    """df: label, uf, x, y, (size)."""
    fig = go.Figure()
    ufs = sorted(df.uf.dropna().unique()) if df.uf.notna().any() else [None]
    for i, uf in enumerate(ufs):
        g = df if uf is None else df[df.uf == uf]
        sz = 7 if size_col is None else np.clip(np.sqrt(g[size_col]) / 40, 4, 38)
        fig.add_trace(go.Scatter(
            x=g.x, y=g.y, mode="markers", name=str(uf or "Territórios"), text=g.label,
            customdata=np.c_[g.x.map(xi.fmt), g.y.map(yi.fmt)],
            marker=dict(size=sz, color=COLORWAY[i % len(COLORWAY)], opacity=.72,
                        line=dict(width=.5, color=SURFACE)),
            hovertemplate="<b>%{text}</b><br>" + xi.label + ": %{customdata[0]}<br>" + yi.label +
                          ": %{customdata[1]}<extra></extra>"))
    ok = df[(df.x > 0) & (df.y > 0)] if log else df
    if fit and len(ok) > 5:
        fx, fy = (np.log10(ok.x), np.log10(ok.y)) if log else (ok.x, ok.y)
        a, b = np.polyfit(fx, fy, 1)
        xs = np.linspace(fx.min(), fx.max(), 40)
        r = np.corrcoef(fx, fy)[0, 1]
        fig.add_trace(go.Scatter(
            x=10 ** xs if log else xs, y=10 ** (a * xs + b) if log else a * xs + b, mode="lines",
            name="Tendência média (linha tracejada)", line=dict(color=TEXT, dash="dash", width=1.5), hoverinfo="skip"))
    fig.update_layout(height=height, legend=dict(orientation="h", y=-0.2, title_text="UF:"))
    value_axis(fig, xi, positive_min(df.x) if log else df.x.min(), df.x.max(), "x", log, title=axis_label(xi))
    value_axis(fig, yi, positive_min(df.y) if log else df.y.min(), df.y.max(), "y", log, title=axis_label(yi))
    return fig


# --------------------------------------------------------------------------- #
# séries temporais
# --------------------------------------------------------------------------- #
def transform(sr: pd.DataFrame, mode: str, ind: Indicator | None = None) -> pd.DataFrame:
    """mode: 'valor' | 'indice' (base 100 no 1º ano com valor diferente de zero) | 'var' (% a.a. entre pontos
    disponíveis; trechos que partem de zero ficam sem valor)."""
    out = []
    for tid, g in sr.groupby("tid", sort=False):
        g = g.dropna(subset=["valor"]).sort_values("ano").copy()
        if g.empty:
            continue
        if mode == "indice":
            g = g[(g.valor != 0).cummax()]  # índice a partir do 1º valor não nulo
            if g.empty:
                continue
            g["y"] = g.valor / g.valor.iloc[0] * 100
        elif mode == "var":
            dy = g.ano.diff()
            g["dy"] = dy  # anos desde o ponto anterior: > 1 quando há lacuna (o valor é a média por ano do intervalo)
            if ind is not None and ind.delta != "pct":  # proporções e índices: diferença por ano (p.p. ou pontos)
                g["y"] = (g.valor - g.valor.shift()) * ind.scale / dy
            else:
                g["y"] = ((g.valor / g.valor.shift()) ** (1 / dy) - 1) * 100
            g = g[np.isfinite(g.y)]
        else:
            g["y"] = g.valor
        out.append(g)
    return pd.concat(out) if out else pd.DataFrame(columns=list(sr.columns) + ["y"])


def _ralear(rot: list[str], n_series: int) -> list[str]:
    """Escolhe quais rótulos de uma série ficam visíveis: todos; só o primeiro e o último com 3 séries ou mais; de dois
    em dois (terminando no último) com mais de 14 pontos."""
    n_pt = len(rot)
    if n_series > 2:
        return [r if i in (0, n_pt - 1) else "" for i, r in enumerate(rot)]
    if n_pt > 14:
        manter = set(range(0, n_pt, 2)) | {n_pt - 1}
        if (n_pt - 1) % 2:
            manter.discard(n_pt - 2)
        return [r if i in manter else "" for i, r in enumerate(rot)]
    return rot


def lines(sr: pd.DataFrame, ind: Indicator, mode: str = "valor", log: bool = False, height: int = 430,
          cores: dict[str, str] | None = None, tracejado: tuple = (), grossas: tuple = (),
          rotulos: bool = False) -> go.Figure:
    """Séries por território. cores: cor por nome de série (substitui a automática); tracejado e grossas: nomes de
    séries desenhadas com linha tracejada ou mais grossa (para diferenciar séries de cores parecidas).
    rotulos: escreve o valor em todos os pontos; com 3 séries ou mais, só no primeiro e no último de cada uma; com mais
    de 14 anos, de dois em dois. Os rótulos de séries vizinhas ficam um acima e outro abaixo da linha."""
    t = transform(sr, mode, ind)
    fig = go.Figure()
    if t.empty:
        return fig
    un = "% a.a." if ind.delta == "pct" else f"{ind.delta_unit} ao ano"
    cmap = _colors(list(t.drop_duplicates("label")[["label", "nivel"]].itertuples(index=False, name=None)))
    cmap.update({k: v for k, v in (cores or {}).items() if k in cmap})
    for lab, g in t.groupby("label", sort=False):
        if mode == "var":
            extra_b = {}
            if rotulos:
                # "*": depois de anos sem dado, a variação é a média por ano desde o último ano com dado
                rot_b = _ralear([ind.fmt_diff(v) + ("*" if d > 1 else "") for v, d in zip(g.y, g.dy)],
                                len(t.label.unique()))
                extra_b = dict(text=rot_b, textposition="outside", cliponaxis=False,
                               textfont=dict(size=10, color=cmap[lab]))
            fig.add_trace(go.Bar(x=g.ano, y=g.y, name=lab, marker_color=cmap[lab], opacity=.9,
                                 hovertemplate=f"{lab}<br>%{{x}}: <b>%{{y:.{ind.diff_decimals}f}} {un}</b>"
                                               "<extra></extra>", **extra_b))
            continue
        hv = g.valor.map(ind.fmt) if mode == "valor" else g.y.map(lambda v: fmt.num(v, 1)) + " (base 100)"
        extra = {}
        if rotulos:
            rot = (g.valor.map(ind.fmt) if mode == "valor" else g.y.map(lambda v: fmt.num(v, 1))).tolist()
            n_pt = len(rot)
            rot = _ralear(rot, len(t.label.unique()))
            i_serie = list(dict.fromkeys(t.label)).index(lab)
            extra = dict(text=rot, textposition="top center" if i_serie % 2 == 0 else "bottom center",
                         textfont=dict(size=10 if n_pt > 8 else 11, color=cmap[lab]), cliponaxis=False)
        # anos sem dado no meio da série: a linha principal é cortada ali e o trecho é refeito pontilhado e mais
        # claro, para ninguém achar que há um ponto faltando por erro
        xs, ys, cds, lacunas = [], [], [], []
        ts = extra.get("text")
        tx = []
        anos_g, y_g, hv_g = g.ano.tolist(), g.y.tolist(), list(hv)
        for i, (a, yv) in enumerate(zip(anos_g, y_g)):
            if i and a - anos_g[i - 1] > 1:
                lacunas.append((anos_g[i - 1], y_g[i - 1], a, yv))
                xs.append(anos_g[i - 1] + 1), ys.append(None), cds.append(""), tx.append("")
            xs.append(a), ys.append(yv), cds.append(hv_g[i]), tx.append(ts[i] if ts is not None else "")
        if ts is not None:
            extra["text"] = tx
        largura = 3.6 if lab in grossas else 2.6
        fig.add_trace(go.Scatter(
            x=xs, y=ys, name=lab, mode="lines+markers+text" if rotulos else "lines+markers", connectgaps=False,
            line=dict(color=cmap[lab], width=largura, dash="dash" if lab in tracejado else "solid"),
            marker=dict(size=7, line=dict(width=1, color=SURFACE)), legendgroup=lab,
            customdata=cds, hovertemplate=f"{lab}<br>%{{x}}: <b>%{{customdata}}</b><extra></extra>", **extra))
        for a0, y0, a1, y1 in lacunas:
            fig.add_trace(go.Scatter(
                x=[a0, a1], y=[y0, y1], mode="lines", showlegend=False, legendgroup=lab, hoverinfo="skip",
                line=dict(color=cmap[lab], width=max(largura - 1, 1.6), dash="dot"), opacity=.55))
    fig.update_layout(height=height, hovermode="x unified" if mode != "var" else "closest",
                      barmode="group", legend=dict(orientation="h", y=-0.15, title_text="Território:"),
                      yaxis_title={"valor": ind.unit, "indice": "Índice (base 100)",
                                   "var": f"Variação ({un})"}[mode])
    fig.update_xaxes(dtick=1, tickformat="d")
    if mode == "valor":
        value_axis(fig, ind, t.y.min(), t.y.max(), "y", log and t.y.min() > 0)
    elif mode == "indice":
        fig.add_hline(y=100, line=dict(color="rgba(31,46,40,.35)", dash="dot"))
        fig.update_yaxes(ticksuffix="")
    else:
        fig.update_yaxes(ticksuffix="%" if ind.delta == "pct" else "")
        fig.add_hline(y=0, line=dict(color="rgba(31,46,40,.35)"))
    return fig


def growth_heatmap(sr: pd.DataFrame, ind: Indicator, height: int | None = None) -> go.Figure:
    """Variação a cada ano por território, na medida do indicador (% ou p.p./pontos por ano). Com polaridade, a cor
    indica a situação (verde = melhora, vermelho = piora); sem polaridade, só a direção (azul = cresceu, marrom = caiu)."""
    t = transform(sr, "var", ind)
    if t.empty:
        return go.Figure()
    p = t.pivot_table(index="label", columns="ano", values="y", sort=False)
    gap = t.pivot_table(index="label", columns="ano", values="dy", sort=False).reindex_like(p)
    lim = float(np.nanpercentile(np.abs(p.values), 95)) or 1
    if ind.polarity:
        lo, hi = (MELHOR, PIOR) if ind.polarity < 0 else (PIOR, MELHOR)
    else:
        lo, hi = BROWN, BLUE
    un = "% a.a." if ind.delta == "pct" else f"{ind.delta_unit} a.a."
    casas = ind.diff_decimals
    # "*": depois de anos sem dado, o valor é a média por ano desde o último ano com dado
    texto = [[("" if np.isnan(v) else fmt.num(v, casas) + ("*" if d > 1 else "")) for v, d in zip(lv, ld)]
             for lv, ld in zip(p.values, gap.values)]
    nota = [[(f"média por ano desde {int(a - d)}" if d > 1 else "") for a, d in zip(p.columns, ld)] for ld in gap.values]
    fig = go.Figure(go.Heatmap(
        # anos como categorias: cada ano com dado é uma coluna da mesma largura, sem esticar sobre as lacunas
        z=p.values, x=[str(int(a)) for a in p.columns], y=p.index, zmin=-lim, zmax=lim,
        colorscale=[[0, lo], [.5, "#FBF8EE"], [1, hi]],
        text=texto, texttemplate="%{text}", customdata=nota,
        textfont=dict(size=10), hovertemplate="%{y}<br>%{x}: <b>%{z:." + str(casas) + "f} " + un + "</b> %{customdata}"
                                              "<extra></extra>",
        colorbar=dict(ticksuffix="%" if ind.delta == "pct" else "", thickness=10, len=0.8, outlinewidth=0,
                      title=dict(text=un, side="right"))))
    fig.update_layout(height=height or max(220, 38 * len(p) + 70), margin=dict(l=0, r=0, t=6, b=6))
    fig.update_xaxes(type="category", side="top")
    fig.update_yaxes(autorange="reversed")
    return fig


def sparkline(years, values, ind: Indicator, color: str = ACCENT) -> go.Figure:
    """Tendência de uma série; o eixo acompanha o intervalo dos valores (não parte do zero), para a
    variação aparecer mesmo em séries que mudam pouco em relação ao nível."""
    lo, hi = float(np.nanmin(values)), float(np.nanmax(values))
    span = max(hi - lo, .02 * max(abs(hi), abs(lo)))  # variação abaixo de 2% do valor não é esticada na altura toda
    mid = (hi + lo) / 2
    lo, hi = mid - span / 2, mid + span / 2
    pad = span * .15 or 1
    fig = go.Figure(go.Scatter(
        x=years, y=values, mode="lines+markers", connectgaps=True, line=dict(color=color, width=2.2),
        marker=dict(size=4), fill="tozeroy", fillcolor="rgba(4,65,60,0.08)",
        text=[ind.fmt(v) for v in values], hovertemplate="%{x}: <b>%{text}</b><extra></extra>"))
    yrs = [int(y) for y in years]
    fig.update_layout(height=104, margin=dict(l=0, r=0, t=2, b=16), showlegend=False)
    for x, anchor, y in ((0, "left", yrs[0]), (1, "right", yrs[-1])):
        fig.add_annotation(x=x, y=0, xref="paper", yref="paper", yshift=-9, text=str(y), showarrow=False,
                           xanchor=anchor, font=dict(size=10, color=MUTED))
    fig.update_xaxes(visible=False)
    fig.update_yaxes(visible=False, rangemode="normal", range=[lo - pad, hi + pad])
    return fig


def percentile_bar(pct: float, label: str = "") -> go.Figure:
    fig = go.Figure(go.Bar(x=[pct], y=[label], orientation="h", marker=dict(color=ACCENT, cornerradius=6),
                           text=[f"{fmt.num(pct, 0)}º percentil"], textposition="inside", insidetextanchor="start",
                           hoverinfo="skip"))
    fig.add_vline(x=50, line=dict(color="rgba(31,46,40,.4)", dash="dot"))
    fig.update_layout(height=60, margin=dict(l=0, r=0, t=0, b=0), showlegend=False)
    fig.update_xaxes(range=[0, 100], visible=False)
    fig.update_yaxes(visible=False)
    return fig
