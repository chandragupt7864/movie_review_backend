from datetime import datetime, timezone


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def build_timeline_event(agent: str, status: str, message: str, data: dict | None = None) -> dict:
    event_time = utc_now_iso()
    return {
        "timestamp": event_time,
        "time": event_time,
        "agent": agent,
        "status": status,
        "message": message,
        "data": data or {},
    }

