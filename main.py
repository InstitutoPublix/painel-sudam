"""PRDA · Diagnóstico Quantitativo da Amazônia Legal — painel Streamlit.

Executar:  streamlit run main.py
"""
from __future__ import annotations

import html
import re
import unicodedata

from functools import partial

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from src import charts, data, fmt, theme
from src.data import AGRUPAMENTOS, AGRUPAMENTOS_SN, LEVELS, ORDEM_CLASSES, PARTE_AL, PORTES

ICON = data.ASSETS / "logos" / "emblema.png"
st.set_page_config(page_title="PRDA · Diagnóstico da Amazônia Legal",
                   page_icon=str(ICON) if ICON.exists() else "🌿", layout="wide",
                   initial_sidebar_state="expanded")
theme.inject()
D = data.load()
L, REG = D["long"], D["registry"]
NOME_UF = L[L.nivel == "Estado"][["uf", "nome"]].drop_duplicates().astype(str).set_index("uf").nome.to_dict()
PARCIAL = D["al_parcial"]  # estados só em parte na Amazônia Legal: {UF: (municípios na AL, total)}


PARTE_OPCOES = ["Parte na Amazônia Legal", "Estado inteiro"]


def modo_parcial(parte: bool, ind: str) -> str:
    """Como os estados só em parte na Amazônia Legal aparecem: 'parcela' (valor da parcela na região), 'sem_parcela'
    (queria a parcela, mas o indicador só existe para o estado inteiro) ou 'inteiro' (valor do estado inteiro).
    Numa base sem o cálculo da parcela (gerada antes dele), vale sempre o estado inteiro."""
    if not parte or not D["al_parte_ind"]:
        return "inteiro"
    return "parcela" if ind in D["al_parte_ind"] else "sem_parcela"


def nota_parcial(modo: str = "inteiro") -> str:
    """Aviso sobre estados que fazem parte da Amazônia Legal só em parte (hoje, o Maranhão). Sempre diz qual valor
    está sendo usado: o da parte que fica na região ou o do estado inteiro."""
    if not PARCIAL:
        return ""
    texto = {
        "parcela": "{n}: só a parte do estado que está na Amazônia Legal ({a} de {t} municípios)",
        "sem_parcela": "{n}: valor do estado inteiro, pois este indicador não existe só para a parte na Amazônia Legal. "
                       "No total da Amazônia Legal, entram só {a} de {t} municípios",
        "inteiro": "{n}: valor do estado inteiro. No total da Amazônia Legal, entram só {a} de {t} municípios",
    }[modo]
    return "; ".join(texto.format(n=NOME_UF[u], a=a, t=t) for u, (a, t) in PARCIAL.items()) + "."


def nota_al() -> str:
    """Aviso para as telas que mostram o total da Amazônia Legal: estados só em parte entram só com a parte da região."""
    if not PARCIAL:
        return ""
    return ("Amazônia Legal: considera só os municípios da região. "
            + "; ".join(f"{NOME_UF[u]} entra com {a} de {t} municípios" for u, (a, t) in PARCIAL.items()) + ".")
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
ABAS = ["Visão Geral", "Mapa e Ranking", "Perfil do Território", "Séries Temporais", "Comparações", "Sobre o Painel"]
TERRIT = {"recorte", "uf", "porte", "grupos"}
FILTROS = {"Visão Geral": {"ind", "ano"} | TERRIT, "Mapa e Ranking": {"ind", "ano"} | TERRIT,
           "Perfil do Território": {"ind", "ano"}, "Séries Temporais": {"ind"},
           "Comparações": {"ind", "ano"} | TERRIT, "Sobre o Painel": set()}
NOTAS = {"Perfil do Território": "O território é escolhido na própria página; o indicador e o ano valem nas seções Evolução, "
                      "Posição e Municípios do estado.",
         "Séries Temporais": "Os territórios são escolhidos na própria página; as séries mostram todos os anos.",
         "Sobre o Painel": "Esta página não usa filtros."}

theme.header()
tabs = st.tabs(ABAS, key="aba", on_change="rerun")
T = dict(zip(ABAS, tabs))
ABA = next((a for a, t in T.items() if t.open), ABAS[0])
if ABA != "Perfil do Território":  # o botão "Voltar" da aba Perfil do Território só vale logo após o clique no ranking
    st.session_state.pop("tr_origem", None)
show = set(FILTROS[ABA])
# a escala escolhida dentro da aba define quais filtros territoriais fazem efeito
escala = {"Mapa e Ranking": st.session_state.get("w_mr_lvl", "Município")}.get(ABA)
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
                   + f"  \nAmazônia Legal: {I.agg_note.lower()}."
                   + (" " + " ".join(f"{NOME_UF[u]} entra só com a parte que está na região." for u in PARCIAL)))
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
                             "Brasil inteiro: todos os estados e municípios do país. " + nota_parcial("parcela")
                             + (" Com Brasil inteiro, esse estado aparece com o valor do estado todo." if PARCIAL else ""))
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
                if col == "idhm":
                    pool = [c for c in ORDEM_CLASSES if c in pool]
                k = state(f"w_g_{col}", [], pool)
                sel = st.multiselect(nome, pool, placeholder="Todos", key=k)
                if sel:
                    GRUPOS[col] = sel
            for col, nome in AGRUPAMENTOS_SN.items():  # marcado: só esses municípios; desmarcado: todos
                rotulo = {"fronteira": "Só cidades de fronteira", "sede_imediata": "Só sedes de região imediata"}.get(
                    col, f"Só: {nome.lower()}")
                if st.checkbox(rotulo, key=state(f"w_g2_{col}", False)):
                    GRUPOS[col] = [True]
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


FILTROS_LIMPAVEIS = ("w_recorte", "w_ufs", "w_porte", "w_ano_modo", "w_ano", "w_grupos_aberto")


def limpar_filtros():
    """Volta os filtros da barra lateral ao padrão: abrangência, UF, porte, agrupamentos e ano. O eixo e o indicador
    escolhidos ficam, para não perder o que está sendo analisado. Roda antes da nova execução da página."""
    for k in list(st.session_state):
        if k in FILTROS_LIMPAVEIS or str(k).startswith(("w_g_", "w_g2_")):
            del st.session_state[k]


def filtros_alterados() -> bool:
    """Há algum filtro fora do padrão na barra lateral (mesmo os que a aba aberta não usa)?"""
    s = st.session_state
    return bool(s.get("w_recorte", "Amazônia Legal") != "Amazônia Legal" or s.get("w_ufs") or s.get("w_porte")
                or s.get("w_ano_modo", MODOS_ANO[0]) != MODOS_ANO[0]
                or any(v for k, v in s.items() if str(k).startswith(("w_g_", "w_g2_"))))


def barra_filtros():
    """Resumo, no topo da aba, dos filtros da barra lateral que estão valendo nela, com o botão para limpá-los."""
    if not show:
        return
    itens = [f"Indicador: <b>{I.label}</b>"]
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
    if PARCIAL and ABA != "Perfil do Território":  # a aba Perfil do Território traz a sua própria nota, conforme a escolha feita nela
        itens.append("◐ " + nota_parcial(modo_parcial(AL_ONLY and "recorte" in show, IND)))
    barra = ('<div class="fbar"><span class="t">Filtros aplicados</span>' + "".join(f"<span>{x}</span>" for x in itens)
             + "</div>")
    if show & (TERRIT | {"ano"}):  # botão ao lado do resumo: é ali que o usuário vê o que está aplicado
        c_barra, c_botao = st.columns([5.2, 1], vertical_alignment="center")
        c_barra.markdown(barra, unsafe_allow_html=True)
        c_botao.button("Limpar filtros", on_click=limpar_filtros, key="limpar_filtros", disabled=not filtros_alterados(),
                       width="stretch", help="Volta abrangência, UF, porte, agrupamentos e ano ao padrão. O eixo e o "
                                             "indicador escolhidos ficam.")
    else:
        st.markdown(barra, unsafe_allow_html=True)
    if "ind" in show:  # legenda do indicador: unidade, fonte e fórmula, como constam na planilha
        m = D["meta"].get(IND, {})
        esc = lambda t: html.escape(str(t).strip())  # noqa: E731
        leg = [f"<span><b>Unidade:</b> {esc(I.unit)}</span>"]
        if m.get("source"):
            leg.append(f"<span><b>Fonte:</b> {esc(m['source'])}</span>")
        if m.get("formula"):
            fx = str(m["formula"]).strip()
            if len(fx) > 220:  # fórmulas muito longas: o começo aqui, o texto inteiro na ficha do Sobre o Painel
                fx = fx[:220].rsplit(" ", 1)[0] + "… (texto completo em Sobre o Painel)"
            leg.append(f"<span><b>Fórmula:</b> {esc(fx)}</span>")
        st.markdown('<div class="fbar leg"><span class="t">Sobre o indicador</span>' + "".join(leg) + "</div>",
                    unsafe_allow_html=True)


def snap(level: str, ind: str = IND, year: int | None = None, filt: bool = True, parte: bool | None = None) -> pd.DataFrame:
    """Territórios de um nível com os filtros da barra lateral (filt=False: sem eles). `parte`: usa, nos estados só em
    parte na Amazônia Legal, o valor da parcela na região; por padrão, só quando a abrangência é Amazônia Legal."""
    year = year_for(ind) if year is None else year
    parte = (AL_ONLY and filt) if parte is None else parte
    if not filt:
        return data.snapshot(D, level, ind, year, parte_al=parte)
    return data.snapshot(D, level, ind, year, al_only=AL_ONLY, ufs=UFS or None, portes=PORTE or None,
                         grupos=GRUPOS or None, parte_al=parte)


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


def change(v: float, v0: float, ik=None) -> float:
    """Diferença de v0 até v na medida do indicador: p.p. para proporções, pontos para índices, % nos demais
    (indefinida quando falta dado ou, na variação %, quando o valor inicial é zero)."""
    return (ik or I).diff(v, v0)


SIT_CSS = {1: "up", -1: "down", 0: "neutro"}  # verde = melhora, vermelho = piora, sem cor = sem polaridade


def arrow(v: float, ik=None) -> str:
    """Seta com a direção da mudança e cor da situação, conforme a polaridade do indicador."""
    ik = ik or I
    if fmt.isna(v):
        return "—"
    r = round(v, ik.diff_decimals)
    seta = "▲" if r > 0 else "▼" if r < 0 else "="
    return f'<span class="{SIT_CSS[ik.situacao(v)]}">{seta} {ik.fmt_diff(v)}</span>'


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
        dif_br = I.diff(v_al, v_br)  # proporções e índices: diferença em p.p. ou pontos

        theme.title(f"{I.label} em {YEAR}: Brasil, Amazônia Legal e municípios extremos",
                    f"Os quatro primeiros cartões são totais fixos; maior e menor município saem dos "
                    f"{escopo('Município', len(muni))}.")
        c = st.columns(6)
        sem_br = fmt.isna(v_br)  # alguns indicadores não têm total nacional
        c[0].markdown(theme.kpi("Brasil", I.fmt(v_br), "sem dado nacional para este indicador" if sem_br
                                else f"{I.label} · {YEAR}", "🇧🇷"), unsafe_allow_html=True)
        c[1].markdown(theme.kpi("Amazônia Legal", I.fmt(v_al), f"{I.label} · {YEAR}", "AL", "hi"), unsafe_allow_html=True)
        if not I.additive and I.delta != "pct":
            c[2].markdown(theme.kpi("Diferença para o Brasil", arrow(dif_br),
                                    "sem total nacional para comparar" if sem_br
                                    else f"Amazônia Legal menos Brasil, em {I.delta_unit}", "Δ"), unsafe_allow_html=True)
        else:
            c[2].markdown(theme.kpi("Participação no Brasil" if I.additive else "Relação com o Brasil",
                                    fmt.pct(share if I.additive else ratio),
                                    "sem total nacional para comparar" if sem_br
                                    else "da Amazônia Legal no total nacional" if I.additive else "AL ÷ Brasil", "%"),
                          unsafe_allow_html=True)
        c[3].markdown(theme.kpi("Variação desde " + (str(y0) if y0 else "—"), arrow(var_al),
                                f"Amazônia Legal, de {y0} a {YEAR}" if y0 else "Amazônia Legal", "Δ"),
                      unsafe_allow_html=True)
        if len(muni):
            top, bot = muni.loc[muni.valor.idxmax()], muni.loc[muni.valor.idxmin()]
            # posição entre todos os municípios da abrangência (Amazônia Legal ou Brasil), mesmo com UF, porte ou
            # agrupamentos filtrados: 1º = maior valor
            uni = data.snapshot(D, "Município", IND, year_for(IND), al_only=AL_ONLY)
            onde = "da Amazônia Legal" if AL_ONLY else "do Brasil"

            def posicao(v: float) -> str:
                p, emp = data.position(uni.valor, v, 0)
                return f"{'=' if emp > 1 else ''}{p}º entre os {len(uni):,} municípios {onde}".replace(",", ".")

            c[4].markdown(theme.kpi("Maior município", I.fmt(top.valor), f"{top.label} · {posicao(top.valor)}", "▲", "hi"),
                          unsafe_allow_html=True)
            c[5].markdown(theme.kpi("Menor município", I.fmt(bot.valor), f"{bot.label} · {posicao(bot.valor)}", "▼", "lo"),
                          unsafe_allow_html=True)
            n0 = int((muni.valor == 0).sum())
            if 0 < n0 <= .05 * len(muni):  # zero em muitos municípios é padrão do indicador (ex.: sim/não), não lacuna
                st.caption(f"⚠ {n0:,} município(s) com valor zero entre os {len(muni):,}".replace(",", ".")
                           + ". Pode ser ausência de registro e não valor real; confira na fonte antes de interpretar.")
        if PARCIAL:
            st.caption(nota_al())
        st.markdown("<div style='height:14px'></div>", unsafe_allow_html=True)

        if muni.empty:
            st.warning("Sem municípios com dado para os filtros selecionados.")
        else:
            a, b, c3 = st.columns([1.15, 1, 1])
            with a:
                st_df = snap("Estado")
                theme.title(f"{I.label} por estado", f"{YEAR} · {escopo('Estado', len(st_df))} · "
                            "cor = faixa do estado (grupos de tamanho parecido, do menor ao maior valor)")
                if len(st_df) >= 5:
                    plot(charts.choropleth(st_df, I, "Estado", **map_view("Estado"), height=370,
                                           al_parcial=tuple(PARCIAL)), "ov_map")
                    st.markdown(charts.legend_html(st_df, I), unsafe_allow_html=True)
                    if PARCIAL:
                        st.caption("◐ " + nota_parcial(modo_parcial(AL_ONLY, IND)))
                else:
                    st.info(f"O mapa por estado divide os estados em faixas e precisa de pelo menos 5 estados; "
                            f"o filtro atual deixa {len(st_df)}. Para ver os municípios desses estados no mapa, "
                            "use a aba Mapa e Ranking.")
            with b:
                theme.title(f"Distribuição dos municípios por {charts.low(I.label)}",
                            f"{YEAR} · {escopo('Município', len(muni))} · cada barra conta os municípios de um "
                            "intervalo de valores; tracejado = mediana" + ("" if I.additive or sem_br else " e Brasil"))
                plot(charts.histogram(muni, I, I.log, None if I.additive or sem_br else ("Brasil", v_br), height=420), "ov_hist")
            with c3:
                theme.title(f"5 municípios com maior valor de {charts.low(I.label)}",
                            f"{YEAR} · entre os {escopo('Município', len(muni))}")
                t5 = muni.nlargest(5, "valor")
                plot(charts.hbar(t5, I, 5, height=360), "ov_top5")
                tot = muni.valor.sum() if I.additive else None
                if tot:
                    st.caption(f"Os 5 maiores concentram **{fmt.pct(t5.valor.sum() / tot * 100)}** do total dos "
                               f"{len(muni):,} municípios filtrados.".replace(",", "."))

            st.markdown("---")
            left, right = st.columns([1.3, 1])
            with left:
                regs = data.territories(D, "Grande Região")
                sr = data.series(D, [BRASIL, AMZ, *regs.tid], IND)
                tem = set(sr.loc[sr.valor.notna(), "tid"])  # só o que existe para este indicador
                nome_de = {BRASIL: "Brasil", AMZ: "Amazônia Legal", **dict(zip(regs.tid, regs.label))}
                opcoes = [nome_de[t] for t in (BRASIL, AMZ, *regs.tid) if t in tem]
                padrao = [n for n in ("Brasil", "Amazônia Legal") if n in opcoes]
                # chips clicáveis: Brasil e Amazônia Legal já vêm marcados; as Grandes Regiões entram com um clique.
                # Quando as opções mudam (outro indicador), mantém o que ainda existe ou volta ao padrão.
                if st.session_state.get("w_vg_opcoes") != opcoes:
                    st.session_state["w_vg_recortes"] = [x for x in st.session_state.get("w_vg_recortes", padrao)
                                                         if x in opcoes] or padrao
                    st.session_state["w_vg_opcoes"] = opcoes
                escolha = st.pills("Clique para incluir ou tirar recortes do gráfico", opcoes, selection_mode="multi",
                                   key="w_vg_recortes") if opcoes else []
                quem = ("sem série" if not opcoes else "nenhum recorte escolhido" if not escolha
                        else escolha[0] if len(escolha) == 1 else ", ".join(escolha[:-1]) + " e " + escolha[-1])
                theme.title(f"Evolução de {charts.low(I.label)}: {quem}",
                            "Índice: base 100 = primeiro ano com valor diferente de zero. Mostra quem cresceu mais, não o tamanho.",
                            fixo=True)
                if not escolha:
                    st.info("Escolha ao menos um recorte acima para ver a evolução.")
                else:
                    sr_v = sr[sr.tid.map(nome_de).isin(escolha)]
                    plot(charts.lines(sr_v, I, "indice", height=360,
                                      # os dois recortes principais em verdes bem distintos; as regiões, em outras cores
                                      cores={"Amazônia Legal": theme.INK, "Brasil": "#6CC24A",
                                             **{n: c for n, c in zip(regs.label, [theme.ORANGE, theme.BLUE, "#D49A12",
                                                                                   theme.BROWN, "#8E9A93"])}},
                                      tracejado=("Brasil",), grossas=("Amazônia Legal", "Brasil")), "ov_line")
            with right:
                if len(muni) > 10 and muni.uf.nunique() > 1:
                    por_pct = charts.tipico_por_uf(muni) == "media"
                    theme.title(f"{I.label}: município típico de cada UF" if not por_pct
                                else f"{I.label}: % dos municípios de cada UF",
                                f"{YEAR} · " + ("percentual dos municípios da UF com o item" if por_pct else
                                                "valor do município do meio em cada UF (metade tem mais, metade tem menos)")
                                + " · passe o mouse para ver o maior e o menor")
                    plot(charts.bars_by_uf(muni, I), "ov_uf")
                else:  # poucos municípios ou uma só UF: a comparação entre UFs perde o sentido
                    st_df = snap("Estado")
                    theme.title(f"{I.label} por estado, do maior para o menor",
                                f"{YEAR} · " + (f"15 maiores entre os {escopo('Estado', len(st_df))}" if len(st_df) > 15
                                                else escopo("Estado", len(st_df))))
                    plot(charts.hbar(st_df, I, 15, height=360), "ov_states")

        st.markdown("---")
        theme.title("Todos os indicadores na Amazônia Legal",
                    "Valor no último ano com dado de cada indicador e a evolução desde o primeiro ano", fixo=True)
        for eixo_nome in eixos:
            ks = [k for k in D["indicators"] if REG[k].axis == eixo_nome]
            with st.expander(f"{eixo_nome} · {len(ks)} indicador" + ("es" if len(ks) != 1 else ""),
                             expanded=eixo_nome == REG[IND].axis):
                for col, k in grid(ks):
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
# 2. TERRITÓRIO: funções de apoio
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


# =========================================================================== #
# 2. TERRITÓRIO: aba
# =========================================================================== #
@st.cache_data(show_spinner="Montando o comparativo…", max_entries=64)
def comparativo(tid: str, plvl: str, uf: str | None, ref_tids: tuple, versao: str, parte: bool = False):
    """Todos os indicadores de um território no último ano com dado dele, ao lado das referências (nível acima,
    Amazônia Legal, Brasil) e da posição entre os pares. Devolve a tabela e a cor da última coluna.
    parte: num estado só em parte na Amazônia Legal, usa o valor da parcela na região (os indicadores que só existem
    para o estado inteiro mantêm esse valor e ganham a marca 'estado inteiro')."""
    nomes_ref = {t: n for n, t in ref_tids}
    comp_tid = AMZ if AMZ in nomes_ref else (ref_tids[0][1] if ref_tids else None)
    comp_nome = nomes_ref.get(comp_tid, "")
    col_comp = f"{plvl} × {comp_nome}" if comp_tid else ""
    rows, cores = [], []
    for k in D["indicators"]:
        ik = REG[k]
        na_parcela = parte and k in D["al_parte_ind"]
        s = data.series(D, [f"{PARTE_AL}:{tid.split(':')[1]}" if na_parcela else tid], k).dropna(subset=["valor"])
        row = {"Indicador": charts.axis_label(ik)}
        if s.empty:
            rows.append(row | {"Ano": "—"})
            cores.append("")
            continue
        y, v = int(s.ano.iloc[-1]), float(s.valor.iloc[-1])
        refs = data.series(D, [t for _, t in ref_tids], k)
        refs = refs[refs.ano == y]
        val = dict(zip(refs.tid, refs.valor))
        row |= {"Ano": str(y), "Valor": ik.fmt(v) + (" (estado inteiro)" if parte and not na_parcela else "")}
        if plvl in ("Estado", "Município", "Grande Região"):
            peers = data.snapshot(D, plvl, k, y, parte_al=parte)
            if len(peers):
                if plvl == "Estado" and uf in D["al_ufs"]:
                    # entre os estados da região, o Maranhão entra com a parcela (menos quando se olha o estado inteiro)
                    pa = data.snapshot(D, plvl, k, y, parte_al=parte or uf not in PARCIAL)
                    al = pa[pa.al.fillna(False).astype(bool)]
                    row["Posição na Amazônia Legal"] = data.position_txt(al.valor, v, ik.polarity)
                if plvl == "Município":
                    no_uf = peers[peers.uf == uf]
                    row["Posição no estado"] = data.position_txt(no_uf.valor, v, ik.polarity)
                row["Posição no Brasil"] = data.position_txt(peers.valor, v, ik.polarity)
        for n, t in ref_tids:
            row[n] = ik.fmt(val.get(t, float("nan")))
        cor = ""
        v_ref = val.get(comp_tid, float("nan")) if comp_tid else float("nan")
        if comp_tid:
            if ik.additive:
                num, sufixo = v, ""
                if plvl == "Estado" and comp_tid == AMZ and uf in PARCIAL:
                    # estado só em parte na região: a participação usa só a parcela que fica nela
                    sufixo = " (só a parte na AL)"
                    if not na_parcela:
                        mm = L[(L.nivel == "Município") & (L.uf == uf) & (L.ind == k) & (L.ano == y)
                               & L.al.fillna(False).astype(bool) & L.valor.notna()]
                        num = float(mm.valor.sum())
                row[col_comp] = f"{fmt.pct(num / v_ref * 100)} do total{sufixo}" if v_ref and not fmt.isna(v_ref) else "—"
            else:
                dif = change(v, v_ref, ik)  # p.p. para proporções, pontos para índices, % nos demais
                row[col_comp] = ik.fmt_diff(dif)
                cor = {1: theme.MELHOR, -1: theme.PIOR}.get(ik.situacao(dif), "")
        rows.append(row)
        cores.append(cor)
    return pd.DataFrame(rows).fillna("—"), cores, col_comp, comp_nome


def voltar_origem():
    st.session_state["aba"] = st.session_state.pop("tr_origem", "Mapa e Ranking")


with T["Perfil do Território"]:
    if T["Perfil do Território"].open:
        barra_filtros()
        if st.session_state.get("tr_origem"):  # chegou aqui clicando numa linha do ranking
            st.button(f"← Voltar ao {st.session_state['tr_origem']}", on_click=voltar_origem, key="tr_voltar")
        st.caption("Escolha um território, de estado a município, e veja tudo sobre ele: indicadores, evolução, posição "
                   "entre os pares e, para estados, o mapa dos municípios.")
        AGG = L[L.nivel != "Município"]
        niveis_t = ["Estado", "Município", "Grande Região", "Amazônia Legal", "Brasil"]
        p1, p2, p3 = st.columns([1, 1, 2])
        plvl = p1.selectbox("Tipo de território", niveis_t, key=state("w_tr_lvl", "Estado", niveis_t))
        terr = data.territories(D, plvl)
        if plvl == "Município":
            puf = p2.selectbox("UF", D["ufs"], key=state("w_tr_uf", "PA" if "PA" in D["ufs"] else D["ufs"][0], D["ufs"]))
            terr = terr[terr.uf == puf]
        elif plvl == "Estado":
            fora = p2.checkbox("Incluir estados fora da Amazônia Legal", key=state("w_tr_fora", False),
                               help=f"Por padrão a lista traz só os {len(D['al_ufs'])} estados da Amazônia Legal.")
            terr = terr if fora else terr[terr.uf.isin(D["al_ufs"])]
        else:
            p2.selectbox("UF", ["—"], disabled=True, help="Usada só para escolher municípios.")
        labels = terr.label.tolist()
        pref = {"Município": "Belém", "Estado": "Pará"}.get(plvl, "")
        padrao = next((l for l in labels if l.startswith(pref)), labels[0]) if pref else labels[0]
        sel = p3.selectbox("Território", labels, key=state("w_tr_terr", padrao, labels))
        row = terr[terr.label == sel].iloc[0]
        tid, cod = row.tid, int(row.cod)
        uf_t = str(row.uf) if plvl in ("Estado", "Município") else None
        nome_curto = sel.split(" (")[0]

        # estado só em parte na Amazônia Legal: a parcela que fica na região ou o estado inteiro
        PARTE = False
        if plvl == "Estado" and uf_t in PARCIAL and D["al_parte_ind"]:
            esc = st.radio(f"{nome_curto} considerado como", PARTE_OPCOES, horizontal=True,
                           key=state("w_tr_parte", PARTE_OPCOES[0], PARTE_OPCOES),
                           help="Só uma parte do estado faz parte da Amazônia Legal. Parte na Amazônia Legal: valores só dos "
                                "municípios da região. Estado inteiro: o valor do estado todo.")
            PARTE = esc == PARTE_OPCOES[0]

        def tid_de(k: str) -> str:
            """Território cujos valores valem para o indicador k: a parcela na região, quando escolhida e calculada."""
            return f"{PARTE_AL}:{cod}" if PARTE and k in D["al_parte_ind"] else tid

        # referências: níveis acima do território, usadas na evolução, no comparativo e nos downloads
        refs = []
        if plvl == "Município":
            refs.append((str(L.loc[L.tid == f"Estado:{cod // 100000}", "nome"].iloc[0]), f"Estado:{cod // 100000}"))
        if plvl == "Estado":
            reg_tid = f"Grande Região:{cod // 10}"
            refs.append((f"Região {AGG.loc[AGG.tid == reg_tid, 'nome'].iloc[0]}", reg_tid))
        if plvl in ("Município", "Estado", "Grande Região"):
            refs.append(("Amazônia Legal", AMZ))
        if plvl != "Brasil":
            refs.append(("Brasil", BRASIL))
        refs = tuple(refs)
        ref_txt = ", ".join(n for n, _ in refs[:-1]) + (" e " if len(refs) > 1 else "") + refs[-1][0] if refs else ""

        chips = [plvl]
        if plvl == "Estado":
            n_mun = int(L[(L.nivel == "Município") & (L.uf == uf_t)].cod.nunique())
            if uf_t in PARCIAL:
                al_chip = (f"Parte na Amazônia Legal: {PARCIAL[uf_t][0]} de {PARCIAL[uf_t][1]} municípios" if PARTE else
                           f"Amazônia Legal só em parte: {PARCIAL[uf_t][0]} de {PARCIAL[uf_t][1]} municípios")
            else:
                al_chip = "Amazônia Legal" if uf_t in D["al_ufs"] else "Fora da Amazônia Legal"
            chips += [uf_t, refs[0][0], al_chip, f"{n_mun} municípios"]
        if plvl == "Município":
            mrow = L[(L.tid == tid)].iloc[0]
            chips += [str(mrow.uf), str(mrow.regiao), "Amazônia Legal" if bool(mrow.al) else "Fora da Amazônia Legal"]
            if D["porte"] is not None:
                chips.append("Porte: " + str(D["porte"].get(cod, "—")))
            if D["carac"] is not None and cod in D["carac"].index:
                cr = D["carac"].loc[cod]
                chips += [f"Região imediata: {cr.rg_imediata}", f"Região intermediária: {cr.rg_intermediaria}"]
                chips += [f"PNDR: {cr.pndr}"] if pd.notna(cr.pndr) else []
                chips += ["Cidade de fronteira"] * bool(cr.fronteira) + ["Sede de região imediata"] * bool(cr.sede_imediata)
                chips += [f"IDHM: {cr.idhm}"] if pd.notna(cr.idhm) else []
        st.markdown(f"<h2 style='margin:.2rem 0 .3rem'>{sel + ' (parte na Amazônia Legal)' if PARTE else sel}</h2>"
                    + "".join(f'<span class="chip">{c}</span>' for c in chips), unsafe_allow_html=True)
        if plvl == "Estado" and uf_t in PARCIAL:  # sempre diz qual valor do estado está em uso
            if PARTE:
                sem = [REG[k].label for k in D["indicators"] if k not in D["al_parte_ind"]]
                st.info("◐ " + nota_parcial("parcela") + (" " + ", ".join(sem) + (" não existe" if len(sem) == 1 else " não existem")
                        + " só para essa parte e mostra" + ("" if len(sem) == 1 else "m") + " o estado inteiro, com a marca "
                        "\"estado inteiro\"." if sem else "") + " Em alguns anos pode faltar valor da parte por falta de "
                        "dados nos municípios.")
            else:
                st.info("◐ " + nota_parcial("inteiro"))

        if PARCIAL and plvl == "Amazônia Legal":
            st.info(nota_al())

        secoes = ["Resumo", "Evolução", "Posição", "Municípios do estado", "Dados"]
        S = dict(zip(secoes, st.tabs(secoes, key="terr_sec", on_change="rerun")))
        rank_grp = {"Município": "municípios do Brasil", "Estado": "estados", "Grande Região": "Grandes Regiões"}

        # ---- Resumo: todos os indicadores -------------------------------------------------
        with S["Resumo"]:
            if S["Resumo"].open:
                theme.title(f"{sel}: todos os indicadores {ANO_TXT}",
                            (f"Posição entre os {rank_grp[plvl]} no mesmo ano (1º = melhor situação; nos indicadores "
                             "sem polaridade, 1º = maior valor; '=' indica empate) e " if plvl in rank_grp else "")
                            + "variação do primeiro ano com dado até o ano do cartão (p.p. para proporções, pontos "
                              "para índices), em verde quando melhora e vermelho quando piora"
                            + (". Se o território não tem dado no último ano do indicador, o cartão mostra o último dado "
                               "dele, sem posição, pois não seria comparável com os demais." if RECENTE else ""))
                for eixo_nome in eixos:
                    ks = [k for k in D["indicators"] if REG[k].axis == eixo_nome]
                    with st.expander(f"{eixo_nome} · {len(ks)} indicador" + ("es" if len(ks) != 1 else ""), expanded=True):
                        for col, k in grid(ks):
                            ik = REG[k]
                            ano = year_for(k)
                            tv = tid_de(k)
                            v = value_of(tv, k, ano)
                            antigo = False
                            if RECENTE and fmt.isna(v):  # sem dado no último ano do indicador: usa o último dado do território
                                sk = data.series(D, [tv], k).dropna(subset=["valor"])
                                if len(sk):
                                    ano, v, antigo = int(sk.ano.iloc[-1]), float(sk.valor.iloc[-1]), True
                            yr0, v0 = first_valid(tv, k, ano)
                            peers = (snap(plvl, k, ano, filt=False, parte=PARTE)
                                     if plvl in ("Município", "Estado", "Grande Região") and not antigo else None)
                            rk = ""
                            if peers is not None and len(peers) and tid in set(peers.tid) and not fmt.isna(v):
                                pos, empate = data.position(peers.valor, v, ik.polarity)
                                if empate > 1 and empate / len(peers) > 0.01:  # empate que torna a posição pouco informativa
                                    rk = f"empatado em {pos}º · {empate:,} de {len(peers):,} com o mesmo valor · ".replace(",", ".")
                                else:
                                    rk = ("=" if empate > 1 else "") + f"{pos}º de {len(peers)} · "
                            ref = f"{ano} (último dado do território; indicador vai até {year_for(k)})" if antigo else f"{ano}"
                            if PARTE and tv == tid:
                                ref += " · estado inteiro"
                            if yr0 and yr0 < ano and v0 == 0 and ik.delta == "pct":
                                sub = f"{rk}{ref} · era zero em {yr0}"
                            elif yr0 and yr0 < ano:
                                sub = f"{rk}{ref} · {arrow(change(v, v0, ik), ik)} desde {yr0}"
                            elif yr0:  # sem ponto anterior: a base inteira tem um ano só, ou só este território
                                sub = f"{rk}{ref} · " + ("único ano com dado na base" if len(data.years_with_data(D, k)) == 1
                                                         else "sem ano anterior para comparar")
                            else:
                                sub = ref
                            with col:
                                st.markdown(theme.kpi(ik.label, ik.fmt(v), sub, ik.icon), unsafe_allow_html=True)

                if refs:
                    st.markdown("---")
                    tab, cores, col_comp, comp_nome = comparativo(tid, plvl, uf_t, refs, D["manifest"]["versao"], PARTE)
                    theme.title(f"{sel} comparado com {ref_txt}",
                                "Cada indicador no último ano com dado do território, ao lado das referências.", fixo=True)
                    if col_comp:
                        sty = tab.style.apply(lambda s: [f"color:{c}; font-weight:700" if c else "" for c in cores],
                                              subset=[col_comp])
                    else:
                        sty = tab
                    cfg = {"Ano": st.column_config.TextColumn(help="Último ano com dado do indicador para o território."),
                           "Posição na Amazônia Legal": st.column_config.TextColumn(
                               help=f"Entre os {len(D['al_ufs'])} estados da Amazônia Legal."),
                           "Posição no estado": st.column_config.TextColumn(help="Entre os municípios do mesmo estado."),
                           "Posição no Brasil": st.column_config.TextColumn(help="Entre os territórios do mesmo tipo no Brasil.")}
                    if col_comp:
                        cfg[col_comp] = st.column_config.TextColumn(
                            help=f"Totais (somas): participação do território no total de {comp_nome}. Taxas e médias: quanto "
                                 f"está acima (+) ou abaixo (−) de {comp_nome}; verde = situação melhor, vermelho = pior, "
                                 "conforme a polaridade do indicador.")
                    st.dataframe(sty, hide_index=True, width="stretch", column_config=cfg)
                    st.caption(f"Última coluna: para totais, participação do território em {comp_nome}; para taxas e médias, "
                               "diferença em relação a ela (verde = melhor, vermelho = pior, sem cor quando o indicador não "
                               "tem polaridade). — indica ausência de dado.")
                    if PARCIAL and plvl in ("Município", "Estado", "Grande Região"):
                        st.caption(nota_al())  # a coluna "Amazônia Legal" soma só os municípios da região
                    if plvl == "Estado" and uf_t in PARCIAL:
                        st.caption("◐ " + nota_parcial("parcela" if PARTE else "inteiro")
                                   + (" A participação e as comparações usam só essa parte."
                                      if PARTE else
                                      " Na participação dos totais, o estado entra só com a parte que está na Amazônia Legal; "
                                      "nas taxas e médias, a comparação usa o estado inteiro."))

        # ---- Evolução --------------------------------------------------------------------
        with S["Evolução"]:
            if S["Evolução"].open:
                st.caption(f"Como **{I.label}** mudou ao longo do tempo em {nome_curto}"
                           + (f", comparado com {ref_txt}." if refs else "."))
                medidas = ["Índice (base 100)", "Valor"]
                med = st.radio("Medida", medidas, horizontal=True,
                               key=state("w_tr_med", medidas[0] if I.additive else medidas[1], medidas),
                               help="Índice: crescimento relativo, bom para totais de tamanhos diferentes. "
                                    "Valor: o número publicado, bom para taxas e médias.")
                theme.title(f"Evolução de {charts.low(I.label)}: {nome_curto}" + (f", {ref_txt}" if refs else ""),
                            "Todos os anos com dado" + ("; base 100 = primeiro ano com valor diferente de zero"
                                                        if med.startswith("Índice") else ""))
                sr = data.series(D, list(dict.fromkeys([tid_de(IND), *[t for _, t in refs]])), IND)
                if PARTE:
                    st.caption("◐ " + nota_parcial(modo_parcial(True, IND)))
                plot(charts.lines(sr, I, "indice" if med.startswith("Índice") else "valor", height=400), "tr_line")

        # ---- Posição ---------------------------------------------------------------------
        with S["Posição"]:
            if S["Posição"].open:
                if plvl in ("Estado", "Grande Região"):
                    # entre os estados da região, o Maranhão entra com a parcela (menos quando se olha o estado inteiro)
                    na_regiao = plvl == "Estado" and uf_t in D["al_ufs"]
                    pares = snap(plvl, filt=False, parte=PARTE or (na_regiao and uf_t not in PARCIAL))
                    if na_regiao:
                        pares = pares[pares.al.fillna(False).astype(bool)]
                    grupo_txt = "estados da Amazônia Legal" if plvl == "Estado" and uf_t in D["al_ufs"] else rank_grp[plvl]
                    theme.title(f"{nome_curto} entre os {grupo_txt}", f"{charts.axis_label(I)} em {YEAR}")
                    if na_regiao and PARCIAL:
                        st.caption("◐ " + nota_parcial(modo_parcial(PARTE or uf_t not in PARCIAL, IND)))
                    if pares.empty:
                        st.info(f"Sem dado de {charts.low(I.label)} em {YEAR} para comparar.")
                    else:
                        plot(charts.hbar(pares, I, len(pares), highlight=sel, height=max(300, 30 * len(pares) + 40)), "tr_rank")
                elif plvl == "Município":
                    peers = snap("Município", IND, YEAR, filt=False)
                    v = value_of(tid)
                    theme.title(f"Onde {nome_curto} fica entre os {rank_grp[plvl]}",
                                f"Quantos municípios têm cada valor de {charts.low(I.label)} em {YEAR}; "
                                f"a linha vermelha é {nome_curto}")
                    if len(peers) > 3 and not fmt.isna(v):
                        pct = float((peers.valor < v).mean() * 100)
                        plot(charts.histogram(peers, I, I.log, (nome_curto, v), height=320), "tr_hist")
                        st.markdown(f"**{sel}** está acima de **{fmt.num(pct, 0)}%** dos {len(peers)} municípios com dado em "
                                    f"{YEAR}" + (" (escala logarítmica)." if I.log else "."))
                    else:
                        st.info(f"Sem dado de {charts.low(I.label)} em {YEAR} para este município.")
                    if D["carac"] is not None and cod in D["carac"].index:
                        cr = D["carac"].loc[cod]
                        grupos_cmp = {"Mesmo porte populacional": (D["porte"], D["porte"].get(cod) if D["porte"] is not None else None),
                                      "Mesma tipologia PNDR": (D["carac"].pndr, cr.pndr),
                                      "Mesma região imediata": (D["carac"].rg_imediata, cr.rg_imediata),
                                      "Mesma classe de IDHM": (D["carac"].idhm, cr.idhm)}
                        grupos_cmp = {k: v for k, v in grupos_cmp.items() if v[0] is not None and pd.notna(v[1])}
                        if grupos_cmp:
                            st.markdown("---")
                            theme.title(f"{nome_curto} comparado a municípios parecidos",
                                        f"{charts.axis_label(I)} em {YEAR} · compara com os municípios do Brasil que têm a "
                                        "mesma característica, e não com todos")
                            escolha = st.radio("Parecidos por", list(grupos_cmp), horizontal=True,
                                               key=state("w_tr_par", next(iter(grupos_cmp)), list(grupos_cmp)))
                            serie, valor_grupo = grupos_cmp[escolha]
                            par = peers[peers.cod.map(serie) == valor_grupo]
                            vm = value_of(tid)
                            if fmt.isna(vm):
                                st.info(f"{sel} não tem dado de {charts.low(I.label)} em {YEAR}.")
                            elif len(par) < 5:
                                st.info("Poucos municípios com dado neste grupo para comparar.")
                            else:
                                m1, m2, m3 = st.columns(3)
                                m1.metric(nome_curto, I.fmt(vm))
                                m2.metric(f"Mediana do grupo ({len(par):,})".replace(",", "."), I.fmt(par.valor.median()))
                                m3.metric("Posição no grupo", data.position_txt(par.valor, vm, I.polarity))
                                st.caption(f"Grupo: {valor_grupo}. Posição: {data.rank_rule(I.polarity)}; '=' indica "
                                           "posição dividida com outro município.")
                                plot(charts.histogram(par, I, I.log, (nome_curto, vm), height=300), "tr_par")
                else:
                    st.info(f"{sel} não tem pares para comparar: a posição existe para estados, Grandes Regiões e municípios.")

        # ---- Municípios do estado ---------------------------------------------------------
        with S["Municípios do estado"]:
            if S["Municípios do estado"].open:
                if plvl != "Estado":
                    st.info("Esta seção aparece quando o território escolhido é um estado: mostra o mapa e os extremos "
                            "dos municípios dele.")
                else:
                    md = data.snapshot(D, "Município", IND, YEAR, ufs=[uf_t])
                    theme.title(f"{I.label} nos municípios de {sel}",
                                f"{YEAR} · {len(md)} de {n_mun} municípios com dado · cor = faixa do município dentro do "
                                "estado (grupos de tamanho parecido, do menor ao maior valor)")
                    if len(md) < 5:
                        st.info(f"{I.label} não tem dado municipal suficiente para {sel} em {YEAR}"
                                + (" (indicador só tem dado estadual)." if md.empty else "."))
                    else:
                        mc, side = st.columns([2, 1])
                        with mc:
                            cores_m = ["Faixas (quintis)", "Contínua (log)" if I.log else "Contínua"]
                            modo = st.radio("Escala de cores", cores_m, horizontal=True, key=state("w_tr_mode", cores_m[0], cores_m))
                            plot(charts.choropleth(md, I, "Município", "faixas" if modo.startswith("Faixas") else "continua",
                                                   **uf_view(cod), height=520), "tr_map")
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
                                           "do total do estado.")
                            acima = int((md.valor > md.valor.median()).sum())
                            st.caption(f"{acima} municípios estão acima da mediana estadual.")
                        b1, b2 = st.columns(2)
                        with b1:
                            theme.title("10 municípios com maior valor", f"{charts.axis_label(I)} em {YEAR}")
                            plot(charts.hbar(md, I, 10, height=320), "tr_top")
                        with b2:
                            theme.title("10 municípios com menor valor", f"{charts.axis_label(I)} em {YEAR}")
                            plot(charts.hbar(md, I, 10, ascending=True, height=320, color=theme.TEAL), "tr_bot")
                    if I.kind == "moeda":
                        st.markdown('<div class="note">Valores a preços correntes (nominais): comparações entre anos incluem '
                                    'inflação.</div>', unsafe_allow_html=True)

        # ---- Dados ------------------------------------------------------------------------
        with S["Dados"]:
            if S["Dados"].open:
                theme.title(f"{sel}: tabela com todos os indicadores, ano a ano")
                wide = (L[(L.tid == tid)].pivot_table(index="ano", columns="ind", values="valor", observed=True)
                        .reindex(columns=D["indicators"]))
                if PARTE:  # valores da parcela na região onde existem; os demais indicadores ficam com o estado inteiro
                    wp = L[L.tid == f"{PARTE_AL}:{cod}"].pivot_table(index="ano", columns="ind", values="valor", observed=True)
                    for k in wp.columns:
                        wide[k] = wp[k].reindex(wide.index)
                    st.caption("◐ " + nota_parcial("parcela"))
                tabela = wide.apply(lambda s: s.map(REG[s.name].fmt) if s.name in REG else s)
                st.dataframe(tabela.rename(columns={k: charts.axis_label(REG[k]) for k in tabela.columns}), width="stretch")
                st.caption("— indica ano sem dado na base de origem.")
                st.markdown("---")
                theme.title(f"Baixar os dados de {sel}",
                            "Arquivos CSV (separador ;, decimal ,) com todos os indicadores e anos, na unidade mostrada no painel")
                slug = re.sub(r"[^a-z0-9]+", "_", nome_curto.lower()).strip("_")
                dl = st.columns(3)
                if refs:
                    tab_dl = comparativo(tid, plvl, uf_t, refs, D["manifest"]["versao"], PARTE)[0]
                    dl[0].download_button("Tabela comparativa", csv_bytes(tab_dl), f"comparativo_{slug}.csv", "text/csv",
                                          help="A tabela comparativa da seção Resumo.", width="stretch")
                tids_s = [tid, *([f"{PARTE_AL}:{cod}"] if PARTE else []), *[t for _, t in refs]]
                dl[1].download_button(f"Séries: {nome_curto}" + (f", {ref_txt}" if refs else ""),
                                      csv_bytes(tabela_longa(L[L.tid.isin(tids_s)])), f"series_{slug}.csv", "text/csv",
                                      width="stretch", help="Uma linha por território, indicador e ano.")
                if plvl == "Estado":
                    mun_uf = L[(L.nivel == "Município") & (L.uf == uf_t)]
                    dl[2].download_button(f"Municípios de {uf_t} ({n_mun})", csv_bytes(tabela_longa(mun_uf)),
                                          f"municipios_{slug}.csv", "text/csv", width="stretch",
                                          help="Uma linha por município, indicador e ano.")

# =========================================================================== #
# 3. MAPA E RANKING
# =========================================================================== #
def sem_acento(t: str) -> str:
    """Minúsculas e sem acentos, para buscar 'belem' e achar 'Belém'."""
    return "".join(c for c in unicodedata.normalize("NFD", str(t).strip().lower()) if unicodedata.category(c) != "Mn")


def abrir_territorio(nivel: str, label: str, uf: str):
    """Leva o território escolhido no ranking para a aba Perfil do Território (roda antes da nova execução da página)."""
    st.session_state["w_tr_lvl"] = nivel
    if nivel == "Município":
        st.session_state["w_tr_uf"] = uf
    if nivel == "Estado" and uf not in D["al_ufs"]:
        st.session_state["w_tr_fora"] = True
    if nivel == "Estado" and uf in PARCIAL:
        st.session_state["w_tr_parte"] = PARTE_OPCOES[0] if AL_ONLY else PARTE_OPCOES[1]
    st.session_state["w_tr_terr"] = label
    st.session_state["tr_origem"] = "Mapa e Ranking"  # a aba Perfil do Território mostra o botão de volta
    st.session_state["aba"] = "Perfil do Território"


def clique_ranking(key: str, nivel: str, linhas: list[tuple[str, str]]):
    """Clique numa linha do ranking: abre o território na aba Perfil do Território. A tabela ganha uma chave nova, para a
    linha não continuar marcada quando o usuário voltar ao ranking."""
    sel = st.session_state[key].selection.rows
    st.session_state["mr_tabela_n"] = st.session_state.get("mr_tabela_n", 0) + 1
    if sel and sel[0] < len(linhas):
        abrir_territorio(nivel, *linhas[sel[0]])


def variacao_desde(level: str, ind: str = IND, year: int | None = None, parte: bool = False) -> pd.DataFrame:
    """Por território: variação do primeiro ano com dado até `year`, na medida do indicador (p.p. para proporções,
    pontos para índices, % nos demais), e o ano de partida, que pode diferir entre territórios."""
    year = year_for(ind) if year is None else year
    ik = REG[ind]
    d = L[(L.nivel == level) & (L.ind == ind) & L.valor.notna() & (L.ano <= year)].sort_values("ano")
    g = d.groupby("cod", observed=True).agg(v0=("valor", "first"), v1=("valor", "last"), ano0=("ano", "first"))
    if level == "Estado" and parte and PARCIAL:  # estado só em parte na região: variação da parcela que fica nela
        dp = L[(L.nivel == PARTE_AL) & (L.ind == ind) & L.valor.notna() & (L.ano <= year)].sort_values("ano")
        gp = dp.groupby("cod", observed=True).agg(v0=("valor", "first"), v1=("valor", "last"), ano0=("ano", "first"))
        g.loc[gp.index, ["v0", "v1", "ano0"]] = gp
    if ik.delta == "pct":
        var = (g.v1 / g.v0.replace(0, np.nan) - 1) * 100  # base zero: sem variação
    else:
        var = (g.v1 - g.v0) * ik.scale
    return pd.DataFrame({"var": var.where(g.ano0 < year), "ano0": g.ano0.where(g.ano0 < year)})


def cheia(cor: str) -> str:
    """Célula com a mesma cor do mapa (faixa ou escala contínua) e texto legível sobre ela."""
    return f"background-color:{cor}; color:{theme.text_on(cor)}; font-weight:600"


with T["Mapa e Ranking"]:
    if T["Mapa e Ranking"].open:
        barra_filtros()
        niveis = ["Estado", "Município", "Grande Região"]
        r1, r2, _ = st.columns([0.95, 1, 1.5])
        lvl = r1.radio("Territórios", niveis, horizontal=True, key=state("w_mr_lvl", "Município", niveis),
                       format_func=lambda x: {"Estado": "Estados", "Município": "Municípios",
                                              "Grande Região": "Grandes Regiões"}[x])
        tem_mapa = True
        cores = ["Faixas (quintis)", "Contínua (log)" if I.log else "Contínua"]
        mode_lbl = (r2.radio("Escala de cores", cores, horizontal=True, key=state("w_mr_mode", cores[0], cores),
                             help="Faixas: grupos de tamanho parecido (5, ou 3 quando há poucos territórios), bom para ver posição "
                                  "relativa. "
                                  "Contínua: a cor acompanha o valor" + (" (em escala logarítmica)." if I.log else "."))
                    if tem_mapa else cores[0])
        rk = snap(lvl)
        if len(rk) < (5 if lvl != "Grande Região" else 1):
            st.warning("Poucos territórios com dado nesta combinação de filtros.")
        else:
            # posição pela polaridade da ficha: 1º = melhor situação (sem polaridade, 1º = maior valor);
            # empatados dividem a posição. A ordem da tabela só muda a leitura, não a posição.
            rk["pos"] = data.ranks(rk.valor, I.polarity)
            rk = rk.sort_values(["pos", "label"]).reset_index(drop=True)
            vd = variacao_desde(lvl, parte=AL_ONLY)
            rk["var"] = rk.cod.map(vd["var"])
            rk["ano0"] = rk.cod.map(vd["ano0"])
            rk["share"] = rk.valor / rk.valor.sum() * 100 if I.additive else np.nan
            rk["faixa"] = (data.bands(rk.valor).astype(int) + 1).map(lambda i: f"Faixa {i}")
            em_faixas = mode_lbl.startswith("Faixas")
            cor_faixa = charts.band_colors(I, rk.faixa.nunique())  # as mesmas cores da legenda do mapa
            rk["cor"] = None if em_faixas else charts.continuous_colors(rk.valor, I)  # escala contínua do mapa
            marca_al = not AL_ONLY and lvl != "Grande Região" and rk.al.fillna(False).astype(bool).any()
            parciais = sorted(u for u in rk.uf.unique() if u in PARCIAL) if lvl == "Estado" else []
            mostra_al = marca_al or bool(parciais)  # coluna AL: ● na Amazônia Legal, ◐ no estado só em parte
            # valor usado nos estados só em parte: o da parcela que fica na região (se calculado) ou o do estado inteiro
            aplicada = lvl == "Estado" and bool(rk.parcela.any())
            modo_mr = "parcela" if aplicada else ("sem_parcela" if (AL_ONLY and lvl == "Estado" and D["al_parte_ind"]) else "inteiro")
            sentido = {1: "↑ maior é melhor", -1: "↓ menor é melhor"}.get(I.polarity, "sem polaridade")

            def resumo(n_col: int = 4):
                """Mediana, média, máximo e mínimo em cartões; na coluna estreita ao lado do mapa, 2 por linha."""
                lo, hi = rk.loc[rk.valor.idxmin()], rk.loc[rk.valor.idxmax()]
                itens = [("Mediana", rk.valor.median(), None), ("Média", rk.valor.mean(), None),
                         ("Máximo", hi.valor, hi.label), ("Mínimo", lo.valor, lo.label)]
                for i in range(0, 4, n_col):
                    for c, (nome, v, onde) in zip(st.columns(n_col), itens[i:i + n_col]):
                        c.metric(nome, I.fmt(v), help=onde)
                st.caption(f"Máximo: {hi.label} · Mínimo: {lo.label} · Unidade: {I.unit} · {YEAR} · "
                           f"{escopo(lvl, len(rk))}")
                st.caption("**Mediana** é o valor do meio: metade dos territórios fica acima e metade abaixo. "
                           "**Média** soma todos os valores e divide pelo número de territórios; valores muito altos "
                           "puxam a média para cima, por isso as duas podem ser bem diferentes.")

            def tabela():
                ordens = (["Melhor situação primeiro", "Pior situação primeiro"] if I.polarity
                          else ["Maiores primeiro", "Menores primeiro"])
                t1, t2 = st.columns([1.2, 1])
                ordem = t1.radio("Ordem da tabela", ordens, horizontal=True, key=state("w_mr_ordem", ordens[0], ordens))
                busca = t2.text_input("Buscar na tabela", placeholder="ex.: belem", key=state("w_mr_busca", ""),
                                      help="Só filtra as linhas da tabela, sem diferenciar acentos nem maiúsculas; as "
                                           "posições continuam as do ranking completo.")
                view = rk[rk.label.map(sem_acento).str.contains(sem_acento(busca), regex=False)] if busca else rk
                if ordem == ordens[1]:
                    view = view.iloc[::-1]
                # ano de partida da variação: no título quando é o mesmo para todos, numa coluna quando varia
                anos0 = rk.ano0.dropna().unique()
                VAR = f"Variação desde {int(anos0[0])}" if len(anos0) == 1 else "Variação"
                tbl = pd.DataFrame({
                    "Posição": view.pos, "Território": view.label,  # o rótulo de município já traz a UF
                    **({"AL": [("◐" if (lvl == "Estado" and u in PARCIAL) else "●" if (a and marca_al) else "")
                               for u, a in zip(view.uf, view.al.fillna(False).astype(bool))]} if mostra_al else {}),
                    f"{I.label}": view.valor.map(I.fmt), VAR: view["var"].map(I.fmt_diff),
                    **({"Desde": view.ano0.astype("Int64").astype(str).replace("<NA>", "—")} if len(anos0) > 1 else {}),
                    "Participação (%)": view.share.map(lambda v: fmt.pct(v, 2)), "Faixa": view.faixa.str[-1]})
                if not em_faixas:  # na escala contínua não há faixas: a cor do mapa vai no próprio valor
                    tbl = tbl.drop(columns=["Faixa"])
                if not I.additive:
                    tbl = tbl.drop(columns=["Participação (%)"])
                # larguras em pixels somando cerca de 600, para a tabela caber ao lado do mapa sem rolagem lateral;
                # o título do valor é "Valor" (o nome do indicador já está no título e a unidade, na ajuda)
                cfg = {"Posição": st.column_config.NumberColumn(
                           width=58, help=data.rank_rule(I.polarity) + ". Territórios com o mesmo valor dividem a "
                                          "posição."),
                       "Território": st.column_config.TextColumn(width=170 if mostra_al else 190),
                       "AL": st.column_config.TextColumn(
                           width=34, help="● Território da Amazônia Legal. ◐ Estado só em parte na região: " + nota_parcial(modo_mr)),
                       f"{I.label}": st.column_config.TextColumn("Valor", width=90, help=f"{I.label} · {I.unit}, em {YEAR}"),
                       VAR: st.column_config.TextColumn(
                           width=110 if len(anos0) == 1 else 90,
                           help={"pct": "Variação relativa (%)", "pp": "Diferença em pontos percentuais (p.p.)",
                                 "pts": "Diferença em pontos do índice"}[I.delta]
                                + f" do primeiro ano com dado até {YEAR}"
                                + (", em azul quando a situação melhorou e em vermelho quando piorou." if I.polarity
                                   else " (indicador sem polaridade: sem cor de melhor ou pior).")),
                       "Desde": st.column_config.TextColumn(width=52, help="Ano de partida da variação, que difere "
                                                                           "entre territórios conforme os dados."),
                       "Participação (%)": st.column_config.TextColumn(
                           "Parte", width=64, help="Parte do total somado de todos os territórios do ranking."),
                       "Faixa": st.column_config.TextColumn(
                           width=48, help="1 = faixa dos menores valores … última = maiores valores. Mesmas faixas e "
                                          "cores do mapa.")}

                cor_sit = {1: f"color:{theme.MELHOR}; font-weight:700", -1: f"color:{theme.PIOR}; font-weight:700"}
                css_var = [cor_sit.get(I.situacao(d), "") for d in view["var"]]
                sty = tbl.style.apply(lambda _: css_var, subset=[VAR])
                if em_faixas:
                    sty = sty.map(lambda v: cheia(cor_faixa[int(v) - 1]), subset=["Faixa"])
                else:
                    cores_v = view.cor.values
                    sty = sty.apply(lambda _: [cheia(c) for c in cores_v], subset=[f"{I.label}"])

                theme.title(f"Ranking de {charts.low(I.label)}: {escopo(lvl)}",
                            f"{YEAR} · {len(rk):,} no ranking".replace(",", ".")
                            + (f" · {len(view)} encontrados para '{busca}'" if busca else "")
                            + f" · {data.rank_rule(I.polarity)}" + f'<span class="sentido">{sentido}</span>')
                st.markdown('<div class="hint"><div class="i">↗</div><div><b>Clique em uma linha</b> para abrir o '
                            "perfil completo do território (todos os indicadores, evolução e comparação com os pares) "
                            "na aba <b>Perfil do Território</b>.</div></div>", unsafe_allow_html=True)
                key = f"mr_tabela_{st.session_state.get('mr_tabela_n', 0)}"
                linhas = [(str(r.label), str(r.uf)) for r in view.itertuples()]
                st.dataframe(sty, width="stretch", hide_index=True, height=min(520, 35 * (len(tbl) + 1) + 3),
                             column_config=cfg, on_select=partial(clique_ranking, key, lvl, linhas),
                             selection_mode="single-row", key=key)
                if parciais:
                    st.caption("◐ " + nota_parcial(modo_mr))
                nome_var = {"pct": "variacao_pct", "pp": "variacao_pp", "pts": "variacao_pontos"}[I.delta]
                st.download_button("Baixar ranking (CSV)",
                                   rk[["pos", "label", "uf", "valor", "var", "ano0", "share", "faixa"]]
                                   .rename(columns={"pos": "posicao", "label": "territorio", "var": nome_var,
                                                    "ano0": "variacao_desde", "share": "participacao_pct"})
                                   .to_csv(index=False, sep=";", decimal=",").encode("utf-8-sig"),
                                   f"ranking_{lvl}_{YEAR}.csv", "text/csv")

            if tem_mapa:
                mc, side = st.columns([1, 1])
                with mc:
                    destaque = " · contorno forte = Amazônia Legal" if marca_al else ""
                    if parciais:
                        nomes = ", ".join(NOME_UF[u] for u in parciais)
                        destaque += (f" · {nomes}: só a parte na Amazônia Legal (contorno forte, ◐ na tabela)" if aplicada
                                     else f" · {nomes}: estado inteiro; o contorno forte marca só a parte na região (◐ na tabela)")
                    theme.title(f"{I.label} por {lvl.lower()}", f"{YEAR} · {escopo(lvl, len(rk))}{destaque}")
                    plot(charts.choropleth(rk, I, lvl, "faixas" if mode_lbl.startswith("Faixas") else "continua",
                                           **map_view(lvl), height=640 if lvl != "Grande Região" else 560, destaque_al=marca_al,
                                           al_parcial=tuple(PARCIAL)), "map_main")
                    if mode_lbl.startswith("Faixas"):
                        st.markdown(charts.legend_html(rk, I), unsafe_allow_html=True)
                with side:
                    resumo(2)
                    tabela()
            else:
                resumo()
                tabela()
        if I.kind == "moeda":
            st.markdown('<div class="note">Valores a preços correntes (nominais): comparações entre anos incluem '
                        'inflação.</div>', unsafe_allow_html=True)

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
            medidas = ["Valor", "Índice (base 100)", "Variação anual"]
            mode_lbl = st.radio("Medida", medidas, key=state("w_ts_mode", "Valor", medidas),
                                help="Valor: o número publicado. Índice: crescimento relativo (base 100 no início), "
                                     "para comparar territórios de tamanhos diferentes. "
                                     "Variação: % de um ano para o outro.")
            mode = {"Valor": "valor", "Índice (base 100)": "indice", "Variação anual": "var"}[mode_lbl]
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
        if PARCIAL and use_al:
            st.caption(nota_al())
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
                medida = ("taxa composta (TCMA, % ao ano)" if I.delta == "pct"
                          else f"diferença média anual ({I.delta_unit} ao ano)")
                theme.title(f"Variação média por ano de {charts.low(I.label)}",
                            f"{medida[0].upper() + medida[1:]}, do primeiro ao último ano com dado de cada território; "
                            "cor = nível do território")
                rows = []
                for t, g in sr.dropna(subset=["valor"]).groupby("tid", sort=False):
                    g = g.sort_values("ano")
                    rows.append(dict(label=g.label.iloc[0], nivel=g.nivel.iloc[0], tcma=I.rate(
                        g.valor.iloc[0], g.valor.iloc[-1], int(g.ano.iloc[-1] - g.ano.iloc[0])),
                        de=int(g.ano.iloc[0]), ate=int(g.ano.iloc[-1])))
                cg = pd.DataFrame(rows, columns=["label", "nivel", "tcma", "de", "ate"]).dropna(subset=["tcma"])
                cg = cg.sort_values("tcma")
                un_a = "% ao ano" if I.delta == "pct" else f"{I.delta_unit} ao ano"
                rot = [f"{I.fmt_diff(v)} ao ano ({a}–{b})".replace("% ao ano", "% a.a.") for v, a, b in
                       zip(cg.tcma, cg.de, cg.ate)]
                fig = go.Figure(go.Bar(
                    x=cg.tcma, y=cg.label, orientation="h",
                    marker=dict(color=[theme.LEVEL_COLOR.get(n, theme.ACCENT) for n in cg.nivel], cornerradius=4),
                    customdata=rot,
                    hovertemplate="%{y}<br>%{customdata}<extra></extra>"))
                # rótulos sempre à direita do zero, para não cobrir o nome quando a barra é negativa
                fig.add_trace(go.Scatter(
                    x=cg.tcma.clip(lower=0), y=cg.label, mode="text", textposition="middle right", hoverinfo="skip",
                    text=[" " + r for r in rot],
                    textfont=dict(size=11), showlegend=False, cliponaxis=False))
                lo, hi = min(0.0, cg.tcma.min()), max(0.0, cg.tcma.max())
                fig.update_layout(height=max(260, 34 * len(cg) + 60), margin=dict(r=10), showlegend=False)
                fig.update_xaxes(ticksuffix="%" if I.delta == "pct" else "", title=un_a,
                                 range=[lo - (hi - lo or 1) * 0.05 if lo < 0 else 0, hi + (hi - lo or 1) * 0.6])
                plot(fig, "ts_cagr")
            with h2:
                leg = ("verde: melhora · vermelho: piora" if I.polarity
                       else "azul: cresceu · marrom: caiu (indicador sem polaridade)")
                theme.title(f"Variação de {charts.low(I.label)} a cada ano, por território",
                            f"{'% ao ano' if I.delta == 'pct' else I.delta_unit + ' ao ano'} em relação ao ano anterior "
                            f"com dado · {leg}")
                plot(charts.growth_heatmap(sr, I), "ts_heat")

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
# 7. COMPARAÇÕES
# =========================================================================== #
with T["Comparações"]:
    if T["Comparações"].open:
        barra_filtros()
        # ---- A. entre granularidades -------------------------------------------------
        theme.title(f"{I.label} em {YEAR}: Brasil, Amazônia Legal, Grandes Regiões e estados lado a lado",
                    f"Cor = nível do território. Só os estados seguem os filtros ({escopo('Estado')}); "
                    "Brasil, Amazônia Legal e Grandes Regiões aparecem sempre.")
        if PARCIAL:
            st.caption(nota_al())
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

        # ---- C. distribuição por UF (extra, recolhido: gráfico mais técnico) ---------------
        mm = snap("Município")
        with st.expander("Extra · distribuição dos municípios em cada UF (boxplot)", expanded=False):
            theme.title(f"Como {charts.low(I.label)} varia entre os municípios de cada UF",
                        f"{YEAR} · {escopo('Município', len(mm))} · a caixa vai do 1º ao 3º quartil (metade dos "
                        "municípios), a linha no meio é a mediana e os pontos soltos são municípios fora do padrão")
            if len(mm) > 10:
                plot(charts.box_by_uf(mm, I, log=I.log), "box")
            else:
                st.info("Poucos municípios com os filtros atuais para desenhar a distribuição.")
        st.markdown("---")

        # ---- D. face a face -----------------------------------------------------------
        theme.title("Face a face: dois territórios em todos os indicadores",
                    f"Escolhidos aqui, de qualquer nível; não seguem os filtros de território. "
                    + ("Cada indicador no seu ano mais recente (coluna Ano)." if RECENTE else f"Valores de {YEAR}.")
                    + " A × B: diferença em p.p. para proporções e em pontos para índices; razão A ÷ B nos demais. "
                      "Verde quando A está em situação melhor que B e vermelho quando pior.",
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
        rows, cores_ff = [], []
        for k in D["indicators"]:
            ik = REG[k]
            va, vb = value_of(picks[0][1], k), value_of(picks[1][1], k)
            if ik.delta == "pct":  # totais e taxas: razão; a situação segue o sinal de A − B
                comp = fmt.num(va / vb, 2) + "×" if vb and not fmt.isna(va) and not fmt.isna(vb) else "—"
                sit = ik.situacao(va - vb) if comp != "—" else 0
            else:  # proporções e índices: diferença na unidade do indicador
                d = ik.diff(va, vb)
                comp, sit = ik.fmt_diff(d), ik.situacao(d)
            rows.append({"Indicador": charts.axis_label(ik), "Ano": str(year_for(k)), picks[0][0]: ik.fmt(va),
                         picks[1][0]: ik.fmt(vb), "A × B": comp})
            cores_ff.append({1: f"color:{theme.MELHOR}; font-weight:700",
                             -1: f"color:{theme.PIOR}; font-weight:700"}.get(sit, ""))
        ff = pd.DataFrame(rows)
        if len(set(ff.columns)) < len(ff.columns):  # A e B iguais: mesma coluna duas vezes
            ff.columns = ["Indicador", "Ano", f"A: {picks[0][0]}", f"B: {picks[1][0]}", "A × B"]
        st.dataframe(ff.style.apply(lambda s: cores_ff, subset=["A × B"]), width="stretch", hide_index=True,
                     column_config={"A × B": st.column_config.TextColumn(
                         help="Proporções: A − B em pontos percentuais. Índices: A − B em pontos do índice. Demais: "
                              "A ÷ B. Verde = A em situação melhor, vermelho = pior; sem cor nos indicadores sem "
                              "polaridade.")})
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
            if PARCIAL:
                st.markdown("**Estados só em parte na Amazônia Legal.** " + nota_parcial("parcela") + " Quando a abrangência é "
                            "Amazônia Legal, o painel mostra só a parte desse estado que está na região, calculada com os "
                            "municípios dela. Os estados inteiros mais essa parte somam o total da Amazônia Legal. Indicadores "
                            "que só existem para o estado todo (como o IDHM) mostram o estado inteiro, com aviso. Quando a "
                            "abrangência é Brasil inteiro, o estado aparece inteiro. Na aba Perfil do Território dá para alternar entre "
                            "as duas leituras.")
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
                    + (f"- **Fórmula:** {m['formula']}\n" if m.get("formula") else "") +
                    f"- **Periodicidade / série:** {m['periodicity']} · {m['series']}\n"
                    f"- **Unidade:** {m['unit']} · **Polaridade:** {m['polarity']}\n"
                    f"- **Regra de agregação (ficha):** {m['aggregation']} · **Menor unidade:** {m['minTerritory']}\n"
                    f"- **Amazônia Legal no painel:** {m.get('aggregationApplied', '—')}")
                st.markdown(f'<div class="note"><b>Limitações.</b> {m["limits"]}</div>', unsafe_allow_html=True)

theme.footer()
