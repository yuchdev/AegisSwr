"""View adapters: subscribe to the core EventBus and render domain events.

The core never imports from this package — views are pluggable observers.
"""
from aegis_swr.views.rich_view import (
    RichView,
    WarRoomView,
    make_console,
    make_view,
    render_verdict,
)

__all__ = [
    "RichView",
    "WarRoomView",
    "make_console",
    "make_view",
    "render_verdict",
]
