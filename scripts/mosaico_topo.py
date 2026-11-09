"""Gera o mosaico do topo do painel (assets/brand/mosaico_topo.webp) a partir dos ícones da identidade visual.

Os ícones ficam em assets/id_visual/icons/ (o do lírio, que não veio na pasta de ícones, foi recortado da capa
ident_PRDA_SUDAM_041126_Capa.jpeg); o painel usa só a imagem gerada aqui. Posições, ícones e faixa copiados da arte do
topo enviada pelo design: três fileiras, à esquerda ícones soltos em escada, à direita encostados uns nos outros, e
embaixo a faixa de seis cores da identidade.

Executar:  python scripts/mosaico_topo.py
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
ICONES = ROOT / "assets" / "id_visual" / "icons"
SAIDA = ROOT / "assets" / "brand" / "mosaico_topo.webp"

T = 76          # lado de cada ícone na imagem (o painel mostra com metade: 38 px, nítido em telas de alta densidade)
FAIXA = 14      # altura da faixa colorida (7 px na tela)
DENSO = 6.28    # onde começam os ícones encostados (em lados de ícone, a partir da esquerda)
N_DENSO = 9     # ícones encostados por fileira
CORES_FAIXA = ["#04413C", "#FCC709", "#EB7D22", "#1EA3A0", "#0966AC", "#98D553"]

# ícones soltos à esquerda: (fileira, posição em lados de ícone, número do ícone)
SOLTOS = [(0, 1.79, "capa-lirio"), (0, 3.52, 7), (0, 5.01, 6),
          (1, 1.25, 3), (1, 3.12, 4), (1, 5.28, 8),
          (2, 0.00, 1), (2, 2.28, 2), (2, 4.42, 5)]
# ícones encostados, por fileira (a do meio fica quase toda sob o cartão dos logos)
DENSOS = [[9, 14, 15, 20, 23, 24, 29, 30, 33],
          [10, 13, 16, 19, 22, 25, 28, 31, 34],
          [11, 12, 17, 18, 21, 26, 27, 32, 35]]


def icone(n: int | str) -> Image.Image:
    nome = f"icons_prda_061126-{n:02d}.jpg" if isinstance(n, int) else f"icons_prda_{n}.jpg"
    return Image.open(ICONES / nome).convert("RGB").resize((T, T), Image.LANCZOS)


def main():
    largura = round((DENSO + N_DENSO) * T)
    img = Image.new("RGBA", (largura, 3 * T + FAIXA), (0, 0, 0, 0))
    for fil, x, n in SOLTOS:
        img.paste(icone(n), (round(x * T), fil * T))
    for fil, nums in enumerate(DENSOS):
        for i, n in enumerate(nums):
            img.paste(icone(n), (round((DENSO + i) * T), fil * T))
    seg = largura / len(CORES_FAIXA)
    for i, cor in enumerate(CORES_FAIXA):
        img.paste(Image.new("RGBA", (round(seg * (i + 1)) - round(seg * i), FAIXA), cor), (round(seg * i), 3 * T))
    SAIDA.parent.mkdir(parents=True, exist_ok=True)
    img.save(SAIDA, "WEBP", quality=88, method=6)
    print(f"{SAIDA.relative_to(ROOT)}: {img.size[0]}x{img.size[1]}, {SAIDA.stat().st_size / 1024:.0f} KB")


if __name__ == "__main__":
    main()
