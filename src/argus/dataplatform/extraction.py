"""Deterministic entity extraction with precision guards (docs/RISKS.md #1).

Tickers match only in cashtag/exchange contexts — never bare words, because tickers
like A, IT, ALL would tag everything. Names/aliases match case-sensitively on word
boundaries with a minimum length."""

import re
from dataclasses import dataclass

MIN_NAME_LEN = 4

CASHTAG = re.compile(r"\$([A-Z]{1,5})\b")
EXCHANGE_TICKER = re.compile(
    r"\((?:NYSE|NASDAQ|Nasdaq|AMEX|NYSE American|CBOE)\s*:\s*([A-Z][A-Z.\-]{0,5})\)"
)


@dataclass(frozen=True)
class Mention:
    text: str
    start: int
    end: int
    company_id: str  # canonical company UUID (as str)


class CompanyMatcher:
    """Built once from the canonical companies table, reused across documents.

    ponytail: single alternation regex — fine for ~10k names at V1 volume;
    switch to pyahocorasick if matching shows up in pipeline_runs latency.
    """

    def __init__(self, companies: list[tuple[str, str, list[str], list[str]]]):
        """companies: (id, name, tickers, aliases)"""
        self.by_ticker: dict[str, str] = {}
        names: list[tuple[str, str]] = []  # (surface form, company_id)
        for cid, name, tickers, aliases in companies:
            for t in tickers:
                self.by_ticker.setdefault(t.upper(), cid)
            for surface in [name, *aliases]:
                if len(surface) >= MIN_NAME_LEN:
                    names.append((surface, cid))
        # longest-first so "Apple Inc." wins over "Apple" at the same position;
        # case-insensitive because registry names are ALL CAPS ("NVIDIA CORP") while
        # prose writes "Nvidia Corp" — but the in-text mention must be capitalized,
        # which rejects "apple pie" without losing "NVIDIA" or "Apple".
        names.sort(key=lambda n: len(n[0]), reverse=True)
        self.by_name = {n.lower(): cid for n, cid in reversed(names)}
        # lookarounds, not \b: names ending in "." (Apple Inc.) have no word boundary
        # after the period, so \b would silently drop the longest surface form
        self.name_re = (
            re.compile(
                r"(?<!\w)(" + "|".join(re.escape(n) for n, _ in names) + r")(?!\w)",
                re.IGNORECASE,
            )
            if names
            else None
        )

    def find(self, text: str) -> list[Mention]:
        found: list[Mention] = []
        claimed: set[int] = set()

        def claim(start: int, end: int, surface: str, cid: str) -> None:
            if not claimed.intersection(range(start, end)):
                claimed.update(range(start, end))
                found.append(Mention(surface, start, end, cid))

        if self.name_re:
            for m in self.name_re.finditer(text):
                if m.group(1)[0].isupper():
                    claim(m.start(), m.end(), m.group(1), self.by_name[m.group(1).lower()])
        for pattern in (CASHTAG, EXCHANGE_TICKER):
            for m in pattern.finditer(text):
                cid = self.by_ticker.get(m.group(1).upper())
                if cid:
                    claim(m.start(), m.end(), m.group(0), cid)
        return sorted(found, key=lambda x: x.start)
