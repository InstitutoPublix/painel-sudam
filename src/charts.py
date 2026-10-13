"""Gráficos Plotly do painel."""
from __future__ import annotations

import json
import math

import numpy as np
import pandas as pd
import plotly.graph_objects as go

from . import fmt
from .data import ASSETS, Indicator, band_ranges, bands
from .theme import COLORWAY, LEVEL_COLOR, LIME, MUTED, SEQ, SEQ_CONT


# --------------------------------------------------------------------------- #
# utilidades
# --------------------------------------------------------------------------- #
def _ticks(ind: Indicator, lo: float, hi: float, log: bool = False, n: int = 5):
    if log and lo > 0:
        vals = [10 ** k for k in range(math.floor(math.log10(lo)), math.ceil(math.log10(hi)) + 1)]
    else:
        vals = list(np.linspace(lo, hi, n))
    return vals, [ind.fmt(v) for v in vals]


def value_axis(fig: go.Figure, ind: Indicator, lo: float, hi: float, axis: str = "y", log: bool = False, **kw):
    """Eixo de valores com rótulos compactos em pt-BR (ex.: 'R$ 5,9 tri')."""
    vals, txt = _ticks(ind, lo, hi, log)
    upd = fig.update_yaxes if axis == "y" else fig.update_xaxes
    upd(tickvals=vals, ticktext=txt, type="log" if log else "linear", **kw)


def _colors(labels_levels: list[tuple[str, str]]) -> dict[str, str]:
    pool = [c for c in COLORWAY if c not in (LIME,)]
    out, i = {}, 0
    for lab, nivel in labels_levels:
        if nivel == "Brasil":
            out[lab] = "#FFFFFF"
        elif nivel == "Amazônia Legal":
            out[lab] = LIME
        else:
            out[lab] = pool[i % len(pool)]
            i += 1
    return out


_GEO: dict[str, dict] = {}


def geojson(level: str) -> dict:
    """Malhas do IBGE (arquivos em assets/geo), com coordenadas arredondadas."""
    key = "uf" if level == "Estado" else "mun"
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
def choropleth(df: pd.DataFrame, ind: Indicator, level: str, mode: str = "faixas",
               zoom: float = 3.2, center=(-9.0, -54.0), height: int = 560) -> go.Figure:
    """df: cod, label, valor. mode: 'faixas' (quantis) ou 'continua' (log)."""
    gj_all = geojson(level)
    ids = set(df.cod.astype(str).str.zfill(2 if level == "Estado" else 7))
    sub = {"type": "FeatureCollection", "features": [f for f in gj_all["features"] if f["id"] in ids]}
    fig = go.Figure()

    # contexto: contorno de todas as UFs
    uf = geojson("Estado")
    fig.add_trace(go.Choroplethmap(
        geojson=uf, locations=[f["id"] for f in uf["features"]], z=[0] * len(uf["features"]),
        colorscale=[[0, "rgba(255,255,255,0.035)"], [1, "rgba(255,255,255,0.035)"]], showscale=False,
        marker_line_color="rgba(198,244,50,0.45)", marker_line_width=0.7, hoverinfo="skip"))

    codes = df.cod.astype(str).str.zfill(2 if level == "Estado" else 7)
    hover = df.label + "<br><b>" + df.valor.map(ind.fmt) + "</b>"
    if mode == "faixas":
        b = bands(df.valor).astype(int)
        scale = []
        for i, c in enumerate(SEQ):
            scale += [[i / 5, c], [(i + 1) / 5, c]]
        fig.add_trace(go.Choroplethmap(
            geojson=sub, locations=codes, z=b + 0.5, zmin=0, zmax=5, colorscale=scale, showscale=False,
            text=hover, hovertemplate="%{text}<extra></extra>",
            marker_line_color="rgba(4,20,11,0.9)", marker_line_width=0.25 if level == "Município" else 0.8))
    else:
        z = np.log10(df.valor.clip(lower=1))
        vals, txt = _ticks(ind, df.valor.min(), df.valor.max(), log=True)
        fig.add_trace(go.Choroplethmap(
            geojson=sub, locations=codes, z=z, colorscale=SEQ_CONT, text=hover,
            hovertemplate="%{text}<extra></extra>",
            marker_line_color="rgba(4,20,11,0.9)", marker_line_width=0.25 if level == "Município" else 0.8,
            colorbar=dict(tickvals=[math.log10(v) for v in vals], ticktext=txt, len=0.6, thickness=10,
                          tickfont=dict(size=10, color="#cfe3d4"), outlinewidth=0)))
    fig.update_layout(map=dict(style="carto-darkmatter", zoom=zoom, center=dict(lat=center[0], lon=center[1])),
                      margin=dict(l=0, r=0, t=0, b=0), height=height)
    return fig


def legend_html(df: pd.DataFrame, ind: Indicator) -> str:
    rng = band_ranges(df.valor)
    items = "".join(f'<span><i style="background:{c}"></i>{ind.fmt(lo)} – {ind.fmt(hi)}</span>'
                    for c, (lo, hi) in zip(SEQ, rng))
    return f'<div class="legend">{items}</div>'


# --------------------------------------------------------------------------- #
# distribuição / ranking
# --------------------------------------------------------------------------- #
def donut(df: pd.DataFrame, ind: Indicator, unit_label: str = "municípios") -> go.Figure:
    b = bands(df.valor).astype(int)
    rng = band_ranges(df.valor)
    counts = b.value_counts().reindex(range(5), fill_value=0)
    names = ["Faixa 1 (menores)", "Faixa 2", "Faixa 3", "Faixa 4", "Faixa 5 (maiores)"]
    fig = go.Figure(go.Pie(
        labels=names, values=counts.values, hole=0.62, sort=False, direction="clockwise",
        marker=dict(colors=SEQ, line=dict(color="#04140B", width=2)),
        customdata=[f"{ind.fmt(lo)} – {ind.fmt(hi)}" for lo, hi in rng],
        hovertemplate="%{label}<br>%{value} " + unit_label + " (%{percent})<br>%{customdata}<extra></extra>",
        textinfo="value", textfont=dict(color="#ffffff", size=12)))
    fig.add_annotation(text=f"<b>{len(df):,}</b><br><span style='font-size:11px;color:{MUTED}'>{unit_label}</span>"
                       .replace(",", "."), showarrow=False, font=dict(size=24))
    fig.update_layout(height=300, showlegend=True, legend=dict(orientation="v", x=1.02, y=0.5, font=dict(size=10)),
                      margin=dict(l=0, r=0, t=6, b=6))
    return fig


def hbar(df: pd.DataFrame, ind: Indicator, n: int = 10, highlight: str | None = None,
         ascending: bool = False, height: int | None = None, color: str = LIME) -> go.Figure:
    d = df.nsmallest(n, "valor") if ascending else df.nlargest(n, "valor")
    d = d.iloc[::-1]
    cols = [LIME if highlight and l == highlight else color for l in d.label]
    if highlight is None:
        cols = [color] * len(d)
    fig = go.Figure(go.Bar(
        x=d.valor, y=d.label, orientation="h", marker=dict(color=cols, cornerradius=4),
        text=d.valor.map(ind.fmt), textposition="outside", cliponaxis=False,
        hovertemplate="%{y}<br><b>%{text}</b><extra></extra>"))
    fig.update_layout(height=height or max(240, 30 * len(d) + 40), margin=dict(l=0, r=70, t=6, b=6),
                      yaxis=dict(automargin=True, tickfont=dict(size=11)), xaxis=dict(visible=False))
    return fig


def benchmark(df: pd.DataFrame, ind: Indicator, log: bool = False, height: int | None = None) -> go.Figure:
    """df: label, nivel, valor — barras horizontais coloridas por granularidade."""
    d = df.sort_values("valor")
    fig = go.Figure()
    for nivel, g in d.groupby("nivel", sort=False):
        fig.add_trace(go.Bar(
            x=g.valor, y=g.label, orientation="h", name=nivel, marker=dict(color=LEVEL_COLOR.get(nivel, MUTED),
                                                                          cornerradius=3),
            text=g.valor.map(ind.fmt), textposition="outside", cliponaxis=False,
            hovertemplate="%{y} · " + nivel + "<br><b>%{text}</b><extra></extra>"))
    fig.update_layout(height=height or max(360, 22 * len(d) + 80), barmode="overlay",
                      margin=dict(l=0, r=70, t=6, b=6), legend=dict(orientation="h", y=1.04))
    fig.update_xaxes(type="log" if log else "linear", visible=False)
    fig.update_yaxes(categoryorder="array", categoryarray=list(d.label), tickfont=dict(size=11))
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
    fig.update_layout(height=420)
    value_axis(fig, ind, max(df.valor.min(), 1), df.valor.max(), "y", log)
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
                        line=dict(width=.5, color="#04140B")),
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
            name=f"Tendência (r = {fmt.num(r, 2)})", line=dict(color="#fff", dash="dash", width=1.5), hoverinfo="skip"))
    fig.update_layout(height=height, legend=dict(orientation="h", y=-0.2))
    value_axis(fig, xi, max(df.x.min(), 1), df.x.max(), "x", log, title=xi.label)
    value_axis(fig, yi, max(df.y.min(), 1), df.y.max(), "y", log, title=yi.label)
    return fig


# --------------------------------------------------------------------------- #
# séries temporais
# --------------------------------------------------------------------------- #
def transform(sr: pd.DataFrame, mode: str) -> pd.DataFrame:
    """mode: 'valor' | 'indice' (base 100 no 1º ano disponível) | 'var' (% a.a. entre pontos disponíveis)."""
    out = []
    for tid, g in sr.groupby("tid", sort=False):
        g = g.dropna(subset=["valor"]).sort_values("ano").copy()
        if g.empty:
            continue
        if mode == "indice":
            g["y"] = g.valor / g.valor.iloc[0] * 100
        elif mode == "var":
            dy = g.ano.diff()
            g["y"] = ((g.valor / g.valor.shift()) ** (1 / dy) - 1) * 100
            g = g.dropna(subset=["y"])
        else:
            g["y"] = g.valor
        out.append(g)
    return pd.concat(out) if out else pd.DataFrame(columns=list(sr.columns) + ["y"])


def lines(sr: pd.DataFrame, ind: Indicator, mode: str = "valor", log: bool = False, height: int = 430) -> go.Figure:
    t = transform(sr, mode)
    fig = go.Figure()
    if t.empty:
        return fig
    cmap = _colors(list(t.drop_duplicates("label")[["label", "nivel"]].itertuples(index=False, name=None)))
    for lab, g in t.groupby("label", sort=False):
        if mode == "var":
            fig.add_trace(go.Bar(x=g.ano, y=g.y, name=lab, marker_color=cmap[lab], opacity=.9,
                                 hovertemplate=f"{lab}<br>%{{x}}: <b>%{{y:.1f}}% a.a.</b><extra></extra>"))
            continue
        hv = g.valor.map(ind.fmt) if mode == "valor" else g.y.map(lambda v: fmt.num(v, 1)) + " (base 100)"
        fig.add_trace(go.Scatter(
            x=g.ano, y=g.y, name=lab, mode="lines+markers", connectgaps=True,
            line=dict(color=cmap[lab], width=2.6), marker=dict(size=7, line=dict(width=1, color="#04140B")),
            text=hv, hovertemplate=f"{lab}<br>%{{x}}: <b>%{{text}}</b><extra></extra>"))
    fig.update_layout(height=height, hovermode="x unified" if mode != "var" else "closest",
                      barmode="group", legend=dict(orientation="h", y=-0.15))
    fig.update_xaxes(dtick=1, tickformat="d")
    if mode == "valor":
        value_axis(fig, ind, t.y.min(), t.y.max(), "y", log and t.y.min() > 0)
    elif mode == "indice":
        fig.add_hline(y=100, line=dict(color="rgba(255,255,255,.3)", dash="dot"))
        fig.update_yaxes(ticksuffix="")
    else:
        fig.update_yaxes(ticksuffix="%")
        fig.add_hline(y=0, line=dict(color="rgba(255,255,255,.3)"))
    return fig


def growth_heatmap(sr: pd.DataFrame, height: int | None = None) -> go.Figure:
    t = transform(sr, "var")
    if t.empty:
        return go.Figure()
    p = t.pivot_table(index="label", columns="ano", values="y", sort=False)
    lim = float(np.nanpercentile(np.abs(p.values), 95)) or 1
    fig = go.Figure(go.Heatmap(
        z=p.values, x=p.columns, y=p.index, zmin=-lim, zmax=lim,
        colorscale=[[0, "#D9482B"], [.5, "#0B2A17"], [1, LIME]],
        text=np.vectorize(lambda v: "" if np.isnan(v) else fmt.num(v, 1))(p.values), texttemplate="%{text}",
        textfont=dict(size=10), hovertemplate="%{y}<br>%{x}: <b>%{z:.1f}% a.a.</b><extra></extra>",
        colorbar=dict(ticksuffix="%", thickness=10, len=0.8, outlinewidth=0)))
    fig.update_layout(height=height or max(220, 38 * len(p) + 70), margin=dict(l=0, r=0, t=6, b=6))
    fig.update_xaxes(dtick=1, tickformat="d", side="top")
    fig.update_yaxes(autorange="reversed")
    return fig


def sparkline(years, values, ind: Indicator, color: str = LIME) -> go.Figure:
    fig = go.Figure(go.Scatter(
        x=years, y=values, mode="lines+markers", connectgaps=True, line=dict(color=color, width=2.2),
        marker=dict(size=4), fill="tozeroy", fillcolor="rgba(198,244,50,0.08)",
        text=[ind.fmt(v) for v in values], hovertemplate="%{x}: <b>%{text}</b><extra></extra>"))
    fig.update_layout(height=90, margin=dict(l=0, r=0, t=2, b=0), showlegend=False)
    fig.update_xaxes(visible=False)
    fig.update_yaxes(visible=False, rangemode="normal")
    return fig


def percentile_bar(pct: float, label: str = "") -> go.Figure:
    fig = go.Figure(go.Bar(x=[pct], y=[label], orientation="h", marker=dict(color=LIME, cornerradius=6),
                           text=[f"{fmt.num(pct, 0)}º percentil"], textposition="inside", insidetextanchor="start",
                           hoverinfo="skip"))
    fig.add_vline(x=50, line=dict(color="rgba(255,255,255,.4)", dash="dot"))
    fig.update_layout(height=60, margin=dict(l=0, r=0, t=0, b=0), showlegend=False)
    fig.update_xaxes(range=[0, 100], visible=False)
    fig.update_yaxes(visible=False)
    return fig
