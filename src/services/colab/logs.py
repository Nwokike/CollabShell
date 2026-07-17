import asyncio
import os


async def get_log_impl(
    service,
    session_name: str,
    lines: int = None,
    event_type: str = None,
) -> list:
    """Get session history logs."""

    def _log():
        from core.storage_patch import resolve_storage_dir
        from colab_cli.history import HistoryLogger

        h = HistoryLogger(log_dir=os.path.join(resolve_storage_dir(), "history"))
        events = h.get_history(session_name)
        if event_type:
            events = [e for e in events if e.get("event_type") == event_type]
        if lines:
            events = events[-lines:]
        return events

    return await asyncio.to_thread(_log)


async def list_log_sessions_impl(service) -> list:
    """List session names that have history logs."""

    def _list():
        from core.storage_patch import resolve_storage_dir
        from colab_cli.history import HistoryLogger

        h = HistoryLogger(log_dir=os.path.join(resolve_storage_dir(), "history"))
        return h.list_sessions()

    return await asyncio.to_thread(_list)


async def export_log_impl(service, session_name: str, output_path: str) -> bool:
    """Export session history to a file."""

    def _export():
        from core.storage_patch import resolve_storage_dir
        from colab_cli.history import HistoryLogger
        from colab_cli.converter import export_history

        h = HistoryLogger(log_dir=os.path.join(resolve_storage_dir(), "history"))
        events = h.get_history(session_name)
        if not events:
            return False
        export_history(events, session_name, output_path)
        return True

    return await asyncio.to_thread(_export)
