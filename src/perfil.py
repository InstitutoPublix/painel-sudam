"""Cálculos do Perfil do Território, sem Streamlit: usados pela aba do painel e pelo relatório em PDF, para os dois
mostrarem exatamente os mesmos números.

Para cada indicador, `linhas` devolve o valor do território no último ano com dado dele, os valores das referências
(nível acima, Amazônia Legal, Brasil) no mesmo ano, a posição entre os pares, a comparação com a referência principal
e a série do território (para a evolução)."""
from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from . import data, fmt
from .data import PARTE_AL

BRASIL, AMZ = "Brasil:1", "Amazônia Legal:0"
NAN = float("nan")


_INDICE: dict = {}  # id da base → posições das linhas de cada indicador (só a base mais recente)


def fatia(D: dict, k: str) -> dict:
    """D com a base reduzida às linhas do indicador k: as consultas de data.py (series, snapshot) dão o mesmo
    resultado, sem varrer a base inteira (milhões de linhas) a cada chamada. Guarda só as posições das linhas de
    cada indicador, não uma cópia da base."""
    L = D["long"]
    if id(L) not in _INDICE:
        _INDICE.clear()
        _INDICE[id(L)] = L.groupby("ind", observed=True).indices
    pos = _INDICE[id(L)].get(k)
    return {**D, "long": L.iloc[pos] if pos is not None else L.iloc[:0]}


def al_por_estados(D: dict, k: str) -> bool:
    """O total da Amazônia Legal do indicador é a soma dos estados dela (o Maranhão entra inteiro)."""
    return k in D["registry"] and D["registry"][k].agg_note.startswith("Soma dos estados")


def referencias(D: dict, plvl: str, cod: int) -> tuple[tuple[str, str], ...]:
    """Territórios de referência (nome, tid): nível acima do território, Amazônia Legal e Brasil."""
    L = D["long"]
    refs = []
    if plvl == "Município":
        refs.append((str(L.loc[L.tid == f"Estado:{cod // 100000}", "nome"].iloc[0]), f"Estado:{cod // 100000}"))
    if plvl == "Estado":
        reg_tid = f"Grande Região:{cod // 10}"
        refs.append((f"Região {L.loc[L.tid == reg_tid, 'nome'].iloc[0]}", reg_tid))
    if plvl in ("Município", "Estado", "Grande Região"):
        refs.append(("Amazônia Legal", AMZ))
    if plvl != "Brasil":
        refs.append(("Brasil", BRASIL))
    return tuple(refs)


def referencia_principal(refs) -> tuple[str | None, str]:
    """A referência da coluna de comparação: a Amazônia Legal, quando ela está entre as referências."""
    nomes = {t: n for n, t in refs}
    tid = AMZ if AMZ in nomes else (refs[0][1] if refs else None)
    return tid, nomes.get(tid, "")


Posicao = tuple[int, int, int]  # (posição, nº de territórios com o mesmo valor, nº de territórios)


def pos_txt(p: Posicao) -> str:
    """'3º de 9' ou '=3º de 9' quando a posição é dividida com outro território (como data.position_txt)."""
    pos, emp, n = p
    return ("=" if emp > 1 else "") + f"{pos}º de {n:,}".replace(",", ".")


def _posicao(valores: pd.Series, v: float, polaridade: int) -> Posicao:
    pos, emp = data.position(valores, v, polaridade)
    return pos, emp, len(valores)


@dataclass
class Linha:
    k: str
    ano: int | None = None             # último ano com dado do território (None: sem dado)
    valor: float = NAN
    estado_inteiro: bool = False       # queria a parcela na Amazônia Legal, mas o indicador só existe inteiro
    motivo_inteiro: str = ""           # por que a parcela não existe (vazio: o dado só existe para o estado inteiro)
    refs: dict = field(default_factory=dict)        # tid da referência → valor no mesmo ano
    pos_al: Posicao | None = None      # entre os estados da Amazônia Legal
    pos_uf: Posicao | None = None      # entre os municípios do mesmo estado
    pos_br: Posicao | None = None      # entre os territórios do mesmo tipo no Brasil
    comp_tipo: str = ""                # 'participacao' (totais) ou 'diferenca' (taxas e médias)
    comp: float | None = None          # participação (%) ou diferença; None quando não dá para comparar
    comp_sufixo: str = ""
    situacao: int = 0                  # 1 melhor, −1 pior que a referência principal (pela polaridade)
    serie: pd.DataFrame | None = None  # anos e valores do território
    ano0: int | None = None            # primeiro ano comparável com dado
    valor0: float = NAN
    variacao: float = NAN              # do primeiro ano comparável até `ano`, na medida do indicador

    @property
    def tem_dado(self) -> bool:
        return self.ano is not None


def linhas(D: dict, tid: str, plvl: str, uf: str | None, refs, parte: bool = False, inds=()) -> list[Linha]:
    """Uma Linha por indicador que existe no nível do território (`inds`: só esses indicadores, na ordem dada).
    parte: num estado só em parte na Amazônia Legal, usa o valor da parcela na região (os indicadores que só existem
    para o estado inteiro mantêm esse valor e ficam com estado_inteiro=True)."""
    REG, PARCIAL = D["registry"], D["al_parcial"]
    D_todo = D
    comp_tid, _ = referencia_principal(refs)
    out = []
    for k in inds or D_todo["indicators"]:
        if plvl not in D_todo["meta"][k]["levels"]:
            continue
        D = fatia(D_todo, k)  # só as linhas deste indicador
        L = D["long"]
        ik = REG[k]
        na_parcela = parte and k in D["al_parte_ind"]
        s = data.series(D, [f"{PARTE_AL}:{tid.split(':')[1]}" if na_parcela else tid], k).dropna(subset=["valor"])
        ln = Linha(k)
        out.append(ln)
        if s.empty:
            continue
        y, v = int(s.ano.iloc[-1]), float(s.valor.iloc[-1])
        ln.ano, ln.valor, ln.estado_inteiro = y, v, parte and not na_parcela
        if ln.estado_inteiro:
            ln.motivo_inteiro = D_todo["meta"][k].get("parteAL", "")
        ln.serie = s[["ano", "valor"]].reset_index(drop=True)
        r = data.series(D, [t for _, t in refs], k)
        r = r[r.ano == y]
        ln.refs = dict(zip(r.tid, r.valor))
        if plvl in ("Estado", "Município", "Grande Região"):
            peers = data.snapshot(D, plvl, k, y, parte_al=parte)
            if len(peers):
                if plvl == "Estado" and uf in D["al_ufs"]:
                    # entre os estados da região, o Maranhão entra com a parcela (menos quando se olha o estado inteiro)
                    pa = data.snapshot(D, plvl, k, y, parte_al=parte or uf not in PARCIAL)
                    ln.pos_al = _posicao(pa[pa.al.fillna(False).astype(bool)].valor, v, ik.polarity)
                if plvl == "Município":
                    ln.pos_uf = _posicao(peers[peers.uf == uf].valor, v, ik.polarity)
                ln.pos_br = _posicao(peers.valor, v, ik.polarity)
        if comp_tid:
            v_ref = ln.refs.get(comp_tid, NAN)
            if ik.additive:
                num = v
                if plvl == "Estado" and comp_tid == AMZ and uf in PARCIAL and not al_por_estados(D, k):
                    # estado só em parte na região: a participação usa só a parcela que fica nela
                    ln.comp_sufixo = " (só a parte na AL)"
                    if not na_parcela:
                        mm = L[(L.nivel == "Município") & (L.uf == uf) & (L.ind == k) & (L.ano == y)
                               & L.al.fillna(False).astype(bool) & L.valor.notna()]
                        num = float(mm.valor.sum())
                ln.comp_tipo = "participacao"
                ln.comp = num / v_ref * 100 if v_ref and not fmt.isna(v_ref) else None
            elif not ik.magnitude:  # contagens e participações de leitura de magnitude não se comparam com a referência
                ln.comp_tipo = "diferenca"
                ln.comp = ik.diff(v, v_ref)  # p.p. para proporções, pontos para índices, % nos demais
                ln.situacao = ik.situacao(ln.comp)
        # variação desde o primeiro ano comparável (quebras de método: só o mesmo trecho da série)
        s0 = s[s.ano >= (data.inicio_comparavel(k, y) or 0)]
        ln.ano0, ln.valor0 = int(s0.ano.iloc[0]), float(s0.valor.iloc[0])
        if ln.ano0 < y and not (ln.valor0 == 0 and ik.delta == "pct") and not ik.no_change:
            ln.variacao = ik.diff(v, ln.valor0)
    return out
