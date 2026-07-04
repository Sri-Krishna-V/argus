"""Company profiles connector: SEC's official ticker registry seeds the canonical
companies table (the entity-resolution target), and each daily snapshot is kept as a
document for provenance."""

import json
import re
from datetime import UTC, datetime

import httpx
from sqlalchemy.orm import Session

from argus.core.config import get_settings
from argus.dataplatform.connectors.base import DocumentRef
from argus.knowledge.models import Company
from argus.knowledge.repositories import CompanyRepository

REGISTRY_URL = "https://www.sec.gov/files/company_tickers.json"

# strip corporate suffixes to derive a prose alias: "NVIDIA CORP" -> "NVIDIA"
_SUFFIX = re.compile(
    r"\s+(inc|corp|corporation|co|company|ltd|plc|sa|nv|ag|holdings?|group|lp|llc)\.?$",
    re.IGNORECASE,
)


class CompanyProfilesConnector:
    name = "company_profiles"

    def run(self, session: Session) -> dict:
        """Ingest today's registry snapshot (provenance) and upsert canonical companies."""
        from argus.dataplatform.connectors.base import ingest

        refs = self.discover()
        stats = ingest(session, self, refs=refs)
        seeded = seed_companies(session, refs[0].inline_content)
        return {**stats, **seeded}

    def discover(self) -> list[DocumentRef]:
        settings = get_settings()
        content = httpx.get(
            REGISTRY_URL, headers={"User-Agent": settings.sec_user_agent}, timeout=30
        ).raise_for_status().content
        today = datetime.now(UTC).date().isoformat()
        return [
            DocumentRef(
                source=self.name,
                native_id=f"company_tickers/{today}",
                doc_type="profile_registry",
                url=REGISTRY_URL,
                title=f"SEC company ticker registry {today}",
                publisher="SEC",
                published_at=datetime.now(UTC),
                inline_content=content,
                enqueue_pipeline=False,  # provenance snapshot, not search corpus
            )
        ]

    def fetch(self, ref: DocumentRef) -> bytes:  # pragma: no cover - inline_content used
        raise NotImplementedError


def seed_companies(session: Session, registry_json: bytes) -> dict:
    """Upsert canonical companies from the registry snapshot. Idempotent."""
    repo = CompanyRepository(session)
    by_cik: dict[str, dict] = {}
    for row in json.loads(registry_json).values():
        cik = str(row["cik_str"])
        entry = by_cik.setdefault(cik, {"name": row["title"], "tickers": []})
        entry["tickers"].append(row["ticker"])

    created = updated = 0
    for cik, entry in by_cik.items():
        alias = _SUFFIX.sub("", entry["name"]).strip()
        aliases = [alias] if len(alias) >= 4 and alias != entry["name"] else []
        company = repo.by_cik(cik)
        if company is None:
            repo.add(
                Company(name=entry["name"], cik=cik, tickers=entry["tickers"], aliases=aliases)
            )
            created += 1
        elif (
            company.name != entry["name"]
            or company.tickers != entry["tickers"]
            or company.aliases != aliases
        ):
            company.name = entry["name"]
            company.tickers = entry["tickers"]
            company.aliases = aliases
            updated += 1
    return {"created": created, "updated": updated}
