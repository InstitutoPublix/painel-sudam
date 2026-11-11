"""Mosaico de ícones da identidade visual (topo do painel e capa do relatório em PDF).

Os ícones ficam em assets/id_visual/icons/ (o do lírio, que não veio na pasta de ícones, foi recortado da capa
ident_PRDA_SUDAM_041126_Capa.jpeg). Posições, ícones e faixa copiados da arte do topo enviada pelo design: três
fileiras, à esquerda ícones soltos em escada, à direita encostados uns nos outros, e embaixo a faixa de seis cores."""
from __future__ import annotations

from functools import lru_cache

from PIL import Image

from .data import ASSETS

ICONES = ASSETS / "id_visual" / "icons"
DENSO = 6.28    # onde começam os ícones encostados (em lados de ícone, a partir da esquerda)
N_DENSO = 9     # ícones encostados por fileira
LARGURA = DENSO + N_DENSO  # largura do mosaico, em lados de ícone
FAIXA = 7 / 38  # altura da faixa colorida, em lados de ícone (7 px com ícones de 38 px)
CORES_FAIXA = ["#04413C", "#FCC709", "#EB7D22", "#1EA3A0", "#0966AC", "#98D553"]

# ícones soltos à esquerda: (fileira, posição em lados de ícone, número do ícone)
SOLTOS = [(0, 1.79, "capa-lirio"), (0, 3.52, 7), (0, 5.01, 6),
          (1, 1.25, 3), (1, 3.12, 4), (1, 5.28, 8),
          (2, 0.00, 1), (2, 2.28, 2), (2, 4.42, 5)]
# ícones encostados, por fileira (a do meio fica quase toda sob o cartão dos logos)
DENSOS = [[9, 14, 15, 20, 23, 24, 29, 30, 33],
          [10, 13, 16, 19, 22, 25, 28, 31, 34],
          [11, 12, 17, 18, 21, 26, 27, 32, 35]]


def icone(n: int | str, lado: int) -> Image.Image:
    nome = f"icons_prda_061126-{n:02d}.jpg" if isinstance(n, int) else f"icons_prda_{n}.jpg"
    return Image.open(ICONES / nome).convert("RGB").resize((lado, lado), Image.LANCZOS)


@lru_cache(maxsize=4)
def compor(lado: int) -> Image.Image:
    """O mosaico com ícones de `lado` px (fundo transparente onde não há ícone)."""
    largura, faixa = round(LARGURA * lado), round(FAIXA * lado)
    img = Image.new("RGBA", (largura, 3 * lado + faixa), (0, 0, 0, 0))
    for fil, x, n in SOLTOS:
        img.paste(icone(n, lado), (round(x * lado), fil * lado))
    for fil, nums in enumerate(DENSOS):
        for i, n in enumerate(nums):
            img.paste(icone(n, lado), (round((DENSO + i) * lado), fil * lado))
    seg = largura / len(CORES_FAIXA)
    for i, cor in enumerate(CORES_FAIXA):
        img.paste(Image.new("RGBA", (round(seg * (i + 1)) - round(seg * i), faixa), cor), (round(seg * i), 3 * lado))
    return img
