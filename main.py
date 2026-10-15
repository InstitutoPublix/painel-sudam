"""PRDA · Diagnóstico Quantitativo da Amazônia Legal — painel Streamlit.

Executar:  streamlit run main.py
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from src import charts, data, fmt, theme
from src.data import LEVELS, PORTES

ICON = data.ASSETS / "logos" / "emblema.png"
st.set_page_config(page_title="PRDA · Diagnóstico da Amazônia Legal",
                   page_icon=str(ICON) if ICON.exists() else "🌿", layout="wide",
                   initial_sidebar_state="expanded")
theme.inject()
D = data.load()
L, REG = D["long"], D["registry"]
BRASIL, AMZ = "Brasil:1", "Amazônia Legal:0"
CFG = {"displayModeBar": False}


def plot(fig: go.Figure, key: str | None = None):
    st.plotly_chart(fig, width="stretch", config=CFG, key=key)


# Widgets com chave "w_*" guardam o valor no session_state: só a aba aberta é desenhada, e sem isso
# o Streamlit descartaria a escolha de um filtro ou controle que ficou oculto ao trocar de aba.
for _k in [k for k in st.session_state if str(k).startswith("w_")]:
    st.session_state[_k] = st.session_state[_k]


def state(key: str, default, options=None) -> str:
    """Prepara o valor inicial do widget `key`, descartando escolhas que não existem mais nas opções."""
    v = st.session_state.get(key, default)
    if options is not None:
        v = [x for x in v if x in options] if isinstance(v, list) else (v if v in options else default)
    st.session_state[key] = v
    return key


# --------------------------------------------------------------------------- #
# Abas e filtros da barra lateral (só os que a aba aberta usa)
# --------------------------------------------------------------------------- #
ABAS = ["Visão Geral", "Mapa Territorial", "Perfil do Território", "Séries Temporais",
        "Ranking", "Comparações", "Sobre o Painel"]
TERRIT = {"recorte", "uf", "porte"}
FILTROS = {"Visão Geral": {"ind", "ano"} | TERRIT, "Mapa Territorial": {"ind", "ano"} | TERRIT,
           "Perfil do Território": {"ind", "ano"}, "Séries Temporais": {"ind"},
           "Ranking": {"ind", "ano"} | TERRIT, "Comparações": {"ind", "ano"} | TERRIT, "Sobre o Painel": set()}
NOTAS = {"Perfil do Território": "O território (e a UF, para municípios) é escolhido na própria página.",
         "Séries Temporais": "Os territórios são escolhidos na própria página; as séries mostram todos os anos.",
         "Sobre o Painel": "Esta página não usa filtros."}

theme.header()
tabs = st.tabs(ABAS, key="aba", on_change="rerun")
ABA = next((a for a, t in zip(ABAS, tabs) if t.open), ABAS[0])
show = set(FILTROS[ABA])
# a escala escolhida dentro da aba define quais filtros territoriais fazem efeito
escala = {"Mapa Territorial": st.session_state.get("w_map_lvl", "Estado"),
          "Ranking": st.session_state.get("w_rk_lvl", "Município")}.get(ABA)
if escala == "Estado":
    show -= {"porte"}
elif escala == "Grande Região":
    show -= TERRIT

with st.sidebar:
    st.markdown("### Filtros")
    eixos = sorted({REG[k].axis for k in D["indicators"]})
    k = state("w_eixo", "Todos os eixos", ["Todos os eixos", *eixos])
    eixo = st.selectbox("Eixo temático", ["Todos os eixos", *eixos], key=k) if "ind" in show else st.session_state[k]
    pool = [k for k in D["indicators"] if eixo == "Todos os eixos" or REG[k].axis == eixo]
    k = state("w_ind", pool[0], pool)
    IND = (st.selectbox("Indicador", pool, format_func=lambda k: REG[k].label, key=k,
                        help="Indicadores ativos em config/indicadores.toml.") if "ind" in show else st.session_state[k])
    I = REG[IND]
    years = data.years_with_data(D, IND)
    k = state("w_ano", years[-1], years)
    if "ano" in show and len(years) > 1:
        YEAR = st.select_slider("Ano de referência", years, key=k)
    else:
        YEAR = st.session_state[k]
        if "ano" in show:
            st.caption(f"Ano de referência: **{YEAR}** (único ano com dado)")
    k = state("w_recorte", "Amazônia Legal", ["Amazônia Legal", "Brasil"])
    recorte = (st.radio("Recorte territorial", ["Amazônia Legal", "Brasil"], horizontal=True, key=k)
               if "recorte" in show else st.session_state[k])
    AL_ONLY = recorte == "Amazônia Legal"
    ufs_pool = D["al_ufs"] if AL_ONLY else D["ufs"]
    k = state("w_ufs", [], ufs_pool)
    UFS = st.multiselect("Estados (UF)", ufs_pool, placeholder="Todos", key=k) if "uf" in show else []
    portes = [p[0] for p in PORTES]
    k = state("w_porte", [], portes)
    PORTE = (st.multiselect("Porte populacional (municípios)", portes, placeholder="Todos", key=k)
             if "porte" in show else [])
    if ABA in NOTAS:
        st.caption(NOTAS[ABA])
    elif escala == "Grande Região":
        st.caption("Grandes Regiões não têm recorte por UF ou porte.")
    if "ind" in show:
        st.caption(f"**{I.label}** · {I.unit}" + (f" · {I.polarity_text}" if I.polarity_text else ""))
        st.caption(f"Amazônia Legal: {I.agg_note.lower()}.")
    st.markdown("---")
    st.caption("SUDAM · PNUD · Instituto Publix\n\nProjeto BRA/21/005")


def snap(level: str, ind: str = IND, year: int = YEAR, filt: bool = True) -> pd.DataFrame:
    if not filt:
        return data.snapshot(D, level, ind, year)
    return data.snapshot(D, level, ind, year, al_only=AL_ONLY, ufs=UFS or None, portes=PORTE or None)


def value_of(tid: str, ind: str = IND, year: int = YEAR) -> float:
    s = data.series(D, [tid], ind)
    v = s.loc[s.ano == year, "valor"]
    return float(v.iloc[0]) if len(v) and pd.notna(v.iloc[0]) else float("nan")


def first_valid(tid: str, ind: str = IND, upto: int = YEAR):
    s = data.series(D, [tid], ind).dropna(subset=["valor"])
    s = s[s.ano <= upto]
    return (int(s.ano.iloc[0]), float(s.valor.iloc[0])) if len(s) else (None, float("nan"))


def change_since_start(level: str, ind: str = IND, year: int = YEAR) -> pd.Series:
    d = L[(L.nivel == level) & (L.ind == ind) & L.valor.notna() & (L.ano <= year)].sort_values("ano")
    g = d.groupby("cod", observed=True).valor.agg(["first", "last"])
    return ((g["last"] / g["first"].replace(0, np.nan) - 1) * 100).rename("var")  # base zero: sem variação


def change(v: float, v0: float) -> float:
    """Variação % de v0 até v; indefinida (NaN) quando falta dado ou o valor inicial é zero."""
    return float("nan") if fmt.isna(v) or fmt.isna(v0) or v0 == 0 else (v / v0 - 1) * 100


def arrow(v: float) -> str:
    if fmt.isna(v):
        return "—"
    return f'<span class="{"up" if v >= 0 else "down"}">{"▲" if v >= 0 else "▼"} {fmt.pct(abs(v))}</span>'


def grid(keys: list[str], n: int = 4):
    """Distribui itens em linhas de n colunas."""
    for i in range(0, len(keys), n):
        yield from zip(st.columns(n), keys[i:i + n])


def map_view(level: str):
    if AL_ONLY:
        return dict(zoom=3.0 if level == "Estado" else 3.2, center=(-6.5, -55.0))
    return dict(zoom=2.7, center=(-14.5, -52.0))


# =========================================================================== #
# 1. VISÃO GERAL
# =========================================================================== #
with tabs[0]:
    if tabs[0].open:
        theme.hero(tuple(sorted({str(c) for c in L[(L.nivel == "Estado") & L.al.fillna(False).astype(bool)].cod.unique()})),
                   D["n_mun_al"], len(D["al_ufs"]))

        v_br, v_al = value_of(BRASIL), value_of(AMZ)
        y0, b0 = first_valid(AMZ)
        var_al = change(v_al, b0) if y0 and y0 < YEAR else float("nan")
        muni = snap("Município")
        share = v_al / v_br * 100 if I.additive and v_br else float("nan")
        ratio = v_al / v_br * 100 if not I.additive and v_br else float("nan")

        c = st.columns(6)
        c[0].markdown(theme.kpi("Brasil", I.fmt(v_br), f"{I.label} · {YEAR}", "🇧🇷"), unsafe_allow_html=True)
        c[1].markdown(theme.kpi("Amazônia Legal", I.fmt(v_al), f"{I.label} · {YEAR}", "AL", "hi"), unsafe_allow_html=True)
        c[2].markdown(theme.kpi("Participação no Brasil" if I.additive else "Relação com o Brasil",
                                fmt.pct(share if I.additive else ratio),
                                "da Amazônia Legal no total nacional" if I.additive else "AL ÷ Brasil", "%"),
                      unsafe_allow_html=True)
        c[3].markdown(theme.kpi("Variação desde " + (str(y0) if y0 else "—"), arrow(var_al),
                                "Amazônia Legal, acumulada", "Δ"), unsafe_allow_html=True)
        if len(muni):
            top, bot = muni.loc[muni.valor.idxmax()], muni.loc[muni.valor.idxmin()]
            c[4].markdown(theme.kpi("Maior município", I.fmt(top.valor), top.label, "▲", "hi"), unsafe_allow_html=True)
            c[5].markdown(theme.kpi("Menor município", I.fmt(bot.valor), bot.label, "▼", "lo"), unsafe_allow_html=True)
        st.markdown("<div style='height:14px'></div>", unsafe_allow_html=True)

        if muni.empty:
            st.warning("Sem municípios com dado para os filtros selecionados.")
        else:
            a, b, c3 = st.columns([1.15, 1, 1])
            with a:
                theme.title("Mapa por estado", f"{I.label} · {YEAR}")
                st_df = snap("Estado")
                if len(st_df) >= 5:
                    plot(charts.choropleth(st_df, I, "Estado", **map_view("Estado"), height=370), "ov_map")
                    st.markdown(charts.legend_html(st_df, I), unsafe_allow_html=True)
            with b:
                theme.title("Distribuição dos municípios", "Faixas por quintil do valor no ano")
                plot(charts.donut(muni, I), "ov_donut")
            with c3:
                theme.title("Ranking geral · Top 5 municípios", f"{I.label} · {YEAR}")
                t5 = muni.nlargest(5, "valor")
                plot(charts.hbar(t5, I, 5, height=250), "ov_top5")
                tot = muni.valor.sum() if I.additive else None
                if tot:
                    st.caption(f"Os 5 maiores concentram **{fmt.pct(t5.valor.sum() / tot * 100)}** do total dos "
                               f"{len(muni):,} municípios filtrados.".replace(",", "."))

            st.markdown("---")
            left, right = st.columns([1.3, 1])
            with left:
                theme.title("Evolução temporal", "Brasil × Amazônia Legal × Grandes Regiões "
                            "(base 100 no primeiro ano com valor diferente de zero)")
                regs = data.territories(D, "Grande Região")
                sr = data.series(D, [BRASIL, AMZ, *regs.tid], IND)
                plot(charts.lines(sr, I, "indice", height=360), "ov_line")
            with right:
                theme.title("Comparação entre estados", f"Ordenação em {YEAR}")
                st_df = snap("Estado")
                plot(charts.hbar(st_df, I, 15, height=360), "ov_states")

        st.markdown("---")
        theme.title("Indicadores em destaque", "Série histórica da Amazônia Legal para cada indicador da base")
        for col, k in grid(D["indicators"]):
            ik = REG[k]
            s = data.series(D, [AMZ], k).dropna(subset=["valor"])
            with col:
                last = s.iloc[-1] if len(s) else None
                st.markdown(theme.kpi(ik.label, ik.fmt(last.valor) if last is not None else "—",
                                      f"{int(last.ano)} · " + ik.unit if last is not None else "", ik.icon),
                            unsafe_allow_html=True)
                if len(s) > 1:
                    plot(charts.sparkline(s.ano, s.valor, ik), f"spark_{k}")

# =========================================================================== #
# 2. MAPA TERRITORIAL
# =========================================================================== #
with tabs[1]:
    if tabs[1].open:
        m1, m2, m3 = st.columns([1, 1, 2])
        lvl = m1.radio("Escala", ["Estado", "Município"], horizontal=True,
                       key=state("w_map_lvl", "Estado", ["Estado", "Município"]))
        cores = ["Faixas (quintis)", "Contínua (log)" if I.log else "Contínua"]
        mode_lbl = m2.radio("Escala de cores", cores, horizontal=True, key=state("w_map_mode", cores[0], cores))
        mdf = snap(lvl)
        if len(mdf) < 5:
            st.warning("Poucos territórios com dado nesta combinação de filtros.")
        else:
            mc, side = st.columns([2.3, 1])
            with mc:
                theme.title(f"{I.label} por {lvl.lower()}", f"{YEAR} · {len(mdf):,} territórios".replace(",", "."))
                plot(charts.choropleth(mdf, I, lvl, "faixas" if mode_lbl.startswith("Faixas") else "continua",
                                       **map_view(lvl), height=640), "map_main")
                if mode_lbl.startswith("Faixas"):
                    st.markdown(charts.legend_html(mdf, I), unsafe_allow_html=True)
            with side:
                s1, s2 = st.columns(2)
                s1.metric("Mediana", I.fmt(mdf.valor.median()))
                s2.metric("Média", I.fmt(mdf.valor.mean()))
                s1.metric("Máximo", I.fmt(mdf.valor.max()))
                s2.metric("Mínimo", I.fmt(mdf.valor.min()))
                theme.title("10 maiores")
                plot(charts.hbar(mdf, I, 10, height=300), "map_top")
                theme.title("10 menores")
                plot(charts.hbar(mdf, I, 10, ascending=True, height=300, color=theme.TEAL), "map_bot")
        if I.kind == "moeda":
            st.markdown('<div class="note">Valores a preços correntes (nominais): comparações entre anos incluem '
                        'inflação.</div>', unsafe_allow_html=True)

# =========================================================================== #
# 3. PERFIL DO TERRITÓRIO
# =========================================================================== #
with tabs[2]:
    if tabs[2].open:
        p1, p2, p3 = st.columns([1, 1, 2])
        niveis = ["Município", "Estado", "Grande Região", "Amazônia Legal", "Brasil"]
        plvl = p1.selectbox("Granularidade", niveis, key=state("w_pf_lvl", "Município", niveis))
        terr = data.territories(D, plvl)
        if plvl == "Município":
            puf = p2.selectbox("UF", D["ufs"], key=state("w_pf_uf", "PA" if "PA" in D["ufs"] else D["ufs"][0], D["ufs"]))
            terr = terr[terr.uf == puf]
        else:
            p2.selectbox("UF", ["—"], disabled=True)
        default = next((i for i, l in enumerate(terr.label) if l.startswith("Belém")), 0)
        labels = terr.label.tolist()
        sel = p3.selectbox("Território", labels,
                           key=state("w_pf_terr", labels[default if plvl == "Município" else 0], labels))
        row = terr[terr.label == sel].iloc[0]
        tid = row.tid
        uf_of = row.uf if plvl in ("Município",) else None
        cod = int(row.cod)

        chips = [plvl]
        if plvl == "Município":
            mrow = L[(L.tid == tid)].iloc[0]
            chips += [str(mrow.uf), str(mrow.regiao), "Amazônia Legal" if bool(mrow.al) else "Fora da Amazônia Legal"]
            if D["porte"] is not None:
                chips.append("Porte: " + str(D["porte"].get(cod, "—")))
        st.markdown(f"<h2 style='margin:.2rem 0 .3rem'>{sel}</h2>" + "".join(f'<span class="chip">{c}</span>' for c in chips),
                    unsafe_allow_html=True)

        for col, k in grid(D["indicators"]):
            ik = REG[k]
            v = value_of(tid, k)
            yr0, v0 = first_valid(tid, k)
            peers = snap(plvl, k, YEAR, filt=False) if plvl in ("Município", "Estado", "Grande Região") else None
            rk = ""
            if peers is not None and len(peers) and tid in set(peers.tid):
                pos = int((peers.valor > v).sum() + 1)
                rk = f"{pos}º de {len(peers)} · "
            if yr0 and yr0 < YEAR and v0 == 0:
                sub = f"{rk}{YEAR} · era zero em {yr0}"
            elif yr0:
                sub = f"{rk}{YEAR} · {arrow(change(v, v0)) if yr0 < YEAR else '—'} desde {yr0}"
            else:
                sub = f"{YEAR}"
            with col:
                st.markdown(theme.kpi(ik.label, ik.fmt(v), sub, ik.icon), unsafe_allow_html=True)

        st.markdown("<div style='height:10px'></div>", unsafe_allow_html=True)
        g1, g2 = st.columns([1.4, 1])
        with g1:
            theme.title(f"{I.label}: território × referências", "Base 100 no primeiro ano com valor diferente de zero")
            refs = [tid]
            if plvl == "Município":
                refs.append(f"Estado:{cod // 100000}")
            if plvl != "Amazônia Legal" and plvl != "Brasil":
                refs.append(AMZ)
            if plvl != "Brasil":
                refs.append(BRASIL)
            refs = list(dict.fromkeys(refs))
            plot(charts.lines(data.series(D, refs, IND), I, "indice", height=360), "perfil_line")
        with g2:
            theme.title("Posição entre os pares", f"Distribuição de {I.label.lower()} em {YEAR}")
            peers = snap(plvl, IND, YEAR, filt=False) if plvl in ("Município", "Estado", "Grande Região") else None
            v = value_of(tid)
            if peers is not None and len(peers) > 3 and not fmt.isna(v):
                pct = float((peers.valor < v).mean() * 100)
                lo = charts.positive_min(peers.valor)
                tf = (lambda x: np.log10(np.clip(x, lo, None))) if I.log else (lambda x: x)
                fig = go.Figure(go.Histogram(x=tf(peers.valor), nbinsx=40,
                                             marker=dict(color=theme.SEQ[2], line=dict(color=theme.BG, width=.5)),
                                             hoverinfo="skip"))
                fig.add_vline(x=float(tf(v)), line=dict(color=theme.ORANGE, width=3),
                              annotation_text=f"{sel.split(' (')[0]}", annotation_font_color=theme.ORANGE)
                vals, txt = charts._ticks(I, lo if I.log else peers.valor.min(), peers.valor.max(), log=I.log)
                fig.update_layout(height=300, bargap=.05, yaxis_title="nº de territórios")
                fig.update_xaxes(tickvals=[float(tf(x)) for x in vals], ticktext=txt)
                plot(fig, "perfil_hist")
                st.markdown(f"**{sel}** está acima de **{fmt.num(pct, 0)}%** dos {len(peers)} "
                            f"{plvl.lower()}s com dado em {YEAR}" + (" (escala logarítmica)." if I.log else "."))
            else:
                st.info("Sem grupo de pares para esta granularidade.")

        theme.title("Série completa do território", "Todos os indicadores disponíveis")
        wide = (L[(L.tid == tid)].pivot_table(index="ano", columns="ind", values="valor", observed=True)
                .reindex(columns=D["indicators"]))
        show = wide.apply(lambda s: s.map(REG[s.name].fmt) if s.name in REG else s)
        st.dataframe(show.rename(columns={k: REG[k].label for k in show.columns}), width="stretch")
        st.caption("— indica ano sem dado na base de origem.")

# =========================================================================== #
# 4. SÉRIES TEMPORAIS
# =========================================================================== #
with tabs[3]:
    if tabs[3].open:
        st.markdown("Monte um conjunto de territórios de **qualquer granularidade** e compare suas trajetórias.")
        q1, q2 = st.columns([1, 2.2])
        with q1:
            use_br = st.checkbox("Brasil", key=state("w_ts_br", True))
            use_al = st.checkbox("Amazônia Legal", key=state("w_ts_al", True))
            medidas = ["Valor", "Índice (base 100)", "Variação % a.a."]
            mode_lbl = st.radio("Medida", medidas, key=state("w_ts_mode", "Valor", medidas))
            mode = {"Valor": "valor", "Índice (base 100)": "indice", "Variação % a.a.": "var"}[mode_lbl]
            log = st.checkbox("Escala logarítmica", disabled=mode != "valor", key=state("w_ts_log", False))
        with q2:
            regs = data.territories(D, "Grande Região")
            ests = data.territories(D, "Estado")
            muns = data.territories(D, "Município")
            r_sel = st.multiselect("Grandes Regiões", regs.label.tolist(),
                                   key=state("w_ts_reg", ["Norte"], regs.label.tolist()))
            e_sel = st.multiselect("Estados", ests.label.tolist(),
                                   key=state("w_ts_est", ["Pará", "Amazonas", "Mato Grosso"], ests.label.tolist()))
            m_sel = st.multiselect("Municípios", muns.label.tolist(),
                                   key=state("w_ts_mun", ["Belém (PA)", "Manaus (AM)"], muns.label.tolist()))
        tids = ([BRASIL] if use_br else []) + ([AMZ] if use_al else [])
        tids += regs[regs.label.isin(r_sel)].tid.tolist() + ests[ests.label.isin(e_sel)].tid.tolist()
        tids += muns[muns.label.isin(m_sel)].tid.tolist()
        if not tids:
            st.info("Selecione ao menos um território.")
        else:
            sr = data.series(D, tids, IND)
            theme.title(f"{I.label} — {mode_lbl.lower()}",
                        "Linhas conectam anos com dado; anos sem dado na base ficam sem marcador"
                        + ("; base 100 no primeiro ano com valor diferente de zero" if mode == "indice" else ""))
            plot(charts.lines(sr, I, mode, log), "ts_main")
            if sr.valor.isna().any():
                miss = sorted(sr[sr.valor.isna()].ano.unique())
                st.caption("Anos sem dado nas bases para este indicador: " + ", ".join(map(str, miss)) + ".")

            st.markdown("---")
            h1, h2 = st.columns([1, 1.25])
            with h1:
                theme.title("Crescimento médio anual (TCMA)", "Do primeiro ao último ano com dado de cada território")
                rows = []
                for t, g in sr.dropna(subset=["valor"]).groupby("tid", sort=False):
                    g = g.sort_values("ano")
                    rows.append(dict(label=g.label.iloc[0], nivel=g.nivel.iloc[0], tcma=data.cagr(
                        g.valor.iloc[0], g.valor.iloc[-1], int(g.ano.iloc[-1] - g.ano.iloc[0])),
                        de=int(g.ano.iloc[0]), ate=int(g.ano.iloc[-1])))
                cg = pd.DataFrame(rows).dropna(subset=["tcma"]).sort_values("tcma")
                fig = go.Figure(go.Bar(
                    x=cg.tcma, y=cg.label, orientation="h",
                    marker=dict(color=[theme.LEVEL_COLOR.get(n, theme.ACCENT) for n in cg.nivel], cornerradius=4),
                    text=[f"{fmt.num(v, 1)}% ({a}–{b})" for v, a, b in zip(cg.tcma, cg.de, cg.ate)],
                    textposition="outside", cliponaxis=False, hovertemplate="%{y}<br>%{text}<extra></extra>"))
                fig.update_layout(height=max(260, 34 * len(cg) + 60), margin=dict(r=90))
                fig.update_xaxes(ticksuffix="%")
                plot(fig, "ts_cagr")
            with h2:
                theme.title("Mapa de calor da variação anual", "Verde: crescimento · vermelho: queda (% a.a.)")
                plot(charts.growth_heatmap(sr), "ts_heat")

            st.markdown("---")
            theme.title("Todos os indicadores lado a lado", f"Território principal: {sr.label.iloc[0]} · "
                        "base 100 no primeiro ano com valor diferente de zero")
            first = sr.tid.iloc[0]
            fig = go.Figure()
            for i, k in enumerate(D["indicators"]):
                colr = theme.COLORWAY[i % len(theme.COLORWAY)]
                t = charts.transform(data.series(D, [first], k), "indice")
                if len(t):
                    fig.add_trace(go.Scatter(x=t.ano, y=t.y, name=REG[k].label, mode="lines+markers", connectgaps=True,
                                             line=dict(color=colr, width=2.6), marker=dict(size=7),
                                             hovertemplate=REG[k].label + " %{x}: <b>%{y:.1f}</b><extra></extra>"))
            fig.update_layout(height=340)
            fig.update_xaxes(dtick=1, tickformat="d")
            plot(fig, "ts_multi")
            with st.expander("Dados da seleção"):
                out = sr.assign(valor_fmt=sr.valor.map(I.fmt))
                st.dataframe(out.rename(columns={"tid": "id", "label": "território", "nivel": "nível", "valor": "valor",
                                                 "valor_fmt": "valor (formatado)"}), width="stretch", hide_index=True)
                st.download_button("Baixar CSV", sr.to_csv(index=False, sep=";", decimal=",").encode("utf-8-sig"),
                                   "series_selecionadas.csv", "text/csv")

# =========================================================================== #
# 5. RANKING
# =========================================================================== #
with tabs[4]:
    if tabs[4].open:
        r1, r2, r3 = st.columns([1, 1.4, 1])
        rniveis = ["Município", "Estado", "Grande Região"]
        rlvl = r1.radio("Granularidade", rniveis, horizontal=True, key=state("w_rk_lvl", "Município", rniveis))
        busca = r2.text_input("Buscar território", placeholder="ex.: Belém", key=state("w_rk_busca", ""))
        topn = r3.slider("Barras no gráfico", 5, 40, key=state("w_rk_topn", 15))
        rk = snap(rlvl if rlvl != "Grande Região" else rlvl)
        if rk.empty:
            st.warning("Sem dados para os filtros selecionados.")
        else:
            rk = rk.sort_values("valor", ascending=False).reset_index(drop=True)
            rk["pos"] = np.arange(1, len(rk) + 1)
            ch = change_since_start(rlvl)
            rk["var"] = rk.cod.map(ch)
            rk["share"] = rk.valor / rk.valor.sum() * 100 if I.additive else np.nan
            rk["rel"] = rk.valor / rk.valor.max() * 100
            rk["faixa"] = (data.bands(rk.valor).astype(int) + 1).map(lambda i: f"Faixa {i}")
            view = rk[rk.label.str.contains(busca, case=False, regex=False)] if busca else rk
            tbl = pd.DataFrame({
                "Posição": view.pos, "Território": view.label, "UF": view.uf if rlvl != "Grande Região" else "",
                f"{I.label}": view.valor.map(I.fmt), "Intensidade": view.rel,
                "Variação desde o 1º ano (%)": view["var"].round(1), "Participação (%)": view.share.round(2),
                "Faixa": view.faixa})
            cfg = {"Intensidade": st.column_config.ProgressColumn("Intensidade", min_value=0, max_value=100, format=" "),
                   "Variação desde o 1º ano (%)": st.column_config.NumberColumn(format="%.1f%%"),
                   "Participação (%)": st.column_config.NumberColumn(format="%.2f%%")}
            if not I.additive:
                tbl = tbl.drop(columns=["Participação (%)"])
            t1, t2 = st.columns([1.5, 1])
            with t1:
                theme.title(f"Ranking de {rlvl.lower()}s", f"{I.label} · {YEAR} · {len(view):,} territórios".replace(",", "."))
                st.dataframe(tbl, width="stretch", hide_index=True, height=620, column_config=cfg)
                st.download_button("Baixar ranking (CSV)", rk[["pos", "label", "uf", "valor", "var", "share", "faixa"]]
                                   .rename(columns={"pos": "posicao", "label": "territorio", "var": "variacao_pct",
                                                    "share": "participacao_pct"})
                                   .to_csv(index=False, sep=";", decimal=",").encode("utf-8-sig"),
                                   f"ranking_{rlvl}_{YEAR}.csv", "text/csv")
            with t2:
                theme.title(f"Top {topn}")
                plot(charts.hbar(rk, I, topn, height=max(300, 26 * topn + 40)), "rk_bar")

# =========================================================================== #
# 6. COMPARAÇÕES
# =========================================================================== #
with tabs[5]:
    if tabs[5].open:
        # ---- A. entre granularidades -------------------------------------------------
        theme.title("Entre granularidades", f"{I.label} em {YEAR}: Brasil, Amazônia Legal, Regiões e Estados")
        parts = []
        for lv in ("Brasil", "Amazônia Legal", "Grande Região", "Estado"):
            s = snap(lv, filt=False)
            if lv == "Estado":
                s = snap("Estado")
            parts.append(s.assign(nivel=lv))
        bm = pd.concat(parts)
        logb = st.checkbox("Escala logarítmica", key=state("w_bm_log", I.log))
        if bm.empty:
            st.warning("Sem dados no ano selecionado.")
        else:
            plot(charts.benchmark(bm, I, logb), "bm")
        st.markdown("---")

        # ---- B. dispersão entre indicadores -------------------------------------------
        theme.title("Relação entre indicadores", "Cada ponto é um território; linha tracejada = tendência")
        b1, b2, b3 = st.columns(3)
        sc_lvl = b1.radio("Granularidade", ["Município", "Estado"], horizontal=True,
                          key=state("w_sc_lvl", "Município", ["Município", "Estado"]))
        xk = b2.selectbox("Eixo X", D["indicators"], format_func=lambda k: REG[k].label,
                          key=state("w_sc_x", D["indicators"][0], D["indicators"]))
        yk = b3.selectbox("Eixo Y", D["indicators"], format_func=lambda k: REG[k].label,
                          key=state("w_sc_y", D["indicators"][min(2, len(D["indicators"]) - 1)], D["indicators"]))
        sx, sy = snap(sc_lvl, xk), snap(sc_lvl, yk)
        sd = sx[["cod", "label", "uf", "valor"]].rename(columns={"valor": "x"}).merge(
            sy[["cod", "valor"]].rename(columns={"valor": "y"}), on="cod")
        if D["pop_col"]:
            sd = sd.merge(snap(sc_lvl, D["pop_col"])[["cod", "valor"]].rename(columns={"valor": "pop"}), on="cod", how="left")
        if len(sd) < 6:
            st.info("Poucos pontos com os dois indicadores neste ano. Tente outro ano ou outro par de indicadores.")
        else:
            plot(charts.scatter(sd, REG[xk], REG[yk], log=REG[xk].log and REG[yk].log,
                                size_col="pop" if "pop" in sd else None), "sc")
            st.caption(f"{len(sd):,} territórios · tamanho do ponto proporcional à população.".replace(",", "."))
        st.markdown("---")

        # ---- C. distribuição por UF ---------------------------------------------------
        theme.title("Distribuição dos municípios por UF", f"{I.label} em {YEAR} (caixas: quartis; pontos: municípios atípicos)")
        mm = snap("Município")
        if len(mm) > 10:
            plot(charts.box_by_uf(mm, I, log=I.log), "box")
        st.markdown("---")

        # ---- D. face a face -----------------------------------------------------------
        theme.title("Face a face", "Compare dois territórios, mesmo de granularidades diferentes")
        fa, fb = st.columns(2)
        picks = []
        for colx, name, defl, defu in ((fa, "A", "Estado", "Pará"), (fb, "B", "Estado", "Amazonas")):
            with colx:
                lv = st.selectbox(f"Granularidade {name}", LEVELS[::-1], key=state(f"w_ff_l{name}", defl, LEVELS[::-1]))
                tt = data.territories(D, lv)
                opts = tt.label.tolist()
                lab = st.selectbox(f"Território {name}", opts,
                                   key=state(f"w_ff_t{name}", defu if defu in opts else opts[0], opts))
                picks.append((lab, tt[tt.label == lab].tid.iloc[0]))
        rows = []
        for k in D["indicators"]:
            va, vb = value_of(picks[0][1], k), value_of(picks[1][1], k)
            rows.append({"Indicador": REG[k].label, picks[0][0]: REG[k].fmt(va), picks[1][0]: REG[k].fmt(vb),
                         "A ÷ B": fmt.num(va / vb, 2) + "×" if vb and not fmt.isna(va) and not fmt.isna(vb) else "—"})
        st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)
        plot(charts.lines(data.series(D, [p[1] for p in picks], IND), I, "indice", height=330), "ff_line")
        st.caption(f"{I.label}, base 100 no primeiro ano com valor diferente de zero.")

# =========================================================================== #
# 7. SOBRE
# =========================================================================== #
with tabs[6]:
    if tabs[6].open:
        s1, s2 = st.columns([1.2, 1])
        with s1:
            st.markdown("### Sobre o painel")
            st.markdown(
                "Este painel apresenta o **Diagnóstico Quantitativo da Amazônia Legal** (PRDA · Produto 1), "
                "no âmbito do projeto BRA/21/005 — SUDAM, PNUD e Instituto Publix. Ele permite ler cada indicador "
                "nas escalas **Brasil, Amazônia Legal, Grandes Regiões, Estados e Municípios**, com mapas, séries "
                "históricas, rankings e comparações.")
            mf = D["manifest"]
            st.markdown(
                "**Origem dos dados.** As bases vêm da planilha do Banco de Indicadores do PRDA "
                f"(*{mf['planilha']}*). Brasil, Grandes Regiões e Estados usam os valores publicados nas abas de "
                "recorte; os textos de cada indicador vêm da aba *Lista de Indicadores*.")
            st.markdown(
                "**Amazônia Legal.** Calculada a partir dos municípios marcados como *Amazônia Legal = SIM* "
                f"({D['n_mun_al']} municípios em {len(D['al_ufs'])} UFs), conforme a regra de agregação de cada "
                "indicador: soma, para totais, ou média ponderada (razão entre totais), para taxas e valores per capita.")
            st.caption(f"Versão da base: {mf['versao']} · gerada em {mf['gerado_em'][:16].replace('T', ' ')}")
            st.markdown("**Faixas.** Os mapas e gráficos de distribuição dividem os territórios em cinco faixas de "
                        "mesmo tamanho (quintis) no ano selecionado.")
        with s2:
            st.markdown("### Disponibilidade dos dados")
            cov = (L[L.nivel == "Município"].assign(ok=lambda d: d.valor.notna())
                   .groupby(["ind", "ano"], observed=True).ok.mean().mul(100).unstack("ano")
                   .reindex(D["indicators"]))
            fig = go.Figure(go.Heatmap(
                z=cov.values, x=cov.columns, y=[REG[k].label for k in cov.index], zmin=0, zmax=100,
                colorscale=[[0, "#F4E3D7"], [.5, "#B2D78C"], [1, theme.INK]], text=np.round(cov.values, 0), texttemplate="%{text:.0f}%",
                textfont=dict(size=9), hovertemplate="%{y} · %{x}: %{z:.0f}% dos municípios<extra></extra>",
                showscale=False))
            fig.update_layout(height=26 * len(cov) + 40, margin=dict(l=0, r=0, t=0, b=0))
            fig.update_xaxes(dtick=1, tickformat="d")
            plot(fig, "cov")
            st.caption("% de municípios com valor informado em cada ano. Lacunas vêm das bases de origem "
                       "(ex.: população em anos de Censo; PIB ainda não divulgado).")

        st.markdown("### Fichas dos indicadores")
        for k in D["indicators"]:
            ik = REG[k]
            m = D["meta"].get(ik.key)
            with st.expander(f"{ik.key} · {ik.label} — {ik.unit}"):
                if not m:
                    st.write("Sem ficha técnica cadastrada.")
                    continue
                st.write(m["description"])
                st.markdown(
                    f"- **Eixo:** {m['axis']}\n- **Tema:** {m['theme']} · {m['subtheme']}\n"
                    f"- **Fonte:** {m['source']} ([{m['table']}]({m['link']}))\n"
                    f"- **Periodicidade / série:** {m['periodicity']} · {m['series']}\n"
                    f"- **Unidade:** {m['unit']} · **Polaridade:** {m['polarity']}\n"
                    f"- **Regra de agregação (ficha):** {m['aggregation']} · **Menor unidade:** {m['minTerritory']}\n"
                    f"- **Amazônia Legal no painel:** {m.get('aggregationApplied', '—')}")
                st.markdown(f'<div class="note"><b>Limitações.</b> {m["limits"]}</div>', unsafe_allow_html=True)

theme.footer()
