"""Formatação numérica em pt-BR."""
import math


def num(v: float, d: int = 1) -> str:
    s = f"{v:,.{d}f}"
    return s.replace(",", "X").replace(".", ",").replace("X", ".")


def isna(v) -> bool:
    return v is None or (isinstance(v, float) and math.isnan(v))


def compact(v: float, d: int = 1) -> str:
    """1.234.567 -> '1,2 mi'. Abaixo de 1 milhão mostra o número inteiro."""
    a = abs(v)
    for lim, suf in ((1e12, " tri"), (1e9, " bi"), (1e6, " mi")):
        if a >= lim:
            return f"{num(v / lim, d)}{suf}"
    return num(v, 0)


def pct(v: float, d: int = 1, sign: bool = False) -> str:
    if isna(v):
        return "—"
    return f"{'+' if sign and v > 0 else ''}{num(v, d)}%"
