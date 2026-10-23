"""PRDA · Diagnóstico Quantitativo da Amazônia Legal — painel Streamlit.

Executar:  streamlit run main.py
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from src import charts, data, fmt, theme
from src.data import AGRUPAMENTOS, AGRUPAMENTOS_SN, LEVELS, ORDEM_CLASSES, PORTES

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
MODOS_ANO = ["Mais recente de cada indicador", "Ano específico"]
ABAS = ["Visão Geral", "Visão Estadual", "Mapa Territorial", "Perfil do Território", "Séries Temporais",
        "Ranking", "Comparações", "Sobre o Painel"]
TERRIT = {"recorte", "uf", "porte", "grupos"}
FILTROS = {"Visão Geral": {"ind", "ano"} | TERRIT, "Mapa Territorial": {"ind", "ano"} | TERRIT,
           "Visão Estadual": {"ind", "ano"}, "Perfil do Território": {"ind", "ano"}, "Séries Temporais": {"ind"},
           "Ranking": {"ind", "ano"} | TERRIT, "Comparações": {"ind", "ano"} | TERRIT, "Sobre o Painel": set()}
NOTAS = {"Visão Estadual": "O estado é escolhido na própria página; a tabela do topo usa o último ano com dado "
                           "de cada indicador.",
         "Perfil do Território": "O território (e a UF, para municípios) é escolhido na própria página.",
         "Séries Temporais": "Os territórios são escolhidos na própria página; as séries mostram todos os anos.",
         "Sobre o Painel": "Esta página não usa filtros."}

theme.header()
tabs = st.tabs(ABAS, key="aba", on_change="rerun")
T = dict(zip(ABAS, tabs))
ABA = next((a for a, t in T.items() if t.open), ABAS[0])
show = set(FILTROS[ABA])
# a escala escolhida dentro da aba define quais filtros territoriais fazem efeito
escala = {"Mapa Territorial": st.session_state.get("w_map_lvl", "Estado"),
          "Ranking": st.session_state.get("w_rk_lvl", "Município")}.get(ABA)
if escala == "Estado":
    show -= {"porte", "grupos"}
elif escala == "Grande Região":
    show -= TERRIT

def grupo(nome: str, dica: str):
    st.markdown(f'<div class="fgroup">{nome}</div><div class="fhint">{dica}</div>', unsafe_allow_html=True)


RECORTES = {"Amazônia Legal": "Só Amazônia Legal", "Brasil": "Brasil inteiro"}

with st.sidebar:
    st.markdown("### Filtros")
    st.caption(f"Mostrando os filtros que valem para a aba **{ABA}**.")
    if "ind" in show:
        grupo("O que medir", "Definem o indicador e o ano mostrados em todos os gráficos desta aba.")
    eixos = sorted({REG[k].axis for k in D["indicators"]})
    k = state("w_eixo", "Todos os eixos", ["Todos os eixos", *eixos])
    eixo = (st.selectbox("Eixo temático", ["Todos os eixos", *eixos], key=k,
                         help="Só encurta a lista de indicadores abaixo; não filtra os gráficos.")
            if "ind" in show else st.session_state[k])
    pool = [k for k in D["indicators"] if eixo == "Todos os eixos" or REG[k].axis == eixo]
    k = state("w_ind", pool[0], pool)
    IND = (st.selectbox("Indicador", pool, format_func=lambda k: REG[k].label, key=k,
                        help="Indicador mostrado nos mapas, gráficos, cartões e rankings desta aba.")
           if "ind" in show else st.session_state[k])
    I = REG[IND]
    if "ind" in show:
        st.caption(f"Unidade: {I.unit}" + (f" · {I.polarity_text}" if I.polarity_text else "")
                   + f"  \nAmazônia Legal: {I.agg_note.lower()}.")
    years = data.years_with_data(D, IND)
    k = state("w_ano_modo", MODOS_ANO[0], MODOS_ANO)
    modo_ano = (st.radio("Ano de referência", MODOS_ANO, key=k,
                         help="Mais recente: cada indicador aparece no seu último ano com dado, e a evolução é "
                              "calculada desde o primeiro ano com dado. Ano específico: todos os indicadores no "
                              "ano escolhido. Gráficos de evolução mostram todos os anos nos dois modos.")
                if "ano" in show else st.session_state[k])
    RECENTE = modo_ano == MODOS_ANO[0]
    k = state("w_ano", years[-1], years)
    if "ano" in show and RECENTE:
        YEAR = years[-1]
        st.caption(f"**{REG[IND].label}**: {YEAR}, o último ano com dado. Cada indicador usa o seu próprio último ano.")
    elif "ano" in show and len(years) > 1:
        YEAR = st.select_slider("Ano", years, key=k,
                                help="Ano dos mapas, cartões e rankings. Gráficos de evolução mostram todos os anos.")
    else:
        YEAR = years[-1] if RECENTE else st.session_state[k]
        if "ano" in show:
            st.caption(f"Ano de referência: **{YEAR}** (único ano com dado)")

    if show & TERRIT:
        grupo("Quais territórios", "Filtram os <b>estados e municípios</b> dos mapas, rankings e distribuições. "
              "Os totais de Brasil, Amazônia Legal e Grandes Regiões não mudam.")
    k = state("w_recorte", "Amazônia Legal", list(RECORTES))
    recorte = (st.radio("Abrangência", list(RECORTES), format_func=RECORTES.get, horizontal=True, key=k,
                        help=f"Só Amazônia Legal: {len(D['al_ufs'])} estados e {D['n_mun_al']} municípios. "
                             "Brasil inteiro: todos os estados e municípios do país.")
               if "recorte" in show else st.session_state[k])
    AL_ONLY = recorte == "Amazônia Legal"
    ufs_pool = D["al_ufs"] if AL_ONLY else D["ufs"]
    k = state("w_ufs", [], ufs_pool)
    UFS = (st.multiselect("Estados (UF)", ufs_pool, placeholder="Todos", key=k,
                          help="Mostra só esses estados e os municípios deles.") if "uf" in show else [])
    portes = [p[0] for p in PORTES]
    k = state("w_porte", [], portes)
    PORTE = (st.multiselect("Porte do município (habitantes)", portes, placeholder="Todos", key=k,
                            help="Só para municípios: faixa de população (mediana dos anos com dado). "
                                 "Não altera estados.") if "porte" in show else [])
    GRUPOS = {}
    carac = D["carac"]
    if "grupos" in show and carac is not None:
        base = carac[carac.al] if AL_ONLY else carac
        if UFS:
            base = base[base.uf.isin(UFS)]
        with st.expander("Mais filtros de municípios", expanded=bool(st.session_state.get("w_grupos_aberto"))):
            st.caption("Só para municípios. Combinam entre si (e com UF e porte): sobram os que atendem a todos.")
            for col, nome in AGRUPAMENTOS.items():
                pool = sorted(base[col].dropna().unique())
                if col == "rg_imediata" and GRUPOS.get("rg_intermediaria"):
                    pool = sorted(base[base.rg_intermediaria.isin(GRUPOS["rg_intermediaria"])][col].dropna().unique())
                if col in ("idhm", "idsc", "ips"):
                    pool = [c for c in ORDEM_CLASSES if c in pool]
                k = state(f"w_g_{col}", [], pool)
                sel = st.multiselect(nome, pool, placeholder="Todos", key=k)
                if sel:
                    GRUPOS[col] = sel
            for col, nome in AGRUPAMENTOS_SN.items():
                k = state(f"w_g_{col}", "Todos", ["Todos", "Sim", "Não"])
                sel = st.radio(nome, ["Todos", "Sim", "Não"], horizontal=True, key=k)
                if sel != "Todos":
                    GRUPOS[col] = [sel == "Sim"]
            st.session_state["w_grupos_aberto"] = bool(GRUPOS)
    if ABA in NOTAS:
        st.caption(NOTAS[ABA])
    elif escala == "Grande Região":
        st.caption("Grandes Regiões não têm recorte por UF ou porte.")
    st.markdown("---")
    st.caption("SUDAM · PNUD · Instituto Publix\n\nProjeto BRA/21/005")


def year_for(ind: str) -> int:
    """Ano usado para um indicador: o último com dado (modo recente) ou o ano escolhido na barra lateral."""
    return D["latest"].get(ind, YEAR) if RECENTE else YEAR


ANO_TXT = "no ano mais recente de cada indicador" if RECENTE else f"em {YEAR}"


def nome_grupo(col: str) -> str:
    return {**AGRUPAMENTOS, **AGRUPAMENTOS_SN}[col]


def _sn(v):
    return ("sim" if v else "não") if isinstance(v, (bool, np.bool_)) else str(v)


def escopo(level: str, n: int | None = None) -> str:
    """Descreve os territórios que sobram depois dos filtros (ex.: '773 municípios da Amazônia Legal · UF: PA')."""
    plural = {"Município": "municípios", "Estado": "estados", "Grande Região": "Grandes Regiões"}[level]
    if n == 1:
        plural = {"Município": "município", "Estado": "estado", "Grande Região": "Grande Região"}[level]
    qtd = f"{n:,} ".replace(",", ".") if n is not None else ""
    if level == "Grande Região":
        return f"{qtd}{plural}"
    out = f"{qtd}{plural} " + ("da Amazônia Legal" if AL_ONLY else "do Brasil")
    if UFS:
        out += " · UF: " + ", ".join(UFS)
    if PORTE and level == "Município":
        out += " · porte: " + ", ".join(PORTE)
    if level == "Município":
        out += "".join(f" · {nome_grupo(c)}: {', '.join(map(_sn, v))}" for c, v in GRUPOS.items())
    return out


def barra_filtros():
    """Resumo, no topo da aba, dos filtros da barra lateral que estão valendo nela."""
    if not show:
        return
    itens = [f"Indicador: <b>{I.label}</b> · {I.unit}"]
    if "ano" in show:
        itens.append(f"Ano: <b>{YEAR}</b>" + (" (mais recente do indicador)" if RECENTE else ""))
    if "recorte" in show:
        itens.append(f"Abrangência: <b>{RECORTES[recorte]}</b>")
    if "uf" in show:
        itens.append("UF: <b>" + (", ".join(UFS) if UFS else "todas") + "</b>")
    if "porte" in show:
        itens.append("Porte: <b>" + (", ".join(PORTE) if PORTE else "todos") + "</b>")
    if "grupos" in show:
        itens += [f"{nome_grupo(c)}: <b>{', '.join(map(_sn, v))}</b>" for c, v in GRUPOS.items()]
    st.markdown('<div class="fbar"><span class="t">Filtros aplicados</span>' + "".join(f"<span>{x}</span>" for x in itens)
                + "</div>", unsafe_allow_html=True)


def snap(level: str, ind: str = IND, year: int | None = None, filt: bool = True) -> pd.DataFrame:
    year = year_for(ind) if year is None else year
    if not filt:
        return data.snapshot(D, level, ind, year)
    return data.snapshot(D, level, ind, year, al_only=AL_ONLY, ufs=UFS or None, portes=PORTE or None,
                         grupos=GRUPOS or None)


def value_of(tid: str, ind: str = IND, year: int | None = None) -> float:
    year = year_for(ind) if year is None else year
    s = data.series(D, [tid], ind)
    v = s.loc[s.ano == year, "valor"]
    return float(v.iloc[0]) if len(v) and pd.notna(v.iloc[0]) else float("nan")


def first_valid(tid: str, ind: str = IND, upto: int | None = None):
    upto = year_for(ind) if upto is None else upto
    s = data.series(D, [tid], ind).dropna(subset=["valor"])
    s = s[s.ano <= upto]
    return (int(s.ano.iloc[0]), float(s.valor.iloc[0])) if len(s) else (None, float("nan"))


def change_since_start(level: str, ind: str = IND, year: int | None = None) -> pd.Series:
    year = year_for(ind) if year is None else year
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
with T["Visão Geral"]:
    if T["Visão Geral"].open:
        barra_filtros()
        theme.hero(tuple(sorted({str(c) for c in L[(L.nivel == "Estado") & L.al.fillna(False).astype(bool)].cod.unique()})),
                   D["n_mun_al"], len(D["al_ufs"]))

        v_br, v_al = value_of(BRASIL), value_of(AMZ)
        y0, b0 = first_valid(AMZ)
        var_al = change(v_al, b0) if y0 and y0 < YEAR else float("nan")
        muni = snap("Município")
        share = v_al / v_br * 100 if I.additive and v_br else float("nan")
        ratio = v_al / v_br * 100 if not I.additive and v_br else float("nan")

        theme.title(f"{I.label} em {YEAR}: Brasil, Amazônia Legal e municípios extremos",
                    f"Os quatro primeiros cartões são totais fixos; maior e menor município saem dos "
                    f"{escopo('Município', len(muni))}.")
        c = st.columns(6)
        c[0].markdown(theme.kpi("Brasil", I.fmt(v_br), f"{I.label} · {YEAR}", "🇧🇷"), unsafe_allow_html=True)
        c[1].markdown(theme.kpi("Amazônia Legal", I.fmt(v_al), f"{I.label} · {YEAR}", "AL", "hi"), unsafe_allow_html=True)
        c[2].markdown(theme.kpi("Participação no Brasil" if I.additive else "Relação com o Brasil",
                                fmt.pct(share if I.additive else ratio),
                                "da Amazônia Legal no total nacional" if I.additive else "AL ÷ Brasil", "%"),
                      unsafe_allow_html=True)
        c[3].markdown(theme.kpi("Variação desde " + (str(y0) if y0 else "—"), arrow(var_al),
                                f"Amazônia Legal, de {y0} a {YEAR}" if y0 else "Amazônia Legal", "Δ"),
                      unsafe_allow_html=True)
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
                st_df = snap("Estado")
                theme.title(f"{I.label} por estado", f"{YEAR} · {escopo('Estado', len(st_df))} · "
                            "cor = faixa do estado (5 faixas com o mesmo nº de estados)")
                if len(st_df) >= 5:
                    plot(charts.choropleth(st_df, I, "Estado", **map_view("Estado"), height=370), "ov_map")
                    st.markdown(charts.legend_html(st_df, I), unsafe_allow_html=True)
                else:
                    st.info(f"O mapa por estado divide os estados em 5 faixas e precisa de pelo menos 5 estados; "
                            f"o filtro atual deixa {len(st_df)}. Para ver os municípios desses estados no mapa, "
                            "use a aba Mapa Territorial.")
            with b:
                theme.title(f"Municípios por faixa de {charts.low(I.label)}",
                            f"{YEAR} · {escopo('Município', len(muni))} divididos em 5 faixas de mesmo tamanho; "
                            "a legenda mostra os limites de cada faixa")
                plot(charts.donut(muni, I), "ov_donut")
            with c3:
                theme.title(f"5 municípios com maior {charts.low(I.label)}",
                            f"{YEAR} · entre os {escopo('Município', len(muni))}")
                t5 = muni.nlargest(5, "valor")
                plot(charts.hbar(t5, I, 5, height=250), "ov_top5")
                tot = muni.valor.sum() if I.additive else None
                if tot:
                    st.caption(f"Os 5 maiores concentram **{fmt.pct(t5.valor.sum() / tot * 100)}** do total dos "
                               f"{len(muni):,} municípios filtrados.".replace(",", "."))

            st.markdown("---")
            left, right = st.columns([1.3, 1])
            with left:
                theme.title(f"Evolução de {charts.low(I.label)}: Brasil, Amazônia Legal e Grandes Regiões",
                            "Índice: base 100 = primeiro ano com valor diferente de zero. Mostra quem cresceu mais, não o tamanho.", fixo=True)
                regs = data.territories(D, "Grande Região")
                sr = data.series(D, [BRASIL, AMZ, *regs.tid], IND)
                plot(charts.lines(sr, I, "indice", height=360), "ov_line")
            with right:
                st_df = snap("Estado")
                theme.title(f"{I.label} por estado, do maior para o menor",
                            f"{YEAR} · " + (f"15 maiores entre os {escopo('Estado', len(st_df))}" if len(st_df) > 15
                                            else escopo("Estado", len(st_df))))
                plot(charts.hbar(st_df, I, 15, height=360), "ov_states")

        st.markdown("---")
        theme.title("Todos os indicadores na Amazônia Legal",
                    "Valor no último ano com dado de cada indicador e a evolução desde o primeiro ano", fixo=True)
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
# 2. VISÃO ESTADUAL
# =========================================================================== #
def _pontos(c):
    if isinstance(c[0], (int, float)):
        yield c
    else:
        for x in c:
            yield from _pontos(x)


def uf_view(cod_uf: int, width: int = 700, height: int = 480) -> dict:
    """Centro e zoom do mapa para enquadrar uma UF inteira."""
    f = next(f for f in charts.geojson("Estado")["features"] if f["id"] == f"{cod_uf:02d}")
    p = np.array(list(_pontos(f["geometry"]["coordinates"])))
    (x0, y0), (x1, y1) = p.min(axis=0), p.max(axis=0)
    zoom = min(np.log2(width * 360 / (256 * max(x1 - x0, .1))), np.log2(height * 360 / (256 * max(y1 - y0, .1))))
    return dict(zoom=float(np.clip(zoom - .25, 2.5, 9)), center=((y0 + y1) / 2, (x0 + x1) / 2))


def tabela_longa(d: pd.DataFrame) -> pd.DataFrame:
    """Linhas com valor, na unidade exibida no painel, prontas para download."""
    d = d[d.valor.notna()]
    ind = d.ind.astype(str)
    return pd.DataFrame({
        "nivel": d.nivel.astype(str), "codigo_ibge": d.cod.astype(int), "territorio": d.nome.astype(str),
        "uf": d.uf.astype(str).replace("nan", ""), "ano": d.ano.astype(int), "id_indicador": ind,
        "indicador": ind.map(lambda k: REG[k].label), "unidade": ind.map(lambda k: REG[k].unit),
        "valor": d.valor * ind.map(lambda k: REG[k].scale).astype(float)})


def csv_bytes(df: pd.DataFrame) -> bytes:
    return df.to_csv(index=False, sep=";", decimal=",").encode("utf-8-sig")


with T["Visão Estadual"]:
    if T["Visão Estadual"].open:
        barra_filtros()
        ests = data.territories(D, "Estado")
        e1, e2 = st.columns([1, 2])
        todos = e2.checkbox("Incluir estados fora da Amazônia Legal", key=state("w_ve_todos", False),
                            help="Por padrão a lista traz só os 9 estados da Amazônia Legal.")
        pool_e = ests if todos else ests[ests.uf.isin(D["al_ufs"])]
        nomes = pool_e.label.tolist()
        sel = e1.selectbox("Estado", nomes, key=state("w_ve_est", "Pará" if "Pará" in nomes else nomes[0], nomes))
        er = pool_e[pool_e.label == sel].iloc[0]
        uf, cod_uf, tid = str(er.uf), int(er.cod), str(er.tid)
        REGIAO = f"Grande Região:{cod_uf // 10}"
        AGG = L[L.nivel != "Município"]
        reg_nome = str(AGG.loc[AGG.tid == REGIAO, "nome"].iloc[0])
        is_al = uf in D["al_ufs"]
        mun_uf = L[(L.nivel == "Município") & (L.uf == uf)]
        n_mun = int(mun_uf.cod.nunique())

        chips = [uf, f"Região {reg_nome}", "Amazônia Legal" if is_al else "Fora da Amazônia Legal", f"{n_mun} municípios"]
        st.markdown(f"<h2 style='margin:.2rem 0 .3rem'>{sel}</h2>" + "".join(f'<span class="chip">{c}</span>' for c in chips),
                    unsafe_allow_html=True)

        # ---- A. todos os indicadores ---------------------------------------------------
        COMP = "Estado × Amazônia Legal"
        theme.title(f"{sel} em todos os indicadores, comparado com a Região {reg_nome}, a Amazônia Legal e o Brasil",
                    "Cada indicador no último ano com dado para o estado. Posição: 1º = maior valor.")
        rows, cores = [], []
        GOOD, BAD = theme.GREEN, theme.RED
        for k in D["indicators"]:
            ik = REG[k]
            d = AGG[(AGG.ind == k) & AGG.valor.notna()]
            de = d[d.tid == tid]
            row = {"Indicador": charts.axis_label(ik)}
            if de.empty:
                rows.append(row | {"Ano": "—"})
                cores.append("")
                continue
            y = int(de.ano.max())
            dy = d[d.ano == y]
            val = dict(zip(dy.tid.astype(str), dy.valor))
            v, v_al = val[tid], val.get(AMZ, float("nan"))
            e_all = dy[dy.nivel == "Estado"]
            e_al = e_all[e_all.al.fillna(False).astype(bool)]
            row |= {"Ano": str(y), sel: ik.fmt(v)}
            if is_al:
                row["Posição na Amazônia Legal"] = f"{int((e_al.valor > v).sum()) + 1}º de {len(e_al)}"
            row |= {"Posição no Brasil": f"{int((e_all.valor > v).sum()) + 1}º de {len(e_all)}",
                    f"Região {reg_nome}": ik.fmt(val.get(REGIAO, float("nan"))),
                    "Amazônia Legal": ik.fmt(v_al), "Brasil": ik.fmt(val.get(BRASIL, float("nan")))}
            cor = ""
            if ik.additive:
                row[COMP] = f"{fmt.pct(v / v_al * 100)} do total" if is_al and v_al else "—"
            else:
                dif = change(v, v_al)
                row[COMP] = "—" if fmt.isna(dif) else ("+" if dif >= 0 else "−") + fmt.pct(abs(dif))
                if not fmt.isna(dif) and ik.polarity and abs(dif) >= 0.05:
                    cor = GOOD if dif * ik.polarity > 0 else BAD
            rows.append(row)
            cores.append(cor)
        resumo = pd.DataFrame(rows).fillna("—")
        sty = resumo.style.apply(lambda s: [f"color:{c}; font-weight:700" if c else "" for c in cores], subset=[COMP])
        st.dataframe(sty, hide_index=True, width="stretch", column_config={
            "Ano": st.column_config.TextColumn(help="Último ano com dado do indicador para o estado."),
            "Posição na Amazônia Legal": st.column_config.TextColumn(help="Entre os 9 estados da Amazônia Legal."),
            "Posição no Brasil": st.column_config.TextColumn(help="Entre os 27 estados."),
            COMP: st.column_config.TextColumn(
                help="Totais (somas): participação do estado no total da Amazônia Legal. Taxas e médias: quanto o "
                     "estado está acima (+) ou abaixo (−) da Amazônia Legal; verde = situação melhor, vermelho = pior, "
                     "conforme a polaridade do indicador.")})
        st.caption(f"Última coluna: para totais, participação do estado na Amazônia Legal; para taxas e médias, "
                   "diferença em relação à Amazônia Legal (verde = melhor, vermelho = pior, sem cor quando o indicador "
                   "não tem polaridade). — indica ausência de dado.")
        st.markdown("---")

        # ---- B. evolução e posição do indicador escolhido --------------------------------
        g1, g2 = st.columns([1.4, 1])
        with g1:
            medidas = ["Índice (base 100)", "Valor"]
            med = st.radio("Medida", medidas, horizontal=True,
                           key=state("w_ve_med", medidas[0] if I.additive else medidas[1], medidas),
                           help="Índice: crescimento relativo, bom para totais de tamanhos diferentes. "
                                "Valor: o número publicado, bom para taxas e médias.")
            theme.title(f"Evolução de {charts.low(I.label)}: {sel}, Região {reg_nome}, Amazônia Legal e Brasil",
                        "Todos os anos com dado" + ("; base 100 = primeiro ano com valor diferente de zero"
                                                    if med.startswith("Índice") else ""))
            sr = data.series(D, list(dict.fromkeys([tid, REGIAO, AMZ, BRASIL])), IND)
            plot(charts.lines(sr, I, "indice" if med.startswith("Índice") else "valor", height=360), "ve_line")
        with g2:
            pares = snap("Estado", filt=False)
            if is_al:
                pares = pares[pares.al.fillna(False).astype(bool)]
            grupo_txt = "estados da Amazônia Legal" if is_al else "estados"
            theme.title(f"{sel} entre os {grupo_txt}", f"{charts.axis_label(I)} em {YEAR}")
            if pares.empty:
                st.info(f"Sem dado estadual de {charts.low(I.label)} em {YEAR}.")
            else:
                plot(charts.hbar(pares, I, len(pares), highlight=sel, height=max(300, 30 * len(pares) + 40)), "ve_rank")
        st.markdown("---")

        # ---- C. municípios do estado ------------------------------------------------------
        md = data.snapshot(D, "Município", IND, YEAR, ufs=[uf])
        theme.title(f"{I.label} nos municípios de {sel}",
                    f"{YEAR} · {len(md)} de {n_mun} municípios com dado · cor = faixa do município dentro do estado "
                    "(5 faixas com o mesmo nº de municípios)")
        if len(md) < 5:
            st.info(f"{I.label} não tem dado municipal suficiente para {sel} em {YEAR}"
                    + (" (indicador só tem dado estadual)." if md.empty else "."))
        else:
            mc, side = st.columns([2, 1])
            with mc:
                cores_m = ["Faixas (quintis)", "Contínua (log)" if I.log else "Contínua"]
                modo = st.radio("Escala de cores", cores_m, horizontal=True, key=state("w_ve_mode", cores_m[0], cores_m))
                plot(charts.choropleth(md, I, "Município", "faixas" if modo.startswith("Faixas") else "continua",
                                       **uf_view(cod_uf), height=520), "ve_map")
                if modo.startswith("Faixas"):
                    st.markdown(charts.legend_html(md, I), unsafe_allow_html=True)
            with side:
                s1, s2 = st.columns(2)
                s1.metric("Mediana", I.fmt(md.valor.median()))
                s2.metric("Média", I.fmt(md.valor.mean()))
                s1.metric("Máximo", I.fmt(md.valor.max()))
                s2.metric("Mínimo", I.fmt(md.valor.min()))
                if I.additive and md.valor.sum():
                    t5 = md.nlargest(5, "valor")
                    st.caption(f"Os 5 maiores municípios concentram **{fmt.pct(t5.valor.sum() / md.valor.sum() * 100)}** "
                               f"do total do estado.")
                acima = int((md.valor > md.valor.median()).sum())
                st.caption(f"{acima} municípios estão acima da mediana estadual.")
            b1, b2 = st.columns(2)
            with b1:
                theme.title(f"10 municípios com maior valor", f"{charts.axis_label(I)} em {YEAR}")
                plot(charts.hbar(md, I, 10, height=320), "ve_top")
            with b2:
                theme.title(f"10 municípios com menor valor", f"{charts.axis_label(I)} em {YEAR}")
                plot(charts.hbar(md, I, 10, ascending=True, height=320, color=theme.TEAL), "ve_bot")
        if I.kind == "moeda":
            st.markdown('<div class="note">Valores a preços correntes (nominais): comparações entre anos incluem '
                        'inflação.</div>', unsafe_allow_html=True)
        st.markdown("---")

        # ---- D. downloads -----------------------------------------------------------------
        theme.title(f"Baixar os dados de {sel}",
                    "Arquivos CSV (separador ;, decimal ,) com todos os indicadores e anos, na unidade mostrada no painel")
        slug = uf.lower()
        d1, d2, d3 = st.columns(3)
        d1.download_button("Tabela-resumo do estado", csv_bytes(resumo), f"resumo_{slug}.csv", "text/csv",
                           help="A tabela do topo desta página.", width="stretch")
        d2.download_button(f"Séries: {uf}, Região {reg_nome}, Amazônia Legal e Brasil",
                           csv_bytes(tabela_longa(AGG[AGG.tid.isin([tid, REGIAO, AMZ, BRASIL])])),
                           f"series_{slug}.csv", "text/csv", width="stretch",
                           help="Uma linha por território, indicador e ano.")
        d3.download_button(f"Municípios de {uf} ({n_mun})", csv_bytes(tabela_longa(mun_uf)),
                           f"municipios_{slug}.csv", "text/csv", width="stretch",
                           help="Uma linha por município, indicador e ano.")

# =========================================================================== #
# 3. MAPA TERRITORIAL
# =========================================================================== #
with T["Mapa Territorial"]:
    if T["Mapa Territorial"].open:
        barra_filtros()
        m1, m2, m3 = st.columns([1, 1, 2])
        lvl = m1.radio("Colorir o mapa por", ["Estado", "Município"], horizontal=True,
                       key=state("w_map_lvl", "Estado", ["Estado", "Município"]))
        cores = ["Faixas (quintis)", "Contínua (log)" if I.log else "Contínua"]
        mode_lbl = m2.radio("Escala de cores", cores, horizontal=True, key=state("w_map_mode", cores[0], cores),
                            help="Faixas: 5 grupos com o mesmo número de territórios, bom para ver posição relativa. "
                                 "Contínua: a cor acompanha o valor" + (" (em escala logarítmica)." if I.log else "."))
        mdf = snap(lvl)
        if len(mdf) < 5:
            st.warning("Poucos territórios com dado nesta combinação de filtros.")
        else:
            mc, side = st.columns([2.3, 1])
            with mc:
                theme.title(f"{I.label} por {lvl.lower()}", f"{YEAR} · {escopo(lvl, len(mdf))}")
                plot(charts.choropleth(mdf, I, lvl, "faixas" if mode_lbl.startswith("Faixas") else "continua",
                                       **map_view(lvl), height=640), "map_main")
                if mode_lbl.startswith("Faixas"):
                    st.markdown(charts.legend_html(mdf, I), unsafe_allow_html=True)
            with side:
                theme.title(f"Resumo dos {escopo(lvl)}", f"{charts.axis_label(I)} em {YEAR}")
                s1, s2 = st.columns(2)
                s1.metric("Mediana", I.fmt(mdf.valor.median()))
                s2.metric("Média", I.fmt(mdf.valor.mean()))
                s1.metric("Máximo", I.fmt(mdf.valor.max()))
                s2.metric("Mínimo", I.fmt(mdf.valor.min()))
                theme.title(f"10 {lvl.lower()}s com maior valor")
                plot(charts.hbar(mdf, I, 10, height=300), "map_top")
                theme.title(f"10 {lvl.lower()}s com menor valor")
                plot(charts.hbar(mdf, I, 10, ascending=True, height=300, color=theme.TEAL), "map_bot")
        if I.kind == "moeda":
            st.markdown('<div class="note">Valores a preços correntes (nominais): comparações entre anos incluem '
                        'inflação.</div>', unsafe_allow_html=True)

# =========================================================================== #
# 4. PERFIL DO TERRITÓRIO
# =========================================================================== #
with T["Perfil do Território"]:
    if T["Perfil do Território"].open:
        barra_filtros()
        p1, p2, p3 = st.columns([1, 1, 2])
        niveis = ["Município", "Estado", "Grande Região", "Amazônia Legal", "Brasil"]
        plvl = p1.selectbox("Tipo de território", niveis, key=state("w_pf_lvl", "Município", niveis))
        terr = data.territories(D, plvl)
        if plvl == "Município":
            puf = p2.selectbox("UF", D["ufs"], key=state("w_pf_uf", "PA" if "PA" in D["ufs"] else D["ufs"][0], D["ufs"]))
            terr = terr[terr.uf == puf]
        else:
            p2.selectbox("UF", ["—"], disabled=True, help="Usada só para escolher municípios.")
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

        rank_grp = {"Município": "municípios do Brasil", "Estado": "estados", "Grande Região": "Grandes Regiões"}
        theme.title(f"{sel}: todos os indicadores {ANO_TXT}",
                    (f"Posição entre os {rank_grp[plvl]} no mesmo ano e " if plvl in rank_grp else "")
                    + "variação do primeiro ano com dado até o ano mostrado no cartão"
                    + (". Se o território não tem dado no último ano do indicador, o cartão mostra o último dado "
                       "dele, sem posição, pois não seria comparável com os demais." if RECENTE else ""))
        for col, k in grid(D["indicators"]):
            ik = REG[k]
            ano = year_for(k)
            v = value_of(tid, k, ano)
            antigo = False
            if RECENTE and fmt.isna(v):  # sem dado no último ano do indicador: usa o último dado do território
                sk = data.series(D, [tid], k).dropna(subset=["valor"])
                if len(sk):
                    ano, v, antigo = int(sk.ano.iloc[-1]), float(sk.valor.iloc[-1]), True
            yr0, v0 = first_valid(tid, k, ano)
            peers = (snap(plvl, k, ano, filt=False)
                     if plvl in ("Município", "Estado", "Grande Região") and not antigo else None)
            rk = ""
            if peers is not None and len(peers) and tid in set(peers.tid) and not fmt.isna(v):
                pos = int((peers.valor > v).sum() + 1)
                empate = int(np.isclose(peers.valor, v).sum())
                if empate > 1 and empate / len(peers) > 0.01:  # empate que torna a posição pouco informativa
                    rk = f"empatado em {pos}º · {empate:,} de {len(peers):,} com o mesmo valor · ".replace(",", ".")
                else:
                    rk = f"{pos}º de {len(peers)} · "
            ref = f"{ano} (último dado do território; indicador vai até {year_for(k)})" if antigo else f"{ano}"
            if yr0 and yr0 < ano and v0 == 0:
                sub = f"{rk}{ref} · era zero em {yr0}"
            elif yr0 and yr0 < ano:
                sub = f"{rk}{ref} · {arrow(change(v, v0))} desde {yr0}"
            elif yr0:  # sem ponto anterior: a base inteira tem um ano só, ou só este território
                sub = f"{rk}{ref} · " + ("único ano com dado na base" if len(data.years_with_data(D, k)) == 1
                                         else "sem ano anterior para comparar")
            else:
                sub = ref
            with col:
                st.markdown(theme.kpi(ik.label, ik.fmt(v), sub, ik.icon), unsafe_allow_html=True)

        st.markdown("<div style='height:10px'></div>", unsafe_allow_html=True)
        g1, g2 = st.columns([1.4, 1])
        with g1:
            ref_txt = {"Município": "o estado, a Amazônia Legal e o Brasil", "Amazônia Legal": "o Brasil",
                       "Brasil": ""}.get(plvl, "a Amazônia Legal e o Brasil")
            theme.title(f"Evolução de {charts.low(I.label)}: {sel}" + (f" comparado com {ref_txt}" if ref_txt else ""),
                        "Índice: base 100 = primeiro ano com valor diferente de zero")
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
            nome_curto = sel.split(" (")[0]
            theme.title(f"Onde {nome_curto} fica entre os {rank_grp.get(plvl, 'pares')}",
                        f"Quantos territórios têm cada valor de {charts.low(I.label)} em {YEAR}; "
                        f"a linha laranja é {nome_curto}")
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
                fig.update_layout(height=300, bargap=.05, yaxis_title=f"nº de {rank_grp.get(plvl, 'territórios')}",
                                  xaxis_title=charts.axis_label(I) + (" · escala log" if I.log else ""))
                fig.update_xaxes(tickvals=[float(tf(x)) for x in vals], ticktext=txt)
                plot(fig, "perfil_hist")
                st.markdown(f"**{sel}** está acima de **{fmt.num(pct, 0)}%** dos {len(peers)} "
                            f"{plvl.lower()}s com dado em {YEAR}" + (" (escala logarítmica)." if I.log else "."))
            else:
                st.info("Sem grupo de pares para esta granularidade.")

        theme.title(f"{sel}: tabela com todos os indicadores, ano a ano")
        wide = (L[(L.tid == tid)].pivot_table(index="ano", columns="ind", values="valor", observed=True)
                .reindex(columns=D["indicators"]))
        tabela = wide.apply(lambda s: s.map(REG[s.name].fmt) if s.name in REG else s)
        st.dataframe(tabela.rename(columns={k: charts.axis_label(REG[k]) for k in tabela.columns}),
                     width="stretch")
        st.caption("— indica ano sem dado na base de origem.")

# =========================================================================== #
# 5. SÉRIES TEMPORAIS
# =========================================================================== #
with T["Séries Temporais"]:
    if T["Séries Temporais"].open:
        barra_filtros()
        st.markdown("Escolha os territórios (de qualquer nível) e compare como o indicador evoluiu em cada um.")
        q1, q2 = st.columns([1, 2.2])
        with q1:
            use_br = st.checkbox("Brasil", key=state("w_ts_br", True))
            use_al = st.checkbox("Amazônia Legal", key=state("w_ts_al", True))
            medidas = ["Valor", "Índice (base 100)", "Variação % a.a."]
            mode_lbl = st.radio("Medida", medidas, key=state("w_ts_mode", "Valor", medidas),
                                help="Valor: o número publicado. Índice: crescimento relativo (base 100 no início), "
                                     "para comparar territórios de tamanhos diferentes. "
                                     "Variação: % de um ano para o outro.")
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
            titulo = {"valor": charts.axis_label(I), "indice": f"Crescimento de {charts.low(I.label)} (índice)",
                      "var": f"Variação anual de {charts.low(I.label)}"}[mode]
            theme.title(f"{titulo} nos {sr.tid.nunique()} territórios escolhidos",
                        "Linhas ligam os anos com dado; anos sem dado ficam sem marcador"
                        + ("; base 100 = primeiro ano com valor diferente de zero" if mode == "indice" else ""))
            plot(charts.lines(sr, I, mode, log), "ts_main")
            if sr.valor.isna().any():
                miss = sorted(sr[sr.valor.isna()].ano.unique())
                st.caption("Anos sem dado nas bases para este indicador: " + ", ".join(map(str, miss)) + ".")

            st.markdown("---")
            h1, h2 = st.columns([1, 1.25])
            with h1:
                theme.title(f"Crescimento médio por ano de {charts.low(I.label)}",
                            "Taxa composta (TCMA), do primeiro ao último ano com dado de cada território; "
                            "cor = nível do território")
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
                    customdata=[f"{fmt.num(v, 1)}% ao ano ({a}–{b})" for v, a, b in zip(cg.tcma, cg.de, cg.ate)],
                    hovertemplate="%{y}<br>%{customdata}<extra></extra>"))
                # rótulos sempre à direita do zero, para não cobrir o nome quando a barra é negativa
                fig.add_trace(go.Scatter(
                    x=cg.tcma.clip(lower=0), y=cg.label, mode="text", textposition="middle right", hoverinfo="skip",
                    text=[f" {fmt.num(v, 1)}% ({a}–{b})" for v, a, b in zip(cg.tcma, cg.de, cg.ate)],
                    textfont=dict(size=11), showlegend=False, cliponaxis=False))
                lo, hi = min(0.0, cg.tcma.min()), max(0.0, cg.tcma.max())
                fig.update_layout(height=max(260, 34 * len(cg) + 60), margin=dict(r=10), showlegend=False)
                fig.update_xaxes(ticksuffix="%", title="% ao ano",
                                 range=[lo - (hi - lo or 1) * 0.05 if lo < 0 else 0, hi + (hi - lo or 1) * 0.6])
                plot(fig, "ts_cagr")
            with h2:
                theme.title(f"Variação de {charts.low(I.label)} a cada ano, por território",
                            "% ao ano em relação ao ano anterior com dado · verde: cresceu · vermelho: caiu")
                plot(charts.growth_heatmap(sr), "ts_heat")

            st.markdown("---")
            theme.title(f"{sr.label.iloc[0]}: todos os indicadores no mesmo gráfico",
                        "Primeiro território da seleção · índice: base 100 = primeiro ano com valor diferente de zero · cada linha é um indicador")
            first = sr.tid.iloc[0]
            fig = go.Figure()
            for i, k in enumerate(D["indicators"]):
                colr = theme.COLORWAY[i % len(theme.COLORWAY)]
                t = charts.transform(data.series(D, [first], k), "indice")
                if len(t):
                    fig.add_trace(go.Scatter(x=t.ano, y=t.y, name=REG[k].label, mode="lines+markers", connectgaps=True,
                                             line=dict(color=colr, width=2.6), marker=dict(size=7),
                                             hovertemplate=REG[k].label + " %{x}: <b>%{y:.1f}</b><extra></extra>"))
            fig.update_layout(height=340, yaxis_title="Índice (base 100)", legend_title_text="Indicador:")
            fig.update_xaxes(dtick=1, tickformat="d")
            plot(fig, "ts_multi")
            with st.expander("Dados da seleção"):
                out = sr.assign(valor_fmt=sr.valor.map(I.fmt))
                st.dataframe(out.rename(columns={"tid": "id", "label": "território", "nivel": "nível", "valor": "valor",
                                                 "valor_fmt": "valor (formatado)"}), width="stretch", hide_index=True)
                st.download_button("Baixar CSV", sr.to_csv(index=False, sep=";", decimal=",").encode("utf-8-sig"),
                                   "series_selecionadas.csv", "text/csv")

# =========================================================================== #
# 6. RANKING
# =========================================================================== #
with T["Ranking"]:
    if T["Ranking"].open:
        barra_filtros()
        r1, r2, r3 = st.columns([1, 1.4, 1])
        rniveis = ["Município", "Estado", "Grande Região"]
        rlvl = r1.radio("Ordenar", rniveis, horizontal=True, key=state("w_rk_lvl", "Município", rniveis),
                        format_func=lambda x: {"Município": "Municípios", "Estado": "Estados",
                                               "Grande Região": "Grandes Regiões"}[x])
        busca = r2.text_input("Buscar na tabela", placeholder="ex.: Belém", key=state("w_rk_busca", ""),
                              help="Só filtra as linhas da tabela; as posições continuam as do ranking completo.")
        topn = r3.slider("Quantos no gráfico de barras", 5, 40, key=state("w_rk_topn", 15))
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
                f"{I.label}": view.valor.map(I.fmt), "Comparado ao 1º": view.rel,
                "Variação (%)": view["var"].round(1), "Participação (%)": view.share.round(2),
                "Faixa": view.faixa})
            cfg = {f"{I.label}": st.column_config.TextColumn(help=f"{I.unit}, em {YEAR}"),
                   "Comparado ao 1º": st.column_config.ProgressColumn(
                       "Comparado ao 1º", min_value=0, max_value=100, format="%.0f%%",
                       help="Valor do território como % do valor do 1º colocado."),
                   "Variação (%)": st.column_config.NumberColumn(
                       format="%.1f%%",
                       help=f"Do primeiro ano com dado até {YEAR}; vazio quando o valor inicial era zero."),
                   "Participação (%)": st.column_config.NumberColumn(
                       format="%.2f%%", help="Parte do total somado de todos os territórios do ranking."),
                   "Faixa": st.column_config.TextColumn(
                       help="Faixa 1 = 20% com menores valores … Faixa 5 = 20% com maiores valores.")}
            if not I.additive:
                tbl = tbl.drop(columns=["Participação (%)"])
            t1, t2 = st.columns([1.5, 1])
            with t1:
                theme.title(f"Ranking de {charts.low(I.label)}: {escopo(rlvl)}",
                            f"{YEAR} · {len(rk):,} no ranking".replace(",", ".")
                            + (f" · {len(view)} encontrados para '{busca}'" if busca else ""))
                st.dataframe(tbl, width="stretch", hide_index=True, height=620, column_config=cfg)
                st.download_button("Baixar ranking (CSV)", rk[["pos", "label", "uf", "valor", "var", "share", "faixa"]]
                                   .rename(columns={"pos": "posicao", "label": "territorio", "var": "variacao_pct",
                                                    "share": "participacao_pct"})
                                   .to_csv(index=False, sep=";", decimal=",").encode("utf-8-sig"),
                                   f"ranking_{rlvl}_{YEAR}.csv", "text/csv")
            with t2:
                theme.title(f"Os {topn} maiores", f"{charts.axis_label(I)} em {YEAR}")
                plot(charts.hbar(rk, I, topn, height=max(300, 26 * topn + 40)), "rk_bar")

# =========================================================================== #
# 7. COMPARAÇÕES
# =========================================================================== #
with T["Comparações"]:
    if T["Comparações"].open:
        barra_filtros()
        # ---- A. entre granularidades -------------------------------------------------
        theme.title(f"{I.label} em {YEAR}: Brasil, Amazônia Legal, Grandes Regiões e estados lado a lado",
                    f"Cor = nível do território. Só os estados seguem os filtros ({escopo('Estado')}); "
                    "Brasil, Amazônia Legal e Grandes Regiões aparecem sempre.")
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
        theme.title("Relação entre dois indicadores",
                    "Os dois indicadores são escolhidos aqui (não usam o indicador da barra lateral); "
                    "ano e territórios seguem os filtros.")
        b1, b2, b3 = st.columns(3)
        sc_lvl = b1.radio("Cada ponto é um", ["Município", "Estado"], horizontal=True,
                          key=state("w_sc_lvl", "Município", ["Município", "Estado"]))
        xk = b2.selectbox("Indicador no eixo horizontal", D["indicators"], format_func=lambda k: REG[k].label,
                          key=state("w_sc_x", D["indicators"][0], D["indicators"]))
        yk = b3.selectbox("Indicador no eixo vertical", D["indicators"], format_func=lambda k: REG[k].label,
                          key=state("w_sc_y", D["indicators"][min(2, len(D["indicators"]) - 1)], D["indicators"]))
        if RECENTE:  # ano mais recente em que os dois indicadores têm dado, para comparar o mesmo ano
            comuns = set(data.years_with_data(D, xk)) & set(data.years_with_data(D, yk))
            ysc = max(comuns) if comuns else None
        else:
            ysc = YEAR
        sx, sy = (snap(sc_lvl, xk, ysc), snap(sc_lvl, yk, ysc)) if ysc else (snap(sc_lvl, xk, 0), snap(sc_lvl, yk, 0))
        sd = sx[["cod", "label", "uf", "valor"]].rename(columns={"valor": "x"}).merge(
            sy[["cod", "valor"]].rename(columns={"valor": "y"}), on="cod")
        if D["pop_col"]:
            ypop = max([y for y in data.years_with_data(D, D["pop_col"]) if y <= (ysc or YEAR)], default=ysc or YEAR)
            sd = sd.merge(snap(sc_lvl, D["pop_col"], ypop)[["cod", "valor"]].rename(columns={"valor": "pop"}), on="cod", how="left")
        if len(sd) < 6:
            st.info("Poucos pontos com os dois indicadores"
                    + (" no mesmo ano" if RECENTE else f" em {YEAR}") + ". Tente outro par de indicadores"
                    + ("" if RECENTE else " ou outro ano") + ".")
        else:
            pode_log = bool(REG[xk].log and REG[yk].log and (sd.x > 0).all() and (sd.y > 0).all())
            lsc = st.checkbox("Escala logarítmica nos dois eixos", disabled=not pode_log,
                              key=state("w_sc_log", pode_log),
                              help="Indicada quando os valores são muito assimétricos (poucos territórios muito "
                                   "maiores que a maioria). Só está disponível se os dois indicadores forem positivos.")
            lsc = lsc and pode_log
            plot(charts.scatter(sd, REG[xk], REG[yk], log=lsc,
                                size_col="pop" if "pop" in sd else None), "sc")
            rho = sd.x.rank().corr(sd.y.rank())  # Spearman = Pearson dos postos
            st.caption(f"{escopo(sc_lvl, len(sd))} em {ysc}"
                       + (" (ano mais recente com dado nos dois indicadores)" if RECENTE else "")
                       + f" · cor = UF · tamanho do ponto = população · linha tracejada = tendência linear"
                       + (" ajustada nos logaritmos" if lsc else "") + " (r de Pearson, no gráfico). "
                       f"Correlação de postos de Spearman = {fmt.num(rho, 2)}: mede se quem tem mais de um indicador "
                       "tende a ter mais (ou menos) do outro, sem ser distorcida por valores extremos. "
                       "Perto de 1 ou −1: relação forte; perto de 0: fraca. Correlação não prova causa.")
        st.markdown("---")

        # ---- C. distribuição por UF ---------------------------------------------------
        mm = snap("Município")
        theme.title(f"Como {charts.low(I.label)} varia entre os municípios de cada UF",
                    f"{YEAR} · {escopo('Município', len(mm))} · a caixa vai do 1º ao 3º quartil (metade dos "
                    "municípios), a linha no meio é a mediana e os pontos soltos são municípios fora do padrão")
        if len(mm) > 10:
            plot(charts.box_by_uf(mm, I, log=I.log), "box")
        st.markdown("---")

        # ---- D. face a face -----------------------------------------------------------
        theme.title("Face a face: dois territórios em todos os indicadores",
                    f"Escolhidos aqui, de qualquer nível; não seguem os filtros de território. "
                    + ("Cada indicador no seu ano mais recente (coluna Ano)." if RECENTE else f"Valores de {YEAR}.")
                    + " A ÷ B é a razão entre os valores de A e de B.",
                    fixo=True)
        fa, fb = st.columns(2)
        picks = []
        for colx, name, defl, defu in ((fa, "A", "Estado", "Pará"), (fb, "B", "Estado", "Amazonas")):
            with colx:
                lv = st.selectbox(f"Tipo do território {name}", LEVELS[::-1], key=state(f"w_ff_l{name}", defl, LEVELS[::-1]))
                tt = data.territories(D, lv)
                opts = tt.label.tolist()
                lab = st.selectbox(f"Território {name}", opts,
                                   key=state(f"w_ff_t{name}", defu if defu in opts else opts[0], opts))
                picks.append((lab, tt[tt.label == lab].tid.iloc[0]))
        rows = []
        for k in D["indicators"]:
            va, vb = value_of(picks[0][1], k), value_of(picks[1][1], k)
            rows.append({"Indicador": charts.axis_label(REG[k]), "Ano": str(year_for(k)), picks[0][0]: REG[k].fmt(va),
                         picks[1][0]: REG[k].fmt(vb),
                         "A ÷ B": fmt.num(va / vb, 2) + "×" if vb and not fmt.isna(va) and not fmt.isna(vb) else "—"})
        st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)
        plot(charts.lines(data.series(D, [p[1] for p in picks], IND), I, "indice", height=330), "ff_line")
        st.caption(f"Evolução de {charts.low(I.label)} nos dois territórios · índice: base 100 = primeiro ano com valor diferente de zero.")

# =========================================================================== #
# 8. SOBRE
# =========================================================================== #
with T["Sobre o Painel"]:
    if T["Sobre o Painel"].open:
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
