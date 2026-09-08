"""
Entity and Relationship Canonical Normalizer
============================================
Generates deterministic stable canonical identifiers, normalizes library/technology
aliases, and deduplicates entities and directed relationships before graph ingestion.
"""

import re
from typing import List, Dict, Tuple, Set, Optional
from backend.git_graph.context.schemas import GitGraphEntity, GitGraphRelationship, GitProvenance

CANONICAL_LIB_ALIASES = {
    "psycopg2-binary": "psycopg2",
    "psycopg2": "psycopg2",
    "psycopg": "psycopg",
    "py-pdf": "pypdf",
    "pypdf2": "pypdf",
    "pypdf": "pypdf",
    "openai-python": "openai",
    "google-generativeai": "google-generativeai",
    "google-genai": "google-genai",
    "pyyaml": "pyyaml",
    "fastapi": "fastapi",
    "uvicorn": "uvicorn",
    "streamlit": "streamlit",
    "duckdb": "duckdb",
    "networkx": "networkx",
    "pandas": "pandas",
    "pyarrow": "pyarrow",
    "pydantic": "pydantic",
    "pytest": "pytest",
}

CANONICAL_TECH_ALIASES = {
    "apache age": "Apache AGE",
    "age": "Apache AGE",
    "apache graph extension": "Apache AGE",
    "postgres": "PostgreSQL",
    "postgresql": "PostgreSQL",
    "fastapi": "FastAPI",
    "streamlit": "Streamlit",
    "docker": "Docker",
    "docker-compose": "Docker Compose",
    "docker compose": "Docker Compose",
    "duckdb": "DuckDB",
    "dbt": "dbt",
    "python": "Python",
    "typescript": "TypeScript",
    "javascript": "JavaScript",
    "nodejs": "Node.js",
    "node.js": "Node.js",
    "react": "React",
    "nextjs": "Next.js",
    "next.js": "Next.js",
    "express": "Express",
    "openai": "OpenAI",
    "gemini": "Google Gemini",
    "google gemini": "Google Gemini",
    "vis.js": "Vis.js",
    "visjs": "Vis.js",
}

class EntityNormalizer:
    @staticmethod
    def clean_name(name: str) -> str:
        cleaned = re.sub(r'^[\s"\'`“‘]+|[\s"\'`”’]+$', '', name)
        cleaned = re.sub(r'\s+', ' ', cleaned).strip()
        return cleaned

    @staticmethod
    def canonical_lib_name(name: str) -> str:
        clean = EntityNormalizer.clean_name(name).lower().replace("_", "-")
        return CANONICAL_LIB_ALIASES.get(clean, clean)

    @staticmethod
    def canonical_tech_name(name: str) -> str:
        clean = EntityNormalizer.clean_name(name)
        lower = clean.lower()
        if lower in CANONICAL_TECH_ALIASES:
            return CANONICAL_TECH_ALIASES[lower]
        if clean.islower() and len(clean) > 2:
            return clean.title()
        return clean

    @staticmethod
    def normalize_rel_type(rel_type: str) -> str:
        cleaned = re.sub(r'[^a-zA-Z0-9_]', '_', rel_type.strip()).upper()
        cleaned = re.sub(r'_+', '_', cleaned).strip('_')
        valid = {
            "CONTAINS", "DEFINES", "IMPORTS", "DEPENDS_ON", "CALLS",
            "IMPLEMENTED_BY", "CONNECTS_TO", "USES", "DESCRIBES", "EXTENDS",
            "RELATED_TO", "MENTIONS"
        }
        return cleaned if cleaned in valid else (cleaned if len(cleaned) > 1 else "RELATED_TO")

    # Canonical ID Generators
    @staticmethod
    def repo_id(repo_name: str) -> str:
        return f"repo:{repo_name}"

    @staticmethod
    def dir_id(repo_name: str, dir_path: str) -> str:
        p = dir_path.replace("\\", "/").strip("/")
        return f"repo:{repo_name}:dir:{p}"

    @staticmethod
    def file_id(repo_name: str, file_path: str) -> str:
        p = file_path.replace("\\", "/").strip("/")
        return f"repo:{repo_name}:file:{p}"

    @staticmethod
    def module_id(repo_name: str, module_name: str) -> str:
        return f"repo:{repo_name}:mod:{module_name.strip()}"

    @staticmethod
    def class_id(repo_name: str, file_path: str, class_name: str) -> str:
        p = file_path.replace("\\", "/").strip("/")
        return f"repo:{repo_name}:file:{p}:class:{class_name.strip()}"

    @staticmethod
    def function_id(repo_name: str, file_path: str, func_name: str) -> str:
        p = file_path.replace("\\", "/").strip("/")
        return f"repo:{repo_name}:file:{p}:func:{func_name.strip()}"

    @staticmethod
    def method_id(repo_name: str, file_path: str, class_name: str, method_name: str) -> str:
        p = file_path.replace("\\", "/").strip("/")
        return f"repo:{repo_name}:file:{p}:class:{class_name.strip()}:method:{method_name.strip()}"

    @staticmethod
    def library_id(lib_name: str) -> str:
        canon = EntityNormalizer.canonical_lib_name(lib_name)
        return f"lib:{canon}"

    @staticmethod
    def technology_id(tech_name: str) -> str:
        canon = EntityNormalizer.canonical_tech_name(tech_name)
        return f"tech:{canon}"

    @staticmethod
    def api_id(repo_name: str, http_method: str, path: str) -> str:
        clean_path = path.strip().replace("/", "_")
        return f"repo:{repo_name}:api:{http_method.upper()}_{clean_path}"

    @staticmethod
    def service_id(repo_name: str, service_name: str) -> str:
        return f"repo:{repo_name}:service:{service_name.strip()}"

    @staticmethod
    def concept_id(concept_name: str) -> str:
        clean = EntityNormalizer.clean_name(concept_name)
        return f"concept:{clean}"

    def deduplicate_and_normalize(
        self,
        entities: List[GitGraphEntity],
        relationships: List[GitGraphRelationship]
    ) -> Tuple[List[GitGraphEntity], List[GitGraphRelationship]]:
        """
        Deduplicate entities and relationships by canonical identifiers.
        Merges metadata, preserves provenance and aggregates weights.
        """
        merged_entities: Dict[str, GitGraphEntity] = {}

        for ent in entities:
            cid = ent.canonical_id
            if not cid:
                continue

            if cid not in merged_entities:
                merged_entities[cid] = ent
            else:
                existing = merged_entities[cid]
                # Merge aliases
                all_aliases = set(existing.aliases + ent.aliases)
                existing.aliases = sorted(list(all_aliases))
                # Merge properties
                for k, v in ent.properties.items():
                    if k not in existing.properties or not existing.properties[k]:
                        existing.properties[k] = v
                # Preserve richer description
                if ent.description and (not existing.description or len(ent.description) > len(existing.description)):
                    existing.description = ent.description
                # Update confidence
                existing.confidence = max(existing.confidence, ent.confidence)

        # Deduplicate relationships
        merged_relationships: Dict[Tuple[str, str, str], GitGraphRelationship] = {}

        for rel in relationships:
            src_cid = rel.source_canonical_id
            tgt_cid = rel.target_canonical_id
            rel_type = self.normalize_rel_type(rel.relationship_type)

            # Prevent self loops and empty IDs
            if not src_cid or not tgt_cid or src_cid == tgt_cid:
                continue

            # Ensure both source and target exist in entities
            if src_cid not in merged_entities or tgt_cid not in merged_entities:
                continue

            key = (src_cid, rel_type, tgt_cid)
            if key not in merged_relationships:
                rel.relationship_type = rel_type
                merged_relationships[key] = rel
            else:
                existing_rel = merged_relationships[key]
                existing_rel.weight += 0.5
                for k, v in rel.properties.items():
                    if k not in existing_rel.properties:
                        existing_rel.properties[k] = v

        return list(merged_entities.values()), list(merged_relationships.values())
