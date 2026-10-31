"""Shared support-agent construction for UI, CLI, evaluation and future batch audio."""
from .calculations import BusinessCalendar
from .config import load_retrieval_settings
from .dialogue import LLMConversation
from .runtime import build_public_index
from .workflows import SupportAgent


def create_agent(settings, model, *, index=None, calendar=None, gateway=None,
                 top_k=5, reply_language=None, allow_ticket_writes=False):
    """Share public resources only; every call owns fresh verification and memory."""
    if index is None:
        retrieval = load_retrieval_settings(settings.project_root)
        index = build_public_index(settings.dataset_dir, settings.artifacts_dir,
                                   retrieval.method, retrieval.offline)
    if calendar is None:
        calendar = BusinessCalendar.load(settings.dataset_dir)
    if gateway is None:
        from .tools import MockToolGateway
        gateway = MockToolGateway(settings.dataset_dir, settings.artifacts_dir / 'tickets',
                                  allow_ticket_writes=allow_ticket_writes)
    backend = SupportAgent(index, model, settings.reference_date, calendar=calendar,
                           gateway=gateway, top_k=top_k, reply_language=reply_language,
                           allow_ticket_writes=allow_ticket_writes)
    return LLMConversation(backend, model)
