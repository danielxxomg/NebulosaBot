"""RED for PR2 2.7 TicketService schedule/cancel + close clears."""

import inspect

from bot.services.ticket_service import TicketService


def test_has_schedule_cancel():
    assert hasattr(TicketService, "schedule_close"), "TicketService.schedule_close missing"
    assert hasattr(TicketService, "cancel_scheduled_close"), "TicketService.cancel_scheduled_close missing"


def test_schedule_signature():
    sig = inspect.signature(TicketService.schedule_close)
    assert "guild_id" in sig.parameters
    assert "duration" in sig.parameters or "seconds" in sig.parameters or "scheduled" in " ".join(sig.parameters)


def test_service_source_calls_db_scheduled():
    import pathlib

    src = pathlib.Path("bot/services/ticket_service.py").read_text()
    # schedule path must touch scheduledCloseAt/By via db
    assert "scheduledCloseAt" in src or "scheduled_close" in src.lower()
    src2 = pathlib.Path("bot/services/ticket_lifecycle_service.py").read_text()
    # lifecycle or service must handle scheduled close
    assert "scheduled" in src.lower() or "scheduled" in src2.lower()
