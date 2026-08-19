"""Thin facade re-exporting ticket views (S3.4B).

Split into 3 seams:
- :mod:`bot.views.ticket_panel` — TicketIntakeModal + TicketPanelView
- :mod:`bot.views.ticket_actions` — TicketActionsView (persistent, timeout=None)
- :mod:`bot.views.ticket_category_select` — ephemeral 300s selectors

All callers continue importing from :mod:`bot.views.tickets`.
"""

from __future__ import annotations

from bot.core.i18n import t
from bot.utils.checks import is_mod_check
from bot.views.ticket_actions import TicketActionsView
from bot.views.ticket_category_select import (
    _CategorySelect,
    _CategorySelectView,
    _EditCategorySelect,
    _EditCategoryView,
)
from bot.views.ticket_panel import (
    CHANNEL_DELETE_DELAY,
    TicketIntakeModal,
    TicketPanelView,
    _create_ticket_after_modal,
    deploy_ticket_panel,
    logger,
)

__all__ = [
    "CHANNEL_DELETE_DELAY",
    "TicketActionsView",
    "TicketIntakeModal",
    "TicketPanelView",
    "_CategorySelect",
    "_CategorySelectView",
    "_EditCategorySelect",
    "_EditCategoryView",
    "_create_ticket_after_modal",
    "deploy_ticket_panel",
    "is_mod_check",
    "logger",
    "t",
]
