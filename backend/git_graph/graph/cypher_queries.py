"""
Predefined Cypher Queries for Git Knowledge Graphs
==================================================
Curated openCypher query templates for repository exploration,
dependency analysis, code hierarchy navigation, and call graph queries.
"""

from typing import Dict

SAMPLE_CYPHER_QUERIES: Dict[str, str] = {
    "1. List all entities in Git Graph (Limit 25)": """MATCH (n)
RETURN n
LIMIT 25""",

    "2. List all relationships with source & target (Limit 25)": """MATCH (a)-[r]->(b)
RETURN a, r, b
LIMIT 25""",

    "3. Find all Classes defined in repository": """MATCH (f:File)-[r:DEFINES]->(c:Class)
RETURN f, r, c
LIMIT 50""",

    "4. Find all Functions & Methods": """MATCH (p)-[r]->(fn)
WHERE label(fn) = 'Function' OR label(fn) = 'Method'
RETURN p, r, fn
LIMIT 50""",

    "5. Find External Library Dependencies": """MATCH (f:File)-[r:IMPORTS]->(l:Library)
RETURN f, r, l
LIMIT 50""",

    "6. Find API Endpoints and their Implementation Functions": """MATCH (api:API)-[r:IMPLEMENTED_BY]->(fn)
RETURN api, r, fn
LIMIT 25""",

    "7. Find Technologies used by the Repository": """MATCH (repo:Repository)-[r:USES]->(tech:Technology)
RETURN repo, r, tech
LIMIT 25""",

    "8. Find Architecture Concepts from README": """MATCH (f:File)-[r:DESCRIBES]->(c:Concept)
RETURN f, r, c
LIMIT 25""",

    "9. Explore Repository Directory Tree Hierarchy": """MATCH (p)-[r:CONTAINS]->(c)
RETURN p, r, c
LIMIT 50"""
}
