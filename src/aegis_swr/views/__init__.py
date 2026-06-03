"""View adapters: subscribe to the core EventBus and render domain events.

The core never imports from this package — views are pluggable observers.
"""
from aegis_swr.views.rich_view import RichView, make_console, render_verdict

__all__ = ["RichView", "make_console", "render_verdict"]
