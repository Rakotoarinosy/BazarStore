"""Montant en toutes lettres (français), pour la mention « Arrêtée la présente facture à… »."""

_UNITS = [
    "zéro", "un", "deux", "trois", "quatre", "cinq", "six", "sept", "huit", "neuf", "dix",
    "onze", "douze", "treize", "quatorze", "quinze", "seize", "dix-sept", "dix-huit", "dix-neuf",
]  # fmt: skip
_TENS = {2: "vingt", 3: "trente", 4: "quarante", 5: "cinquante", 6: "soixante"}


def _below_100(n: int) -> str:
    if n < 20:
        return _UNITS[n]
    tens, unit = divmod(n, 10)
    if tens in (7, 9):  # 70-79 = soixante-dix…, 90-99 = quatre-vingt-dix…
        base = "soixante" if tens == 7 else "quatre-vingt"
        rest = _UNITS[10 + unit]
        return f"{base}-et-{rest}" if tens == 7 and unit == 1 else f"{base}-{rest}"
    if tens == 8:
        return "quatre-vingts" if unit == 0 else f"quatre-vingt-{_UNITS[unit]}"
    if unit == 0:
        return _TENS[tens]
    if unit == 1:
        return f"{_TENS[tens]}-et-un"
    return f"{_TENS[tens]}-{_UNITS[unit]}"


def _below_1000(n: int) -> str:
    hundreds, rest = divmod(n, 100)
    if hundreds == 0:
        return _below_100(rest)
    head = "cent" if hundreds == 1 else f"{_UNITS[hundreds]}-cent"
    if rest == 0:
        return head + ("s" if hundreds > 1 else "")
    return f"{head}-{_below_100(rest)}"


def amount_in_words(n: int) -> str:
    """Orthographe rectifiée de 1990 (traits d'union partout), ex. 1 328 000 → un-million-…"""
    if n < 0:
        return "moins-" + amount_in_words(-n)
    if n == 0:
        return "zéro"

    parts: list[str] = []
    for value, singular, plural in (
        (10**9, "milliard", "milliards"),
        (10**6, "million", "millions"),
    ):
        count, n = divmod(n, value)
        if count:
            parts.append(f"{_below_1000(count)}-{singular if count == 1 else plural}")

    thousands, n = divmod(n, 1000)
    if thousands:
        # « mille » est invariable et ne prend pas « un » devant ; « cents/vingts » perdent le s.
        prefix = "" if thousands == 1 else _below_1000(thousands).removesuffix("s") + "-"
        parts.append(f"{prefix}mille")
    if n:
        parts.append(_below_1000(n))
    return "-".join(parts)
