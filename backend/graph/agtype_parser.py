"""
Apache AGE Agtype Parser
========================
Converts PostgreSQL Apache AGE raw agtype strings into native Python dictionaries/objects.

Examples:
- Vertex: '{"id": 844424930131969, "label": "Technology", "properties": {"name": "Apache AGE"}}::vertex'
  -> {'id': 844424930131969, 'label': 'Technology', 'properties': {'name': 'Apache AGE'}}
- Edge: '{"id": 1688849860263937, "label": "EXTENDS", "end_id": ..., "start_id": ..., "properties": {...}}::edge'
  -> {'id': 1688849860263937, 'label': 'EXTENDS', 'end_id': ..., 'start_id': ..., 'properties': {...}}
"""

import re
import json
from typing import Any, Union, Dict, List

def parse_agtype(val: Any) -> Any:
    if val is None:
        return None
    
    if isinstance(val, (dict, list, int, float, bool)):
        return val
        
    s = str(val).strip()
    
    # Strip type casting suffix ::vertex, ::edge, ::path, ::numeric, etc.
    s_cleaned = re.sub(r'::(vertex|edge|path|numeric|int|float|bool|agtype)$', '', s).strip()
    
    # Try parsing as JSON
    try:
        parsed = json.loads(s_cleaned)
        # If it's a vertex or edge dictionary, normalize properties
        if isinstance(parsed, dict):
            if "properties" not in parsed and "label" in parsed:
                parsed["properties"] = {}
        return parsed
    except Exception:
        # Fallback to string without type cast
        return s_cleaned
