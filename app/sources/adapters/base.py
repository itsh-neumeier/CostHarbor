"""Base adapter interface."""

from abc import ABC, abstractmethod

from sqlalchemy.orm import Session

from app.sources.models import ImportJob, SourceConnection


class BaseAdapter(ABC):
    """Abstract base class for data source adapters."""

    def __init__(self, db: Session, job: ImportJob, source: SourceConnection):
        self.db = db
        self.job = job
        self.source = source
        self.config = source.connection_config_json or {}

    @abstractmethod
    def run(self) -> None:
        """Execute the import."""
        ...

    def _increment_imported(self, count: int = 1) -> None:
        self.job.records_imported += count

    def _increment_failed(self, count: int = 1) -> None:
        self.job.records_failed += count
