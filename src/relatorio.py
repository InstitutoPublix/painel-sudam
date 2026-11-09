"""Relatório do território em PDF (A4 retrato), montado na aba Relatório do painel.

A pessoa escolhe o território, com quem comparar, quais indicadores e quais partes entram (`Opcoes`). O relatório
traz capa com sumário, resumo, um capítulo por eixo temático com uma ficha por indicador (valor, texto de leitura,
gráfico da evolução e gráfico de comparação), mapas dos municípios (estados) e as fontes.

Os números vêm de src/perfil.py, os mesmos da aba Perfil do Território. O PDF é montado com reportlab (só Python,
sem programas extras no servidor): gráficos e mapas são desenhados em vetor.

Uso:  relatorio.gerar(D, relatorio.Opcoes(tid="Estado:15", comparar=("Estado:13",)))  →  bytes do PDF
"""
from __future__ import annotations

import datetime as dt
import io
import json
import math
import re
from dataclasses import dataclass
from functools import lru_cache
from xml.sax.saxutils import escape

import pandas as pd
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (BaseDocTemplate, CondPageBreak, Flowable, Frame, KeepTogether, NextPageTemplate,
                                PageBreak, PageTemplate, Paragraph, Spacer, Table, TableStyle)

from . import data, fmt, mosaico, perfil, theme
from .data import ASSETS, PARTE_AL

W, H = A4
MX = 36                 # margem lateral
LARG = W - 2 * MX       # largura útil
TOPO, RODAPE = 70, 44   # alturas reservadas ao cabeçalho e ao rodapé das páginas internas

# indicadores dos números-chave do resumo (os que existirem para o território)
CHAVE = ["IND-001", "IND-013", "IND-002", "IND-003", "IND-069", "IND-007"]
# indicadores dos mapas dos municípios (relatório de estado)
MAPAS = ["IND-001", "IND-069", "IND-003", "IND-036"]
# partes do relatório que a pessoa liga e desliga na aba Relatório: chave → (rótulo, ligada por padrão)
SECOES = {
    "resumo": ("Resumo: números-chave e placar por eixo", True),
    "destaques": ("Pontos fortes e pontos de atenção", True),
    "como_ler": ("Quadro \"Como ler este relatório\"", True),
    "texto": ("Texto de leitura de cada indicador", True),
    "evolucao": ("Gráfico da evolução de cada indicador", True),
    "comparacao": ("Gráfico de comparação de cada indicador", True),
    "tabela": ("Tabela-resumo no início de cada eixo", False),
    "mapas": ("Mapas dos municípios (relatório de estado)", True),
    "fontes": ("Fontes dos indicadores", True),
}
FICHA = ("texto", "evolucao", "comparacao")  # o que compõe a ficha de cada indicador
REFS = ("acima", "al", "brasil")  # nível acima do território (região ou estado), Amazônia Legal, Brasil


@dataclass(frozen=True)
class Opcoes:
    tid: str                                  # território do relatório (ex.: 'Estado:15', 'Município:1504208')
    parte: bool = False                       # estado só em parte na Amazônia Legal: usa a parcela na região
    comparar: tuple[str, ...] = ()            # outros territórios do mesmo tipo, lado a lado nos gráficos e textos
    refs: tuple[str, ...] = REFS              # referências mostradas (ver REFS)
    inds: tuple[str, ...] | None = None       # indicadores (None: todos com dado para o território)
    secoes: tuple[str, ...] = tuple(k for k, (_, ligada) in SECOES.items() if ligada)


# cores das linhas e barras: o território, os comparados e as referências
PALETA_COMP = ["#EE7D22", "#0968B1", "#8A5CF5", "#9A6A4C"]
COR_REF = {"acima": "#D49A12", "al": "#16A3A0", "brasil": "#8E9A93"}

# cor de cada eixo, pelo número (a de assets/indicators.json, quando houver; senão a da paleta)
CORES_EIXO = ["#F9C80E", "#F58220", "#18A86B", "#19A7A5", "#1687D9", "#0D5B8F", "#8A5CF5", "#5C6770", "#C8462B"]


# preposição antes do nome de cada estado ("do Pará", "de Rondônia", "da Bahia")
PREP_UF = {"AC": "do", "AL": "de", "AP": "do", "AM": "do", "BA": "da", "CE": "do", "DF": "do", "ES": "do", "GO": "de",
           "MA": "do", "MT": "de", "MS": "de", "MG": "de", "PA": "do", "PB": "da", "PR": "do", "PE": "de", "PI": "do",
           "RJ": "do", "RN": "do", "RS": "do", "RO": "de", "RR": "de", "SC": "de", "SP": "de", "SE": "de", "TO": "do"}
ARTIGO = {"Amazônia Legal": "a", "Brasil": "o"}


def com_artigo(nome: str) -> str:
    """'a Amazônia Legal', 'o Brasil', 'a Região Norte'; os demais nomes ficam como estão."""
    art = ARTIGO.get(nome) or ("a" if nome.startswith("Região ") else "")
    return f"{art} {nome}" if art else nome


def de(nome: str, uf: str | None = None) -> str:
    """'da Amazônia Legal', 'do Brasil', 'do Pará' (com a UF), 'de Marabá'."""
    if uf:
        return f"{PREP_UF.get(uf, 'de')} {nome}"
    art = ARTIGO.get(nome) or ("a" if nome.startswith("Região ") else "")
    return {"a": "da", "o": "do"}.get(art, "de") + " " + nome


def lista(nomes) -> str:
    nomes = list(nomes)
    return nomes[0] if len(nomes) == 1 else ", ".join(nomes[:-1]) + " e " + nomes[-1]


def C(h: str):
    return colors.HexColor(h)


INK, TEXT, MUTED = C(theme.INK), C(theme.TEXT), C(theme.MUTED)
CREME, CARTAO, BEGE = C(theme.BG), C(theme.CARD), C(theme.NAV)
MELHOR, PIOR = C(theme.MELHOR), C(theme.PIOR)
LINHA = C("#D9D3BC")
SEQ = [C(c) for c in theme.SEQ]


# --------------------------------------------------------------------------- #
# fontes e estilos
# --------------------------------------------------------------------------- #
@lru_cache(maxsize=1)
def _fontes() -> bool:
    for nome, arq in (("Mont", "Regular"), ("Mont-SB", "SemiBold"), ("Mont-B", "Bold"), ("Mont-XB", "ExtraBold")):
        pdfmetrics.registerFont(TTFont(nome, str(ASSETS / "fonts" / f"Montserrat-{arq}.ttf")))
    pdfmetrics.registerFontFamily("Mont", normal="Mont", bold="Mont-B", italic="Mont", boldItalic="Mont-B")
    return True


def _estilo(nome, fonte="Mont", tam=8.5, cor=TEXT, ent=None, **kw) -> ParagraphStyle:
    return ParagraphStyle(nome, fontName=fonte, fontSize=tam, leading=ent or tam * 1.35, textColor=cor, **kw)


ST = {
    "h1": _estilo("h1", "Mont-XB", 19, INK, 23, spaceAfter=4),
    "h2": _estilo("h2", "Mont-B", 11.5, INK, 15, spaceBefore=8, spaceAfter=4),
    "p": _estilo("p", tam=8.5, ent=12.5, spaceAfter=4),
    "pm": _estilo("pm", tam=7.4, cor=MUTED, ent=10),
    "cel": _estilo("cel", tam=6.9, ent=8.6),
    "celb": _estilo("celb", "Mont-SB", 6.9, TEXT, 8.6),
    "celm": _estilo("celm", tam=5.9, cor=MUTED, ent=7.2),
    "celr": _estilo("celr", tam=6.9, ent=8.6, alignment=TA_RIGHT),
    "celc": _estilo("celc", tam=6.9, ent=8.6, alignment=TA_CENTER),
    "cab": _estilo("cab", "Mont-B", 6.1, colors.white, 7.4),
    "cabr": _estilo("cabr", "Mont-B", 6.1, colors.white, 7.4, alignment=TA_RIGHT),
    "kl": _estilo("kl", "Mont-B", 6.3, MUTED, 8),
    "fn": _estilo("fn", "Mont-B", 10, INK, 12.5),
    "fu": _estilo("fu", tam=6.8, cor=MUTED, ent=8.6),
    "fv": _estilo("fv", "Mont-XB", 15, INK, 18, alignment=TA_RIGHT),
    "ft": _estilo("ft", tam=7.8, ent=10.8, spaceBefore=2),
    "fg": _estilo("fg", "Mont-B", 6.4, MUTED, 8),
    "kv": _estilo("kv", "Mont-XB", 15, TEXT, 18),
    "ks": _estilo("ks", tam=6.6, cor=MUTED, ent=8.4),
}


def _p(txt: str, st: str = "p") -> Paragraph:
    return Paragraph(txt, ST[st])


def _e(t) -> str:
    return escape(str(t))


# --------------------------------------------------------------------------- #
# desenhos (minigráfico, barra do placar, mapa)
# --------------------------------------------------------------------------- #
class Minigrafico(Flowable):
    """Linha da evolução do território, com o último ponto marcado."""

    def __init__(self, anos, valores, w=36, h=14, cor=INK):
        super().__init__()
        self.pts, self.w, self.h, self.cor = list(zip(anos, valores)), w, h, cor

    def wrap(self, *_):
        return self.w, self.h

    def draw(self):
        if len(self.pts) < 2:
            return
        xs, ys = [float(a) for a, _ in self.pts], [float(v) for _, v in self.pts]
        x0, x1, lo, hi = min(xs), max(xs), min(ys), max(ys)
        span = max(hi - lo, .02 * max(abs(hi), abs(lo)), 1e-12)  # variação mínima não estica na altura toda
        mid = (hi + lo) / 2
        px = lambda x: (x - x0) / ((x1 - x0) or 1) * (self.w - 3) + 1.5  # noqa: E731
        py = lambda y: ((y - mid) / span + .5) * (self.h - 4) + 2  # noqa: E731
        c = self.canv
        c.setStrokeColor(self.cor)
        c.setLineWidth(.9)
        c.setLineJoin(1)
        p = c.beginPath()
        p.moveTo(px(xs[0]), py(ys[0]))
        for x, y in zip(xs[1:], ys[1:]):
            p.lineTo(px(x), py(y))
        c.drawPath(p, stroke=1, fill=0)
        c.setFillColor(self.cor)
        c.circle(px(xs[-1]), py(ys[-1]), 1.4, stroke=0, fill=1)


class BarraPlacar(Flowable):
    """Barra empilhada: quantos indicadores estão melhor (verde), pior (vermelho) ou sem juízo (bege)."""

    def __init__(self, melhor, pior, neutro, w=110, h=7):
        super().__init__()
        self.v, self.w, self.h = (melhor, pior, neutro), w, h

    def wrap(self, *_):
        return self.w, self.h

    def draw(self):
        tot = sum(self.v) or 1
        x = 0
        for n, cor in zip(self.v, (MELHOR, PIOR, BEGE)):
            if n:
                self.canv.setFillColor(cor)
                self.canv.rect(x, 0, n / tot * self.w, self.h, stroke=0, fill=1)
                x += n / tot * self.w


class Marca(Flowable):
    """Marcador invisível: registra em que página começa uma seção (para o sumário da capa)."""

    def __init__(self, secao: str):
        super().__init__()
        self.secao = secao

    def wrap(self, *_):
        return 0, 0

    def draw(self):
        pass


class Amostra(Flowable):
    """Quadrado de cor da legenda dos mapas."""

    def __init__(self, cor, lado=8):
        super().__init__()
        self.cor, self.lado = cor, lado

    def wrap(self, *_):
        return self.lado, self.lado

    def draw(self):
        self.canv.setFillColor(self.cor)
        self.canv.rect(0, 0, self.lado, self.lado, stroke=0, fill=1)


def _ticks(lo: float, hi: float, n: int = 4) -> list[float]:
    """Marcas 'redondas' do eixo de valores (1, 2, 2,5 ou 5 × potência de 10) cobrindo de lo a hi."""
    if hi == lo:
        d = abs(hi) * .1 or 1
        lo, hi = lo - d, hi + d
    bruto = (hi - lo) / n
    mag = 10 ** math.floor(math.log10(bruto))
    passo = next(m * mag for m in (1, 2, 2.5, 5, 10) if m * mag >= bruto * .999)
    v, fim, out = math.floor(lo / passo) * passo, math.ceil(hi / passo) * passo, []
    while v <= fim + passo * 1e-6:
        out.append(round(v, 10))
        v += passo
    return out


def _corta(texto: str, fonte: str, tam: float, largura: float) -> str:
    while pdfmetrics.stringWidth(texto, fonte, tam) > largura and len(texto) > 4:
        texto = texto[:-2].rstrip() + "…"
    return texto


class GraficoEvolucao(Flowable):
    """Linhas ano a ano: o território (linha grossa), os comparados e as referências (Brasil tracejado)."""

    def __init__(self, linhas: list[dict], ik, w: float, h: float):
        super().__init__()
        self.linhas, self.ik, self.w, self.h = linhas, ik, w, h

    def wrap(self, *_):
        return self.w, self.h

    def draw(self):
        c, ik = self.canv, self.ik
        pts = [(a, v) for ln in self.linhas for a, v in zip(ln["anos"], ln["vals"]) if not fmt.isna(v)]
        if not pts:
            return
        anos = sorted({int(a) for a, _ in pts})
        vs = [v for _, v in pts]
        ticks = _ticks(min(vs), max(vs))
        rot = [re.sub(r",0+(?!\d)", "", ik.fmt(t)) for t in ticks]  # "90%" em vez de "90,00%"
        esq = max(pdfmetrics.stringWidth(r, "Mont", 6) for r in rot) + 5
        x0, x1, y0, y1 = esq, self.w - 6, 12, self.h - 4
        lo, hi = ticks[0], ticks[-1]
        px = lambda a: x0 + (a - anos[0]) / ((anos[-1] - anos[0]) or 1) * (x1 - x0)  # noqa: E731
        py = lambda v: y0 + (v - lo) / ((hi - lo) or 1) * (y1 - y0)  # noqa: E731
        c.setFont("Mont", 6)
        for t, r in zip(ticks, rot):
            c.setStrokeColor(C("#ECE7D6"))
            c.setLineWidth(.4)
            c.line(x0, py(t), x1, py(t))
            c.setFillColor(MUTED)
            c.drawRightString(x0 - 3, py(t) - 2, r)
        passo = max(1, math.ceil(len(anos) / 7))
        marcas = anos[::passo] + ([anos[-1]] if (len(anos) - 1) % passo else [])
        for a in marcas:
            c.drawCentredString(px(a), 2, str(a))
        for ln in sorted(self.linhas, key=lambda ln: ln.get("grossa", False)):  # o território por cima
            c.setStrokeColor(C(ln["cor"]))
            c.setFillColor(C(ln["cor"]))
            c.setLineWidth(1.8 if ln.get("grossa") else 1)
            c.setDash(*([2.2, 1.6] if ln.get("tracejada") else []))
            serie = [(int(a), v) for a, v in zip(ln["anos"], ln["vals"])]
            trecho = []
            for a, v in serie + [(None, float("nan"))]:
                if a is not None and not fmt.isna(v):
                    trecho.append((px(a), py(v)))
                    continue
                if len(trecho) > 1:
                    pth = c.beginPath()
                    pth.moveTo(*trecho[0])
                    for xy in trecho[1:]:
                        pth.lineTo(*xy)
                    c.drawPath(pth, stroke=1, fill=0)
                elif len(trecho) == 1:
                    c.circle(*trecho[0], 1.3, stroke=0, fill=1)
                trecho = []
            c.setDash()
            ult = [(a, v) for a, v in serie if not fmt.isna(v)]
            if ult and ln.get("grossa"):
                c.circle(px(ult[-1][0]), py(ult[-1][1]), 2, stroke=0, fill=1)


class GraficoBarras(Flowable):
    """Barras horizontais com o valor de cada território no mesmo ano (o do relatório em destaque)."""

    def __init__(self, itens: list[tuple[str, float, str, bool]], ik, w: float, h: float):
        super().__init__()
        self.itens, self.ik, self.w, self.h = itens, ik, w, h

    def wrap(self, *_):
        return self.w, self.h

    def draw(self):
        c, ik = self.canv, self.ik
        itens = self.itens
        vs = [v for _, v, _, _ in itens if not fmt.isna(v)]
        if not vs:
            return
        rots = [ik.fmt(v) for _, v, _, _ in itens]
        nome_w = min(90, max(pdfmetrics.stringWidth(n, "Mont-B", 6.4) for n, *_ in itens) + 8)
        val_w = max(pdfmetrics.stringWidth(r, "Mont-B", 6.4) for r in rots) + 4
        x0, x1 = nome_w, self.w - val_w
        lo, hi = min(0, min(vs)), max(0, max(vs))
        px = lambda v: x0 + (v - lo) / ((hi - lo) or 1) * (x1 - x0)  # noqa: E731
        linha = min(16, (self.h - 4) / len(itens))
        barra = min(9, linha * .62)
        topo = self.h - 2 - (self.h - 4 - linha * len(itens)) / 2
        c.setStrokeColor(C("#CFC8AE"))
        c.setLineWidth(.5)
        c.line(px(0), topo - linha * len(itens), px(0), topo)
        for i, ((nome, v, cor, destaque), r) in enumerate(zip(itens, rots)):
            yc = topo - linha * (i + .5)
            c.setFillColor(INK if destaque else TEXT)
            c.setFont("Mont-B" if destaque else "Mont", 6.4)
            c.drawRightString(x0 - 4, yc - 2.2, _corta(nome, "Mont-B" if destaque else "Mont", 6.4, nome_w - 5))
            if fmt.isna(v):
                c.setFillColor(MUTED)
                c.setFont("Mont", 6)
                c.drawString(px(0) + 3, yc - 2, "sem dado")
                continue
            c.setFillColor(C(cor))
            a, b = sorted((px(0), px(v)))
            c.rect(a, yc - barra / 2, max(b - a, .6), barra, stroke=0, fill=1)
            c.setFillColor(INK if destaque else TEXT)
            c.setFont("Mont-B" if destaque else "Mont", 6.4)
            c.drawString(max(px(v), px(0)) + 3, yc - 2.2, r)


class Legenda(Flowable):
    """Amostras de cor e nomes das séries dos gráficos, numa ou mais linhas."""

    def __init__(self, itens: list[tuple[str, str, bool, bool]], w: float):
        super().__init__()
        self.itens, self.w = itens, w
        self._pos = []
        x, y = 0, 0
        for nome, *_ in itens:
            larg = 16 + pdfmetrics.stringWidth(nome, "Mont", 6.4) + 12
            if x + larg > w and x:
                x, y = 0, y + 10
            self._pos.append((x, y))
            x += larg
        self.h = y + 9

    def wrap(self, *_):
        return self.w, self.h

    def draw(self):
        c = self.canv
        for (nome, cor, grossa, tracejada), (x, y) in zip(self.itens, self._pos):
            yy = self.h - y - 6
            c.setStrokeColor(C(cor))
            c.setLineWidth(1.8 if grossa else 1.1)
            c.setDash(*([2.2, 1.6] if tracejada else []))
            c.line(x, yy + 2, x + 12, yy + 2)
            c.setDash()
            c.setFillColor(INK if grossa else TEXT)
            c.setFont("Mont-B" if grossa else "Mont", 6.4)
            c.drawString(x + 16, yy, nome)


@lru_cache(maxsize=2)
def _geo(nome: str) -> dict:
    """Anéis de cada polígono por código IBGE (uf.json: 2 dígitos; mun.json: 7 dígitos)."""
    g = json.loads((ASSETS / "geo" / f"{nome}.json").read_text())
    out = {}
    for f in g["features"]:
        geo = f["geometry"]
        polis = [geo["coordinates"]] if geo["type"] == "Polygon" else geo["coordinates"]
        out[int(f["properties"]["codarea"])] = [p[0] for p in polis]  # só o anel externo
    return out


class Mapa(Flowable):
    """Mapa simples em vetor: {código: cor} sobre os polígonos de uf.json ou mun.json."""

    def __init__(self, base: str, cores: dict, w: float, h: float, contorno=colors.white, espessura=.3):
        super().__init__()
        self.base, self.cores, self.w, self.h, self.contorno, self.esp = base, cores, w, h, contorno, espessura

    def wrap(self, *_):
        return self.w, self.h

    def draw(self):
        geo = _geo(self.base)
        aneis = [(cod, a) for cod in self.cores if cod in geo for a in geo[cod]]
        if not aneis:
            return
        lons = [x for _, a in aneis for x, _ in a]
        lats = [y for _, a in aneis for _, y in a]
        k = math.cos(math.radians((min(lats) + max(lats)) / 2))  # projeção simples: encurta a longitude
        x0, x1, y0, y1 = min(lons) * k, max(lons) * k, min(lats), max(lats)
        esc = min(self.w / ((x1 - x0) or 1), self.h / ((y1 - y0) or 1))
        dx, dy = (self.w - (x1 - x0) * esc) / 2, (self.h - (y1 - y0) * esc) / 2
        c = self.canv
        c.setStrokeColor(self.contorno)
        c.setLineWidth(self.esp)
        c.setLineJoin(1)
        for cod, anel in aneis:
            c.setFillColor(self.cores[cod])
            p = c.beginPath()
            for i, (lon, lat) in enumerate(anel):
                xy = (dx + (lon * k - x0) * esc, dy + (lat - y0) * esc)
                p.moveTo(*xy) if i == 0 else p.lineTo(*xy)
            p.close()
            c.drawPath(p, stroke=1, fill=1)


# --------------------------------------------------------------------------- #
# dados do relatório
# --------------------------------------------------------------------------- #
def _num_eixo(eixo: str) -> int:
    try:
        return int(eixo.split(".", 1)[0])
    except ValueError:
        return 0


def _cor_eixo(D: dict, eixo: str) -> str:
    n = _num_eixo(eixo)
    cor = next((c for nome, c in D.get("axis_colors", {}).items() if _num_eixo(nome) == n), None)
    return cor or CORES_EIXO[(n - 1) % len(CORES_EIXO)]


def _desc_eixo(D: dict, eixo: str) -> str:
    n = _num_eixo(eixo)
    return next((d for nome, d in D.get("axis_desc", {}).items() if _num_eixo(nome) == n), "")


def _sit_brasil(ik, ln) -> int:
    """Melhor (1) ou pior (−1) que o Brasil, para taxas e médias com polaridade; 0 sem juízo."""
    if ik.additive or not ik.polarity:
        return 0
    return ik.situacao(ik.diff(ln.valor, ln.refs.get(perfil.BRASIL, float("nan"))))


def _tipo_ref(tid: str) -> str:
    return {perfil.AMZ: "al", perfil.BRASIL: "brasil"}.get(tid, "acima")


class Territorio:
    """Tudo o que o relatório usa de um território: identificação, referências, comparados e as linhas de cada eixo."""

    def __init__(self, D: dict, op: Opcoes):
        L = D["long"]
        tid, parte = op.tid, op.parte
        self.D, self.op, self.tid, self.parte = D, op, tid, parte
        self.plvl, cod = tid.split(":")
        self.cod = int(cod)
        r = L[L.tid == tid].iloc[0]
        self.nome = str(r.nome)
        self.uf = str(r.uf) if self.plvl in ("Estado", "Município") else None
        self.regiao = str(r.regiao) if pd.notna(r.regiao) else ""
        self.al = bool(r.al) if pd.notna(r.al) else False
        self.titulo = self.nome + (f" ({self.uf})" if self.plvl == "Município" else "")
        self.de_nome = de(self.nome, self.uf if self.plvl == "Estado" else None)  # "do Pará", "de Marabá"
        if parte:
            self.titulo += " · parte na Amazônia Legal"
        self.refs = perfil.referencias(D, self.plvl, self.cod)
        self.comp_tid, self.comp_nome = perfil.referencia_principal(self.refs)
        self.refs_vis = [(n, tt) for n, tt in self.refs if _tipo_ref(tt) in op.refs]  # as mostradas
        nomes = L[L.tid.isin(list(op.comparar))].drop_duplicates("tid").set_index("tid").label.astype(str)
        self.comparar = [(nomes[c], c) for c in op.comparar if c in nomes.index and c != tid]
        # UF de cada estado citado nos textos, para a preposição ("do Pará", "de Rondônia")
        self._uf_estado = {self.nome if self.plvl == "Estado" else self.refs[0][0]: self.uf} if self.uf else {}
        if self.plvl == "Estado":
            ufs = L[L.tid.isin([c for _, c in self.comparar])].drop_duplicates("tid")
            self._uf_estado |= dict(zip(ufs.nome.astype(str), ufs.uf.astype(str)))
        REG = D["registry"]
        sel = [k for k in D["indicators"]
               if (op.inds is None or k in op.inds) and self.plvl in D["meta"][k]["levels"]]
        if not sel:
            raise ValueError("Nenhum indicador escolhido existe para este tipo de território.")
        self.sel = set(sel)
        calc = tuple(k for k in D["indicators"] if k in self.sel or k in CHAVE)  # números-chave entram sempre
        self.por_k = {ln.k: ln for ln in perfil.linhas(D, tid, self.plvl, self.uf, self.refs, parte, calc)}
        self.linhas = [self.por_k[k] for k in sel]
        self.eixos = sorted({REG[k].axis for k in sel}, key=_num_eixo)
        # posição usada nos destaques: entre os estados da região, os municípios do estado ou os pares do Brasil
        self.estado_nome = self.refs[0][0] if self.plvl == "Município" else self.nome
        self.pos_nome = {"Estado": "entre os estados da Amazônia Legal",
                         "Município": f"entre os municípios {de(self.estado_nome, self.uf)}"
                         }.get(self.plvl, "entre os territórios do mesmo tipo no Brasil")

    def de(self, nome: str) -> str:
        """'do Pará', 'da Amazônia Legal', 'de Marabá (PA)'."""
        return de(nome, self._uf_estado.get(nome))

    def pos(self, ln):
        return ln.pos_al if self.plvl == "Estado" else ln.pos_uf if self.plvl == "Município" else ln.pos_br

    def do_eixo(self, eixo: str):
        REG = self.D["registry"]
        return [ln for ln in self.linhas if REG[ln.k].axis == eixo]

    def fora_do_nivel(self, eixo: str) -> list[str]:
        """Indicadores do eixo que não existem para este tipo de território (ex.: só por estado). Só quando o eixo
        entra inteiro no relatório: com uma escolha feita a dedo, a lista não interessa."""
        REG, D = self.D["registry"], self.D
        do_eixo = [k for k in D["indicators"] if REG[k].axis == eixo]
        if any(k not in self.sel for k in do_eixo if self.plvl in D["meta"][k]["levels"]):
            return []
        return [REG[k].label for k in do_eixo if self.plvl not in D["meta"][k]["levels"]]

    def series(self, k: str) -> tuple[str, pd.DataFrame]:
        """Séries do território (ou da sua parcela na Amazônia Legal), dos comparados e das referências mostradas."""
        principal = f"{PARTE_AL}:{self.cod}" if self.parte and k in self.D["al_parte_ind"] else self.tid
        tids = [principal] + [c for _, c in self.comparar] + [r for _, r in self.refs_vis]
        return principal, data.series(perfil.fatia(self.D, k), tids, k)

    def caracteristicas(self) -> list[str]:
        D = self.D
        out = [self.plvl]
        if self.plvl == "Estado":
            n_mun = int(D["long"].loc[(D["long"].nivel == "Município") & (D["long"].uf == self.uf), "cod"].nunique())
            out += [self.uf, f"Região {self.regiao}"]
            if self.uf in D["al_parcial"]:
                a, t = D["al_parcial"][self.uf]
                out.append(f"Amazônia Legal só em parte: {a} de {t} municípios")
            else:
                out.append("Amazônia Legal" if self.uf in D["al_ufs"] else "Fora da Amazônia Legal")
            out.append(f"{n_mun} municípios")
        elif self.plvl == "Município":
            out += [self.uf, f"Região {self.regiao}", "Amazônia Legal" if self.al else "Fora da Amazônia Legal"]
            if D["porte"] is not None:
                out.append("Porte: " + str(D["porte"].get(self.cod, "—")))
            cr = D["carac"].loc[self.cod] if D["carac"] is not None and self.cod in D["carac"].index else None
            if cr is not None:
                out += [f"Região imediata: {cr.rg_imediata}", f"Região intermediária: {cr.rg_intermediaria}"]
                out += ["Município de fronteira"] * bool(cr.fronteira) + ["Sede de região imediata"] * bool(cr.sede_imediata)
        return out


# --------------------------------------------------------------------------- #
# páginas: capa, cabeçalho e rodapé
# --------------------------------------------------------------------------- #
@lru_cache(maxsize=1)
def _mosaico_capa() -> ImageReader:
    from PIL import Image
    m = mosaico.compor(160)  # 160 px por ícone: ~300 dpi na largura da página
    fundo = Image.new("RGB", m.size, theme.BG)
    fundo.paste(m, mask=m.split()[3])
    buf = io.BytesIO()
    fundo.save(buf, "JPEG", quality=88)
    buf.seek(0)
    return ImageReader(buf)


def _img(caminho):
    return ImageReader(str(caminho))


class Documento(BaseDocTemplate):
    def __init__(self, buf, t: Territorio, gerado: str):
        super().__init__(buf, pagesize=A4, leftMargin=MX, rightMargin=MX, topMargin=TOPO, bottomMargin=RODAPE,
                         title=f"Relatório do território: {t.titulo}", author="SUDAM · PNUD · Instituto Publix",
                         subject="Diagnóstico Quantitativo da Amazônia Legal")
        self.t, self.gerado = t, gerado
        self.paginas: dict = {}   # seção → página, registrada nesta montagem
        self.sumario: dict = {}   # seção → página, da montagem anterior (desenhado na capa)
        capa = Frame(MX, RODAPE, LARG, H - RODAPE - 40, id="capa")
        corpo = Frame(MX, RODAPE, LARG, H - TOPO - RODAPE, id="corpo", topPadding=4)
        self.addPageTemplates([PageTemplate("capa", [capa], onPage=self._capa),
                               PageTemplate("corpo", [corpo], onPage=self._pagina)])

    def afterFlowable(self, f):
        if isinstance(f, Marca):
            self.paginas.setdefault(f.secao, self.page)

    # capa: fundo creme, mosaico com os logos, marca do projeto, nome do território e mapa de localização
    def _capa(self, c, doc):
        t = self.t
        c.saveState()
        c.setFillColor(CREME)
        c.rect(0, 0, W, H, stroke=0, fill=1)
        mos = _mosaico_capa()
        mw, mh = mos.getSize()
        lado = W / mosaico.LARGURA
        alt = W * mh / mw
        c.drawImage(mos, 0, H - alt, W, alt)
        # cartão dos logos sobre a fileira do meio, como no topo do painel
        cw, ch = 8.75 * lado, 1.3 * lado
        cy = H - .9 * lado - ch
        c.setFillColor(C(theme.SIDEBAR))
        c.roundRect(W - cw, cy, cw + 12, ch, 10, stroke=0, fill=1)
        ass = _img(ASSETS / "logos" / "assinatura.png")
        aw, ah = ass.getSize()
        lh = ch * .62
        c.drawImage(ass, W - cw / 2 - lh * aw / ah / 2, cy + (ch - lh) / 2, lh * aw / ah, lh, mask="auto")
        # marca do projeto
        y = H - alt - 92
        c.drawImage(_img(ASSETS / "logos" / "emblema.png"), MX, y, 62, 62, mask="auto")
        c.setFillColor(INK)
        c.setFont("Mont-B", 10.5)
        for i, linha in enumerate(["Apoio à Execução,", "Monitoramento e Gestão do", "Plano Regional de",
                                   "Desenvolvimento da Amazônia"]):
            c.drawString(MX + 74, y + 50 - i * 13, linha)
        c.setStrokeColor(INK)
        c.setLineWidth(.7)
        c.line(MX + 74, y + 6, MX + 74 + 168, y + 6)
        c.setFont("Mont", 6.2)
        c.drawString(MX + 74, y - 3, "Superintendência do Desenvolvimento da Amazônia")
        # título
        y -= 70
        c.setFillColor(MUTED)
        c.setFont("Mont-B", 10)
        c.drawString(MX, y, "DIAGNÓSTICO QUANTITATIVO DA AMAZÔNIA LEGAL")
        c.setFillColor(INK)
        c.setFont("Mont-XB", 15)
        c.drawString(MX, y - 26, "Relatório do território")
        tam = 38 if len(t.titulo) <= 22 else 30 if len(t.titulo) <= 30 else 24
        c.setFont("Mont-XB", tam)
        c.drawString(MX, y - 26 - tam * 1.15, t.titulo)
        c.setFillColor(TEXT)
        c.setFont("Mont", 8.5)
        yy = y - 26 - tam * 1.15 - 22
        for linha in _quebra(" · ".join(t.caracteristicas()), "Mont", 8.5, LARG * .55):
            c.drawString(MX, yy, linha)
            yy -= 12
        if t.comparar:
            c.setFont("Mont-B", 8.5)
            c.setFillColor(INK)
            for linha in _quebra("Comparado com: " + " · ".join(n for n, _ in t.comparar), "Mont-B", 8.5, LARG * .55):
                c.drawString(MX, yy, linha)
                yy -= 12
        # sumário, com as páginas da montagem anterior
        if self.sumario:
            yy -= 18
            c.setFillColor(INK)
            c.setFont("Mont-B", 9)
            c.drawString(MX, yy, "Neste relatório")
            yy -= 4
            itens = [("Resumo", self.sumario.get("resumo"))]
            itens += [(f"Eixo {s.split(':', 1)[1].split('. ', 1)[0]} · {s.split('. ', 1)[-1]}", pg)
                      for s, pg in self.sumario.items() if s.startswith("eixo:")]
            itens += [(f"Municípios {t.de_nome}", self.sumario.get("mapas")),
                      ("Fontes dos indicadores", self.sumario.get("fontes"))]
            larg = W - 2 * MX - 250
            for nome, pg in itens:
                if pg is None:
                    continue
                yy -= 13.5
                c.setStrokeColor(LINHA)
                c.setLineWidth(.4)
                c.line(MX, yy - 4, MX + larg, yy - 4)
                c.setFillColor(TEXT)
                c.setFont("Mont", 7.8)
                while pdfmetrics.stringWidth(nome, "Mont", 7.8) > larg - 24 and len(nome) > 10:
                    nome = nome[:-2].rstrip() + "…"  # corta até caber, terminando em reticências
                c.drawString(MX, yy, nome)
                c.setFont("Mont-B", 7.8)
                c.setFillColor(INK)
                c.drawRightString(MX + larg, yy, str(pg))
        # mapa de localização: o estado entre os da Amazônia Legal, ou o município no seu estado
        D = t.D
        if t.plvl == "Estado":
            comp = {int(c.split(":")[1]): C(PALETA_COMP[i % len(PALETA_COMP)]) for i, (_, c) in enumerate(t.comparar)}
            ufs = set(_codigos_uf(D, D["al_ufs"] + ([t.uf] if t.uf not in D["al_ufs"] else []))) | set(comp)
            cores = {u: (INK if u == t.cod else comp.get(u, C("#CFE3C9"))) for u in ufs}
            mapa, rotulo = Mapa("uf", cores, 230, 230, CREME, .8), "Estados da Amazônia Legal"
        elif t.plvl == "Município":
            muns = [m for m in _geo("mun") if m // 100000 == t.cod // 100000]
            comp = {int(c.split(":")[1]): C(PALETA_COMP[i % len(PALETA_COMP)]) for i, (_, c) in enumerate(t.comparar)}
            cores = {m: (INK if m == t.cod else comp.get(m, C("#CFE3C9"))) for m in muns}
            mapa, rotulo = Mapa("mun", cores, 230, 230, CREME, .35), f"Municípios de {t.uf}"
        else:
            mapa = None
        if mapa:
            mapa.wrapOn(c, 230, 230)
            mapa.drawOn(c, W - MX - 230, RODAPE + 70)
            c.setFillColor(MUTED)
            c.setFont("Mont", 7)
            c.drawRightString(W - MX, RODAPE + 58, f"{rotulo} · em destaque: {t.nome}"
                              + (" (verde-escuro) e os comparados" if t.comparar else ""))
        # rodapé da capa
        c.setFillColor(MUTED)
        c.setFont("Mont", 7.5)
        c.drawString(MX, RODAPE + 16, f"Gerado em {self.gerado} a partir do painel do Diagnóstico Quantitativo da "
                                      "Amazônia Legal")
        c.drawString(MX, RODAPE + 5, f"Base de dados: versão {D['manifest'].get('versao', '—')} · Projeto BRA/21/005 · "
                                     "SUDAM · PNUD · Instituto Publix")
        c.restoreState()

    # páginas internas: faixa de cores no alto, marca à esquerda, território à direita e rodapé com a página
    def _pagina(self, c, doc):
        t = self.t
        c.saveState()
        seg = W / len(mosaico.CORES_FAIXA)
        for i, cor in enumerate(mosaico.CORES_FAIXA):
            c.setFillColor(C(cor))
            c.rect(i * seg, H - 5, seg + .5, 5, stroke=0, fill=1)
        c.drawImage(_img(ASSETS / "logos" / "emblema.png"), MX, H - 46, 26, 26, mask="auto")
        c.setFillColor(INK)
        c.setFont("Mont-B", 8)
        c.drawString(MX + 33, H - 31, "Diagnóstico Quantitativo da Amazônia Legal")
        c.setFillColor(MUTED)
        c.setFont("Mont", 7)
        c.drawString(MX + 33, H - 41, "Relatório do território")
        c.setFillColor(INK)
        c.setFont("Mont-B", 9)
        c.drawRightString(W - MX, H - 31, t.titulo)
        c.setFillColor(MUTED)
        c.setFont("Mont", 7)
        c.drawRightString(W - MX, H - 41, " · ".join(t.caracteristicas()[:3]))
        c.setStrokeColor(LINHA)
        c.setLineWidth(.6)
        c.line(MX, H - 52, W - MX, H - 52)
        c.line(MX, RODAPE - 12, W - MX, RODAPE - 12)
        c.setFont("Mont", 6.5)
        c.drawString(MX, RODAPE - 24, f"Gerado em {self.gerado} · base {t.D['manifest'].get('versao', '—')} · "
                                      "SUDAM · PNUD · Instituto Publix")
        c.setFont("Mont-B", 7)
        c.setFillColor(INK)
        c.drawRightString(W - MX, RODAPE - 24, str(doc.page))
        c.restoreState()


def _quebra(texto: str, fonte: str, tam: float, largura: float) -> list[str]:
    linhas, atual = [], ""
    for parte in texto.split(" · "):
        prox = f"{atual} · {parte}" if atual else parte
        if pdfmetrics.stringWidth(prox, fonte, tam) > largura and atual:
            linhas.append(atual)
            atual = parte
        else:
            atual = prox
    return linhas + [atual] if atual else linhas


def _codigos_uf(D: dict, ufs) -> list[int]:
    L = D["long"]
    e = L[(L.nivel == "Estado") & L.uf.isin(list(ufs))].drop_duplicates("cod")
    return sorted(int(c) for c in e.cod)


# --------------------------------------------------------------------------- #
# seções
# --------------------------------------------------------------------------- #
def _fmt_var(ik, ln) -> str:
    if fmt.isna(ln.variacao):
        if ln.ano0 is not None and ln.ano0 < ln.ano and ln.valor0 == 0:
            return f'<font color="{theme.MUTED}">era zero em {ln.ano0}</font>'
        return f'<font color="{theme.MUTED}">só um ano</font>' if ln.ano0 == ln.ano else "—"
    r = round(ln.variacao, ik.diff_decimals)
    seta = "▲" if r > 0 else "▼" if r < 0 else "="
    cor = {1: theme.MELHOR, -1: theme.PIOR}.get(ik.situacao(ln.variacao), theme.TEXT)
    return (f'<font color="{cor}"><b>{seta} {_e(ik.fmt_diff(ln.variacao))}</b></font><br/>'
            f'<font size="5.9" color="{theme.MUTED}">desde {ln.ano0}</font>')


def _fmt_comp(ik, ln) -> str:
    if ln.comp_tipo == "participacao":
        return "—" if ln.comp is None else f"{fmt.pct(ln.comp)} do total{_e(ln.comp_sufixo)}"
    if ln.comp_tipo == "diferenca":
        cor = {1: theme.MELHOR, -1: theme.PIOR}.get(ln.situacao, theme.TEXT)
        return f'<font color="{cor}"><b>{_e(ik.fmt_diff(ln.comp))}</b></font>'
    return "—"


def _como_ler(t: Territorio) -> list:
    pos = {"Estado": "entre os estados da Amazônia Legal", "Município": f"entre os municípios do estado ({t.uf})"
           }.get(t.plvl, "entre os territórios do mesmo tipo no Brasil")
    outros = [n for n, _ in t.comparar] + [n for n, _ in t.refs_vis]
    itens = [
        "<b>Valor</b>: o do último ano com dado do território para cada indicador"
        + (f"; {_e(lista(outros))} aparecem no mesmo ano." if outros else "."),
        f"<b>Posição</b>: {pos}; 1º é a melhor situação conforme o sentido do indicador (sem sentido definido, 1º é o "
        "maior valor). \"=\" indica empate.",
        f"<b>Comparação</b>: para totais (somas), a participação do território no total {_e(de(t.comp_nome))}; "
        "para taxas e médias, quanto está acima ou abaixo de cada referência, em pontos percentuais (p.p.), pontos de "
        "índice ou %.",
        "<b>Gráficos</b>: a linha mais grossa é o território do relatório; o Brasil aparece tracejado. Nos totais "
        "(somas), as referências ficam fora dos gráficos, porque a escala delas é muito maior; o texto traz a "
        "participação.",
        "<b>Variação</b>: do primeiro ano com dado até o ano do valor. Em séries com mudança de método, só dentro do "
        "mesmo trecho.",
        f'<font color="{theme.MELHOR}"><b>Verde</b></font> = situação melhor; <font color="{theme.PIOR}"><b>vermelho</b>'
        "</font> = pior, conforme o sentido do indicador. Sem cor: totais e indicadores sem sentido definido.",
    ]
    if t.D["al_parcial"]:
        itens.append("<b>Amazônia Legal</b>: soma ou média dos seus municípios; "
                     + "; ".join(f"{_e(u)} entra com {a} de {n} municípios" for u, (a, n) in t.D["al_parcial"].items())
                     + ".")
    caixa = Table([[_p("Como ler este relatório", "h2")]] + [[_p("• " + i, "pm")] for i in itens],
                  colWidths=[LARG])
    caixa.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), C("#F3EFDE")), ("LEFTPADDING", (0, 0), (-1, -1), 10),
                               ("RIGHTPADDING", (0, 0), (-1, -1), 10), ("TOPPADDING", (0, 0), (-1, -1), 1.5),
                               ("BOTTOMPADDING", (0, 0), (-1, -1), 1.5), ("BOTTOMPADDING", (0, -1), (-1, -1), 8),
                               ("TOPPADDING", (0, 0), (-1, 0), 2)]))
    return [Spacer(1, 8), KeepTogether([caixa])]


def _resumo(t: Territorio) -> list:
    D, REG = t.D, t.D["registry"]
    sec = t.op.secoes
    if not {"resumo", "destaques", "como_ler"} & set(sec):
        return []
    com = [ln for ln in t.linhas if ln.tem_dado]
    outros = [n for n, _ in t.comparar] + [com_artigo(n) for n, _ in t.refs_vis]
    out = [Marca("resumo"), _p("Resumo", "h1"),
           _p(f"Este relatório reúne <b>{len(com)} indicador{'es' if len(com) != 1 else ''}</b> do painel com dado "
              f"para <b>{_e(t.titulo)}</b>, em {len(t.eixos)} eixo{'s' if len(t.eixos) != 1 else ''} temático"
              f"{'s' if len(t.eixos) != 1 else ''} do PRDA. Cada indicador aparece no último ano com dado do território"
              + (f" e é comparado com {_e(lista(outros))}." if outros else "."))]
    if "resumo" not in sec:
        return out + (_destaques(t) if "destaques" in sec else []) + (_como_ler(t) if "como_ler" in sec else [])
    # números-chave
    cartoes = []
    for k in CHAVE:
        ln = t.por_k.get(k)
        if not ln or not ln.tem_dado:
            continue
        ik = REG[k]
        if ik.additive and ln.comp is not None:
            sub = f"{ln.ano} · {fmt.pct(ln.comp)} do total {de(t.comp_nome)}"
        else:
            refs = [f"{n.replace('Amazônia Legal', 'AL')}: {ik.fmt(ln.refs[tt])}" for n, tt in t.refs
                    if n in ("Amazônia Legal", "Brasil") and not fmt.isna(ln.refs.get(tt, float("nan")))]
            sub = f"{ln.ano} · " + " · ".join(refs)
        cartoes.append([_p(_e(ik.label.upper()), "kl"), _p(_e(ik.fmt(ln.valor)), "kv"), _p(_e(sub), "ks")])
    if cartoes:
        n_col = 3
        cel = [Table([[x] for x in c], colWidths=[LARG / n_col - 14]) for c in cartoes]
        for x in cel:
            x.setStyle(TableStyle([("LEFTPADDING", (0, 0), (-1, -1), 0), ("TOPPADDING", (0, 0), (-1, -1), 1),
                                   ("BOTTOMPADDING", (0, 0), (-1, -1), 1)]))
        grade = [cel[i:i + n_col] + [""] * (n_col - len(cel[i:i + n_col])) for i in range(0, len(cel), n_col)]
        tg = Table(grade, colWidths=[LARG / n_col] * n_col)
        estilo = [("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 10),
                  ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6)]
        for i in range(len(cel)):
            r, cc = divmod(i, n_col)
            estilo += [("BACKGROUND", (cc, r), (cc, r), CARTAO), ("BOX", (cc, r), (cc, r), 2.5, colors.white)]
        tg.setStyle(TableStyle(estilo))
        out += [_p("Números-chave", "h2"), tg]

    # placar por eixo
    linhas = [[_p("Eixo temático", "cab"), _p("Indicadores com dado", "cabr"),
               _p(f"Melhor / pior que {_e(t.comp_nome)}", "cab"), "", _p("Melhor / pior que o Brasil", "cab"), ""]]
    for eixo in t.eixos:
        ls = [ln for ln in t.do_eixo(eixo) if ln.tem_dado]
        if not ls:
            continue
        sa = [ln.situacao for ln in ls]
        sb = [_sit_brasil(REG[ln.k], ln) for ln in ls]
        linha = [_p(_e(eixo), "cel"), _p(str(len(ls)), "celr")]
        for s in (sa, sb):
            m, p = s.count(1), s.count(-1)
            linha += [BarraPlacar(m, p, len(s) - m - p, 70),
                      _p(f'<font color="{theme.MELHOR}"><b>{m}</b></font> / <font color="{theme.PIOR}"><b>{p}</b></font>',
                         "cel")]
        linhas.append(linha)
    tp = Table(linhas, colWidths=[LARG - 62 - 2 * 118, 62, 78, 40, 78, 40], repeatRows=1)
    tp.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), INK), ("SPAN", (2, 0), (3, 0)), ("SPAN", (4, 0), (5, 0)),
                            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("ROWBACKGROUNDS", (0, 1), (-1, -1),
                                                                     [colors.white, C("#FBF8EE")]),
                            ("LINEBELOW", (0, 1), (-1, -1), .4, LINHA), ("TOPPADDING", (0, 0), (-1, -1), 3),
                            ("BOTTOMPADDING", (0, 0), (-1, -1), 3)]))
    out += [_p("Placar por eixo", "h2"),
            _p("Quantos indicadores do eixo estão em situação melhor ou pior que a referência, conforme o sentido de "
               "cada um. A parte bege da barra são os totais e os indicadores sem sentido definido, que não entram "
               "nessa conta.", "pm"), Spacer(1, 4), tp]
    return out + (_destaques(t) if "destaques" in sec else []) + (_como_ler(t) if "como_ler" in sec else [])


def _destaques(t: Territorio) -> list:
    REG = t.D["registry"]
    cand = []
    for ln in t.linhas:
        ik, pos = REG[ln.k], t.pos(ln)
        if not ln.tem_dado or ik.additive or not ik.polarity or not pos or pos[2] < 3 or pos[1] / pos[2] > .2:
            continue
        cand.append(((pos[0] - 1) / (pos[2] - 1), ln, pos))
    fortes = [x for x in sorted(cand, key=lambda x: (x[0], x[2][0])) if x[0] <= 1 / 3][:5]
    fracos = [x for x in sorted(cand, key=lambda x: (-x[0], -x[2][0])) if x[0] >= 2 / 3][:5]

    def destaques(itens, vazio):
        if not itens:
            return [_p(vazio, "pm")]
        return [_p(f"<b>{_e(REG[ln.k].label)}</b>: {_e(REG[ln.k].fmt(ln.valor))} em {ln.ano} · "
                   f"{_e(perfil.pos_txt(pos))}", "cel") for _, ln, pos in itens]

    td = Table([[_p(f'<font color="{theme.MELHOR}">Pontos fortes</font>', "h2"),
                 _p(f'<font color="{theme.PIOR}">Pontos de atenção</font>', "h2")],
                [destaques(fortes, "Nenhum indicador no terço de cima."), destaques(fracos, "Nenhum indicador no terço de baixo.")]],
               colWidths=[LARG / 2] * 2)
    td.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0),
                            ("RIGHTPADDING", (0, 0), (0, -1), 12)]))
    return [KeepTogether([_p("Destaques", "h2"),
                          _p(f"Taxas e médias em que {_e(t.titulo)} está entre as melhores ou as piores posições "
                             f"{_e(t.pos_nome)} (terço de cima e de baixo do ranking). Totais e indicadores sem sentido "
                             "definido não entram.", "pm"), Spacer(1, 2), td])]


def _colunas(t: Territorio):
    """(cabeçalho, largura, alinhamento) de cada coluna da tabela dos eixos."""
    refs = [(n.replace("Região ", ""), 46) for n, _ in t.refs_vis]
    pos = {"Estado": "Posição na AL", "Município": "Posição no estado"}.get(t.plvl, "Posição no Brasil")
    fixas = [("Ano", 27)] + [("Valor", 49)] + refs + [(pos, 47), (f"× {t.comp_nome}", 52), ("Variação", 52),
                                                       ("Evolução", 38)]
    return [("Indicador", LARG - sum(w for _, w in fixas))] + fixas


def _eixo(t: Territorio, eixo: str) -> list:
    D, REG = t.D, t.D["registry"]
    ls = t.do_eixo(eixo)
    com = [ln for ln in ls if ln.tem_dado]
    sem = [REG[ln.k].label for ln in ls if not ln.tem_dado]
    fora = t.fora_do_nivel(eixo)
    cor = _cor_eixo(D, eixo)
    letra = "#FFFFFF" if theme.text_on(cor) == "#FFFFFF" else theme.INK
    n = _num_eixo(eixo)
    titulo = eixo.split(". ", 1)[-1]
    faixa = Table([[_p(f'<font color="{letra}" size="8"><b>EIXO {n}</b></font>', "p")],
                   [_p(f'<font color="{letra}" size="15"><b>{_e(titulo)}</b></font>', "h1")]], colWidths=[LARG])
    faixa.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), C(cor)), ("LEFTPADDING", (0, 0), (-1, -1), 12),
                               ("TOPPADDING", (0, 0), (-1, 0), 9), ("BOTTOMPADDING", (0, -1), (-1, -1), 10),
                               ("TOPPADDING", (0, 1), (-1, 1), 0), ("BOTTOMPADDING", (0, 0), (-1, 0), 0)]))
    out = [Marca(f"eixo:{eixo}"), faixa, Spacer(1, 6)]
    desc = _desc_eixo(D, eixo)
    sa = [ln.situacao for ln in com]
    resumo = (f"{len(com)} indicador{'es' if len(com) != 1 else ''} com dado para {_e(t.titulo)}"
              + (f' · <font color="{theme.MELHOR}"><b>{sa.count(1)}</b> melhor{"es" if sa.count(1) != 1 else ""}</font> e '
                 f'<font color="{theme.PIOR}"><b>{sa.count(-1)}</b> pior{"es" if sa.count(-1) != 1 else ""}</font> que '
                 f"{_e(com_artigo(t.comp_nome))}" if any(sa) else "") + ".")
    out += [_p((_e(desc) + " " if desc else "") + resumo, "p"), Spacer(1, 4)]
    if com and "tabela" in t.op.secoes:
        cols = _colunas(t)
        cab = [_p(_e(nome), "cab" if i == 0 else "cabr") for i, (nome, _) in enumerate(cols)]
        linhas = [cab]
        for ln in com:
            ik = REG[ln.k]
            valor = _e(ik.fmt(ln.valor)) + ('<br/><font size="5.6" color="%s">estado inteiro</font>' % theme.MUTED
                                            if ln.estado_inteiro else "")
            pos = t.pos(ln)
            linha = [[_p(f"<b>{_e(ik.label)}</b>", "cel"), _p(_e(ik.unit), "celm")], _p(str(ln.ano), "celr"),
                     _p(f"<b>{valor}</b>", "celr")]
            linha += [_p(_e(ik.fmt(ln.refs.get(tt, float("nan")))), "celr") for _, tt in t.refs_vis]
            linha += [_p(_e(perfil.pos_txt(pos)) if pos else "—", "celr"), _p(_fmt_comp(ik, ln), "celr"),
                      _p(_fmt_var(ik, ln), "celr"),
                      Minigrafico(ln.serie.ano, ln.serie.valor, cols[-1][1] - 6) if len(ln.serie) > 1
                      else _p("—", "celc")]
            linhas.append(linha)
        tab = Table(linhas, colWidths=[w for _, w in cols], repeatRows=1)
        tab.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), INK), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                                 ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, C("#FBF8EE")]),
                                 ("LINEBELOW", (0, 1), (-1, -1), .4, LINHA),
                                 ("LEFTPADDING", (0, 0), (-1, -1), 3), ("RIGHTPADDING", (0, 0), (-1, -1), 3),
                                 ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                                 ("LEFTPADDING", (0, 0), (0, -1), 5), ("ALIGN", (-1, 1), (-1, -1), "CENTER")]))
        out += [tab, Spacer(1, 10)]
    if set(FICHA) & set(t.op.secoes):
        out += [_ficha(t, ln) for ln in com]
    notas = []
    if sem:
        notas.append(f"<b>Sem dado para {_e(t.titulo)}</b>: {_e('; '.join(sem))}.")
    if fora:
        nivel = {"Estado": "estados", "Município": "municípios", "Grande Região": "Grandes Regiões"}.get(t.plvl, "este nível")
        notas.append(f"<b>Não existem para {nivel}</b>: {_e('; '.join(fora))}.")
    if notas:
        out += [Spacer(1, 6)] + [_p(x, "pm") for x in notas]
    return out


def _ao(nome: str) -> str:
    art = ARTIGO.get(nome) or ("a" if nome.startswith("Região ") else "")
    return {"a": "à", "o": "ao"}.get(art, "a") + " " + nome


def _leitura(t: Territorio, ln, ik, valores: dict) -> str:
    """Frases sobre o indicador: comparação com as referências, posição, variação e territórios comparados."""
    cor = lambda sit: {1: theme.MELHOR, -1: theme.PIOR}.get(sit, theme.TEXT)  # noqa: E731
    frases = []
    if ln.estado_inteiro:
        frases.append("Valor do estado inteiro: o indicador não existe só para a parte na Amazônia Legal.")
    if ik.additive:
        if ln.comp is not None and _tipo_ref(t.comp_tid or "") in t.op.refs:
            frases.append(f"Corresponde a <b>{fmt.pct(ln.comp)} do total</b> {_e(de(t.comp_nome))}"
                          f"{_e(ln.comp_sufixo)}.")
    else:
        partes = []
        for n, tt in t.refs_vis:
            vr = ln.refs.get(tt, float("nan"))
            if fmt.isna(vr):
                continue
            d = ik.diff(ln.valor, vr)
            if fmt.isna(d) or round(d, ik.diff_decimals) == 0:
                partes.append(f"igual {_e(_ao(n))} ({_e(ik.fmt(vr))})")
            else:
                partes.append(f'<font color="{cor(ik.situacao(d))}"><b>{_e(ik.fmt_diff(abs(d)).lstrip("+"))} '
                              f'{"acima" if d > 0 else "abaixo"}</b></font> {_e(t.de(n))} ({_e(ik.fmt(vr))})')
        if partes:
            frases.append("Está " + lista(partes) + ".")
    pos = t.pos(ln)
    if pos:
        regra = "1º = melhor situação" if ik.polarity else "1º = maior valor"
        frases.append(f"Posição <b>{_e(perfil.pos_txt(pos))}</b> {_e(t.pos_nome)} ({regra}).")
    if not fmt.isna(ln.variacao):
        r = round(ln.variacao, ik.diff_decimals)
        seta = "▲" if r > 0 else "▼" if r < 0 else "="
        frases.append(f'Desde {ln.ano0}, variou <font color="{cor(ik.situacao(ln.variacao))}"><b>{seta} '
                      f"{_e(ik.fmt_diff(ln.variacao))}</b></font>.")
    elif ln.ano0 == ln.ano:
        frases.append("Só há um ano com dado comparável para o território.")
    comp = {n: v for n, v in valores.items() if not fmt.isna(v)}
    if len(comp) > 2:
        hi, lo = max(comp, key=comp.get), min(comp, key=comp.get)
        frases.append(f"Entre os territórios comparados, o maior valor é {_e(t.de(hi))} ({_e(ik.fmt(comp[hi]))}) e o "
                      f"menor, {_e(t.de(lo))} ({_e(ik.fmt(comp[lo]))}).")
    elif len(comp) == 2:
        (n1, v1), (n2, v2) = comp.items()
        d = ik.diff(v1, v2)
        if not fmt.isna(d) and round(d, ik.diff_decimals):
            frases.append(f"Em relação a {_e(n2)} ({_e(ik.fmt(v2))}), está <b>{_e(ik.fmt_diff(abs(d)).lstrip('+'))} "
                          f"{'acima' if d > 0 else 'abaixo'}</b>.")
    return " ".join(frases)


def _ficha(t: Territorio, ln) -> Flowable:
    """Ficha de um indicador: nome e valor, texto de leitura, gráfico da evolução e gráfico de comparação."""
    REG, sec = t.D["registry"], t.op.secoes
    ik = REG[ln.k]
    principal, s = t.series(ln.k)
    # quem entra nos gráficos: o território, os comparados e, fora dos totais, as referências
    quem = [(t.titulo if not t.parte else t.nome, principal, theme.INK, True, False)]
    quem += [(n, c, PALETA_COMP[i % len(PALETA_COMP)], False, False) for i, (n, c) in enumerate(t.comparar)]
    if not ik.additive:
        quem += [(n, r, COR_REF[_tipo_ref(r)], False, _tipo_ref(r) == "brasil") for n, r in t.refs_vis]
    ult = s[s.ano == ln.ano]
    no_ano = dict(zip(ult.tid, ult.valor))  # valor de cada um no ano do relatório
    valores = {n: no_ano.get(tid, float("nan")) for n, tid, *_ in quem[:1 + len(t.comparar)]}

    valor = _e(ik.fmt(ln.valor))
    cab = Table([[[_p(f"<b>{_e(ik.label)}</b>", "fn"), _p(_e(ik.unit), "fu")],
                  _p(f'<font name="Mont-XB" size="15" color="{theme.INK}">{valor}</font>'
                     f'<font size="7" color="{theme.MUTED}">  {ln.ano}</font>', "fv")]],
                colWidths=[LARG - 24 - 150, 150])
    cab.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0),
                             ("RIGHTPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 2)]))
    corpo = [cab]
    if "texto" in sec:
        txt = _leitura(t, ln, ik, valores)
        if txt:
            corpo.append(_p(txt, "ft"))
    graficos, largs = [], []
    serie_ok = s[s.tid == principal].valor.notna().sum() > 1
    if "evolucao" in sec and serie_ok:
        linhas = []
        for nome, tid, cor, grossa, trac in quem:
            sx = s[s.tid == tid]
            if sx.valor.notna().any():
                linhas.append({"anos": list(sx.ano), "vals": list(sx.valor), "cor": cor, "grossa": grossa,
                               "tracejada": trac})
        graficos.append([_p("Evolução", "fg"), GraficoEvolucao(linhas, ik, LARG * .56, 86)])
        largs.append(LARG * .56 + 4)
    if "comparacao" in sec and len(quem) > 1:
        itens = [(nome, no_ano.get(tid, float("nan")), cor, grossa) for nome, tid, cor, grossa, _ in quem]
        w = LARG - 24 - sum(largs) - (8 if largs else 0)
        graficos.append([_p(f"Comparação em {ln.ano}", "fg"),
                         GraficoBarras(itens, ik, w, max(40, min(86, 12 * len(itens) + 6)))])
        largs.append(w)
    if graficos:
        g = Table([graficos], colWidths=largs)
        g.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0),
                               ("RIGHTPADDING", (0, 0), (-1, -1), 8), ("TOPPADDING", (0, 0), (-1, -1), 4)]))
        corpo.append(g)
        corpo.append(Legenda([(nome, cor, grossa, trac) for nome, _, cor, grossa, trac in quem], LARG - 24))
        if ik.additive and t.refs_vis:
            corpo.append(_p("Total (soma): " + _e(lista(n for n, _ in t.refs_vis)) + " ficam fora dos gráficos, porque a "
                            "escala é muito maior.", "fu"))
    elif "evolucao" in sec and not serie_ok and "texto" not in sec:
        corpo.append(_p("Só há um ano com dado para o território.", "fu"))
    caixa = Table([[x] for x in corpo], colWidths=[LARG])
    caixa.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), C("#FCFAF2")), ("BOX", (0, 0), (-1, -1), .5, LINHA),
                               ("LEFTPADDING", (0, 0), (-1, -1), 12), ("RIGHTPADDING", (0, 0), (-1, -1), 12),
                               ("TOPPADDING", (0, 0), (-1, -1), 2), ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
                               ("TOPPADDING", (0, 0), (-1, 0), 9), ("BOTTOMPADDING", (0, -1), (-1, -1), 9)]))
    return KeepTogether([caixa, Spacer(1, 8)])


def _mapas_municipios(t: Territorio) -> list:
    """Relatório de estado: quatro mapas dos municípios, em faixas de valor (mais escuro = maior)."""
    D, REG = t.D, t.D["registry"]
    paineis = []
    for k in MAPAS:
        if k not in REG or "Município" not in D["meta"][k]["levels"]:
            continue
        ik = REG[k]
        ano = None
        for a in reversed(data.years_with_data(D, k)):
            s = data.snapshot(D, "Município", k, a, ufs=[t.uf])
            if len(s) >= .8 * len(s.drop_duplicates("cod")) and len(s) > 3:
                ano = a
                break
        if ano is None:
            continue
        s = s.set_index("cod").valor
        b = data.bands(s)
        cores = {int(c): SEQ[min(int(i) * (len(SEQ) - 1) // max(int(b.max()), 1), len(SEQ) - 1)] for c, i in b.items()}
        todos = [m for m in _geo("mun") if m // 100000 == t.cod]
        cores = {m: cores.get(m, C("#E8E4D4")) for m in todos}
        faixas = data.band_ranges(s)
        n_f = max(int(b.max()), 1)
        leg = [[Amostra(SEQ[min(i * (len(SEQ) - 1) // n_f, len(SEQ) - 1)]),
                _p(f"{_e(ik.fmt(lo))} a {_e(ik.fmt(hi))} <font color='{theme.MUTED}'>({n})</font>", "celm")]
               for i, (lo, hi, n) in enumerate(faixas)]
        tl = Table(leg, colWidths=[12, LARG / 2 - 40])
        tl.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("LEFTPADDING", (0, 0), (-1, -1), 0),
                                ("TOPPADDING", (0, 0), (-1, -1), .5), ("BOTTOMPADDING", (0, 0), (-1, -1), .5)]))
        paineis.append([_p(f"<b>{_e(ik.label)}</b> · {ano}", "cel"), Mapa("mun", cores, LARG / 2 - 20, 175), tl])
    if not paineis:
        return []
    cel = []
    for pn in paineis:
        x = Table([[c] for c in pn], colWidths=[LARG / 2 - 14])
        x.setStyle(TableStyle([("LEFTPADDING", (0, 0), (-1, -1), 0), ("TOPPADDING", (0, 0), (-1, -1), 2)]))
        cel.append(x)
    grade = [cel[i:i + 2] + [""] * (2 - len(cel[i:i + 2])) for i in range(0, len(cel), 2)]
    tg = Table(grade, colWidths=[LARG / 2] * 2)
    tg.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("BOTTOMPADDING", (0, 0), (-1, -1), 10)]))
    return [Marca("mapas"), _p(f"Municípios {_e(t.de_nome)}", "h1"),
            _p("Como os indicadores se distribuem dentro do estado: cada mapa divide os municípios em faixas de "
               "valor com número parecido de municípios (entre parênteses, quantos em cada faixa); mais escuro = "
               "valor maior. Cinza: sem dado.", "p"), Spacer(1, 6), tg]


def _anexo(t: Territorio) -> list:
    D, REG = t.D, t.D["registry"]
    linhas = [[_p("Indicador", "cab"), _p("Unidade", "cab"), _p("Fonte", "cab")]]
    for eixo in t.eixos:
        for ln in t.do_eixo(eixo):
            if ln.tem_dado:
                m = D["meta"][ln.k]
                linhas.append([_p(_e(REG[ln.k].label), "cel"), _p(_e(REG[ln.k].unit), "celm"),
                               _p(_e(m.get("source", "—")), "celm")])
    tab = Table(linhas, colWidths=[LARG * .38, LARG * .2, LARG * .42], repeatRows=1)
    tab.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), INK), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                             ("LINEBELOW", (0, 1), (-1, -1), .3, LINHA), ("TOPPADDING", (0, 0), (-1, -1), 2),
                             ("BOTTOMPADDING", (0, 0), (-1, -1), 2)]))
    return [Marca("fontes"), _p("Fontes dos indicadores", "h1"),
            _p("Unidade e fonte de cada indicador presente no relatório. As fichas técnicas completas (fórmula, "
               "periodicidade, regra de agregação e observações) estão na aba Sobre o Painel.", "p"), Spacer(1, 4), tab]


# --------------------------------------------------------------------------- #
# montagem
# --------------------------------------------------------------------------- #
def gerar(D: dict, op: Opcoes) -> bytes:
    """PDF do relatório descrito em `op` (território, comparados, referências, indicadores e partes)."""
    _fontes()
    t = Territorio(D, op)
    gerado = dt.date.today().strftime("%d/%m/%Y")

    def historia() -> list:
        hist = [Spacer(1, 1), NextPageTemplate("corpo"), PageBreak()]
        resumo = _resumo(t)
        hist += resumo
        for i, eixo in enumerate(e for e in t.eixos if any(ln.tem_dado for ln in t.do_eixo(e))):
            # o 1º eixo só pula de página se faltar espaço: quando o "Como ler" do resumo não cabe na página dele, o
            # eixo começa logo abaixo, sem deixar uma página quase vazia
            hist += ([CondPageBreak(H * .45) if i == 0 else PageBreak()] if resumo or i else []) + _eixo(t, eixo)
        if t.plvl == "Estado" and "mapas" in op.secoes:
            mp = _mapas_municipios(t)
            hist += ([PageBreak()] + mp) if mp else []
        return hist + (([PageBreak()] + _anexo(t)) if "fontes" in op.secoes else [])

    # 1ª montagem: só descobre em que página começa cada seção; a 2ª desenha o sumário da capa com elas
    rascunho = Documento(io.BytesIO(), t, gerado)
    rascunho.build(historia())
    buf = io.BytesIO()
    doc = Documento(buf, t, gerado)
    doc.sumario = rascunho.paginas
    doc.build(historia())
    return buf.getvalue()


def n_paginas(pdf: bytes) -> int:
    return len(re.findall(rb"/Type /Page[^s]", pdf))


def estimar_paginas(por_eixo: list[int], secoes, estado: bool) -> int:
    """Páginas aproximadas, antes de gerar: capa, resumo, fichas (3 por página com gráficos, 6 só com texto),
    tabelas, mapas e fontes."""
    sec = set(secoes)
    graf = bool({"evolucao", "comparacao"} & sec)
    por_pag = 3 if graf else 6 if "texto" in sec else 0
    p = 1 + (1 if {"resumo", "destaques"} & sec else 0)
    for n in por_eixo:
        p += max(1, (math.ceil(n / por_pag) if por_pag else 0) + (math.ceil(n / 24) if "tabela" in sec else 0))
    p += (1 if estado and "mapas" in sec else 0) + (math.ceil(sum(por_eixo) / 45) if "fontes" in sec else 0)
    return p
