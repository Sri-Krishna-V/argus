"""Precision guards from docs/RISKS.md #1: bare tickers never match; names need
word boundaries, min length, and capitalization."""

from argus.dataplatform.extraction import CompanyMatcher

COMPANIES = [
    ("id-agilent", "Agilent Technologies Inc", ["A"], ["Agilent"]),
    ("id-gartner", "Gartner Inc", ["IT"], ["Gartner"]),
    ("id-nvidia", "NVIDIA CORP", ["NVDA"], ["NVIDIA"]),
    ("id-apple", "Apple Inc.", ["AAPL"], ["Apple"]),
]


def matcher() -> CompanyMatcher:
    return CompanyMatcher(COMPANIES)


def test_bare_ticker_words_do_not_match():
    text = "A great IT department is all you need."
    assert matcher().find(text) == []


def test_cashtag_and_exchange_context_match():
    found = matcher().find("Buy $NVDA now; Agilent (NYSE: A) also reported.")
    assert {m.company_id for m in found} == {"id-nvidia", "id-agilent"}


def test_names_match_case_insensitively_but_require_capitalization():
    found = matcher().find("Nvidia Corp and NVIDIA both shipped; an apple pie did not.")
    assert {m.company_id for m in found} == {"id-nvidia"}
    assert len(found) == 2


def test_longest_name_wins_and_offsets_are_correct():
    text = "Apple Inc. announced earnings."
    found = matcher().find(text)
    assert len(found) == 1
    assert found[0].company_id == "id-apple"
    assert text[found[0].start : found[0].end] == "Apple Inc."


def test_word_boundaries():
    assert matcher().find("Pineapples and NVIDIAX are not companies.") == []
