"""Shared FastAPI dependencies."""

from db.database import async_session, get_db
from api.scanner import ScanOrchestrator
from core.simulation.ocoka import Specter

db_dependency = get_db

_orchestrator: ScanOrchestrator | None = None
_specter: Specter | None = None


def get_orchestrator() -> ScanOrchestrator:
    """Return singleton ScanOrchestrator."""
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = ScanOrchestrator()
    return _orchestrator


def get_specter() -> Specter:
    """Return singleton Specter instance."""
    global _specter
    if _specter is None:
        _specter = Specter()
    return _specter
