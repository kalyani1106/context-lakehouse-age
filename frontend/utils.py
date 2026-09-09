"""
Frontend UI Helper Utilities
============================
Reusable formatting, icon mapping, and status indicators for Streamlit UI.
"""

from pathlib import Path
from typing import Optional, Union


def get_file_icon(filename_or_ext: Optional[str]) -> str:
    """Returns a recognizable emoji/icon for a supported file format or extension."""
    if not filename_or_ext:
        return "📄"
    ext = Path(filename_or_ext).suffix.lower()
    if not ext and filename_or_ext.startswith("."):
        ext = filename_or_ext.lower()
    elif not ext:
        ext = f".{filename_or_ext.lower()}"
    
    icon_map = {
        ".pdf": "📕",
        ".docx": "📝",
        ".txt": "📄",
        ".text": "📄",
        ".md": "📝",
        ".markdown": "📝",
        ".csv": "📊",
        ".tsv": "📊",
        ".xlsx": "📗",
        ".xls": "📗",
        ".json": "🔢",
        ".jsonl": "🔢",
        ".ndjson": "🔢",
        ".xml": "🧩",
        ".html": "🌐",
        ".htm": "🌐",
        ".parquet": "⚡",
        ".pq": "⚡",
        ".feather": "🪶",
        ".arrow": "🪶",
        ".yaml": "⚙️",
        ".yml": "⚙️",
        ".sql": "🗄️",
        ".rtf": "📄",
    }
    return icon_map.get(ext, "📄")


def get_status_indicator(status: Optional[str]) -> str:
    """Returns formatted status with a color indicator emoji."""
    if not status:
        return "⚪ PENDING"
    s = str(status).upper()
    if "COMPLETED" in s:
        return "🟢 COMPLETED"
    elif "PROCESSING" in s or "RUNNING" in s:
        return "🟡 PROCESSING"
    elif "FAILED" in s or "ERROR" in s:
        return "🔴 FAILED"
    elif "UPLOADED" in s:
        return "🔵 UPLOADED"
    else:
        return "⚪ PENDING"


def get_intent_badge(intent: Optional[str]) -> str:
    """Returns an icon-prefixed formatted intent badge string."""
    if not intent:
        return "🔍 GENERAL"
    intent_str = str(intent).upper().replace("QUERYINTENT.", "")
    intent_map = {
        "AUTHENTICATION": "🔐 AUTHENTICATION",
        "DEPENDENCY": "📦 DEPENDENCY",
        "API_ROUTES": "🌐 API_ROUTES",
        "ARCHITECTURE": "🏛️ ARCHITECTURE",
        "SCHEMA": "📊 SCHEMA",
        "DATA_FLOW": "⚡ DATA_FLOW",
        "GENERAL": "🔍 GENERAL",
    }
    return intent_map.get(intent_str, f"🔍 {intent_str}")


def format_bytes(size_bytes: Optional[Union[int, float]]) -> str:
    """Converts a raw byte count to a clean human-readable KB / MB string."""
    if size_bytes is None or size_bytes < 0:
        return "0 KB"
    kb = size_bytes / 1024.0
    if kb >= 1024.0:
        mb = kb / 1024.0
        return f"{mb:.2f} MB"
    return f"{kb:.1f} KB"
