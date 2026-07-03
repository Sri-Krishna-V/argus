"""Repositories for the knowledge aggregates. All DB access above core goes through
these — storage stays swappable (ADR-0002)."""

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from argus.knowledge.models import Company, Document


class DocumentRepository:
    def __init__(self, session: Session):
        self.session = session

    def add(self, document: Document) -> Document:
        self.session.add(document)
        self.session.flush()
        return document

    def get(self, document_id: uuid.UUID) -> Document | None:
        return self.session.get(Document, document_id)

    def by_source_id(self, source: str, source_native_id: str) -> Document | None:
        return self.session.scalar(
            select(Document).where(
                Document.source == source, Document.source_native_id == source_native_id
            )
        )

    def advance_status(self, document_id: uuid.UUID, status: str) -> None:
        """The only sanctioned mutation; content columns are trigger-guarded."""
        doc = self.session.get(Document, document_id)
        if doc is None:
            raise LookupError(f"document {document_id} not found")
        doc.status = status
        self.session.flush()


class CompanyRepository:
    def __init__(self, session: Session):
        self.session = session

    def add(self, company: Company) -> Company:
        self.session.add(company)
        self.session.flush()
        return company

    def by_cik(self, cik: str) -> Company | None:
        return self.session.scalar(select(Company).where(Company.cik == cik))
