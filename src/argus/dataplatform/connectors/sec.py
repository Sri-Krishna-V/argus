"""SEC EDGAR connector: recent filings for the configured watchlist via the official
submissions API. Respects SEC fair-access rules (descriptive User-Agent, ~10 req/s)."""

import logging
import time
from datetime import UTC, datetime

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from argus.core.config import get_settings
from argus.dataplatform.connectors.base import DocumentRef
from argus.knowledge.models import Company

log = logging.getLogger(__name__)

RECENT_PER_COMPANY = 5


class SecEdgarConnector:
    name = "sec_edgar"

    def __init__(self, session: Session):
        self.session = session  # watchlist tickers resolve against canonical companies

    def _client(self) -> httpx.Client:
        return httpx.Client(
            headers={"User-Agent": get_settings().sec_user_agent}, timeout=30
        )

    def _watchlist_ciks(self) -> list[tuple[str, str]]:
        settings = get_settings()
        rows = self.session.execute(
            select(Company.cik, Company.name).where(
                Company.tickers.overlap(settings.sec_watchlist), Company.cik.is_not(None)
            )
        ).all()
        return [(cik, name) for cik, name in rows]

    def discover(self) -> list[DocumentRef]:
        settings = get_settings()
        refs: list[DocumentRef] = []
        with self._client() as client:
            for cik, company_name in self._watchlist_ciks():
                try:
                    data = (
                        client.get(f"https://data.sec.gov/submissions/CIK{int(cik):010d}.json")
                        .raise_for_status()
                        .json()
                    )
                except httpx.HTTPError:
                    # one bad company must not kill the pass (docs/RISKS.md #5)
                    log.exception("submissions fetch failed", extra={"context": {"cik": cik}})
                    continue
                recent = data["filings"]["recent"]
                taken = 0
                for i, form in enumerate(recent["form"]):
                    if form not in settings.sec_filing_types:
                        continue
                    accession = recent["accessionNumber"][i]
                    primary = recent["primaryDocument"][i]
                    if not primary:
                        continue
                    refs.append(
                        DocumentRef(
                            source=self.name,
                            native_id=accession,
                            doc_type="filing",
                            url=(
                                f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/"
                                f"{accession.replace('-', '')}/{primary}"
                            ),
                            title=f"{company_name} {form} {recent['filingDate'][i]}",
                            publisher=company_name,
                            published_at=datetime.strptime(
                                recent["filingDate"][i], "%Y-%m-%d"
                            ).replace(tzinfo=UTC),
                            extra={"form": form, "cik": cik},
                        )
                    )
                    taken += 1
                    if taken >= RECENT_PER_COMPANY:
                        break
                time.sleep(0.15)  # SEC fair-access pacing
        return refs

    def fetch(self, ref: DocumentRef) -> bytes:
        with self._client() as client:
            content = client.get(ref.url).raise_for_status().content
        time.sleep(0.15)
        return content
