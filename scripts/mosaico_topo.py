"""Gera o mosaico do topo do painel (assets/brand/mosaico_topo.webp) a partir dos ícones da identidade visual.

A montagem (ícones, posições e faixa de cores) fica em src/mosaico.py, a mesma usada na capa do relatório em PDF.

Executar:  python scripts/mosaico_topo.py
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src import mosaico  # noqa: E402

SAIDA = ROOT / "assets" / "brand" / "mosaico_topo.webp"
LADO = 76  # lado de cada ícone na imagem (o painel mostra com metade: 38 px, nítido em telas de alta densidade)


def main():
    img = mosaico.compor(LADO)
    SAIDA.parent.mkdir(parents=True, exist_ok=True)
    img.save(SAIDA, "WEBP", quality=88, method=6)
    print(f"{SAIDA.relative_to(ROOT)}: {img.size[0]}x{img.size[1]}, {SAIDA.stat().st_size / 1024:.0f} KB")


if __name__ == "__main__":
    main()
