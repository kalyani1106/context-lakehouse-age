"""
Entity and Relationship Normalizer & Deduplicator
=================================================
Resolves entity aliases, merges duplicate entities across chunks/pages,
normalizes relationship types, and ensures graph integrity.
"""

import re
from typing import List, Dict, Tuple, Set, Optional
from backend.context.schemas import Entity, Relationship, DocumentContext, Provenance

# Known canonical mappings and aliases
CANONICAL_ALIASES = {
    "apache age": "Apache AGE",
    "age": "Apache AGE",
    "apache graph extension": "Apache AGE",
    "postgres": "PostgreSQL",
    "postgresql": "PostgreSQL",
    "context lakehouse": "Context Lakehouse",
    "lakehouse": "Context Lakehouse",
    "duckdb": "DuckDB",
    "dbt": "dbt",
    "dbt core": "dbt",
    "metricflow": "MetricFlow",
    "datahub": "DataHub",
    "palantir": "Palantir",
    "palantir foundry": "Palantir Foundry",
    "onetrust": "OneTrust",
    "stardog": "Stardog",
    "segmento": "Segmento",
    "knowledge graph": "Knowledge Graph",
    "semantic layer": "Semantic Layer",
    "context layer": "Context Layer",
}

class EntityNormalizer:
    @staticmethod
    def clean_name(name: str) -> str:
        """Strip punctuation, quotes, and normalize internal spaces."""
        cleaned = re.sub(r'^[\s"\'`“‘]+|[\s"\'`”’]+$', '', name)
        cleaned = re.sub(r'\s+', ' ', cleaned).strip()
        return cleaned

    @staticmethod
    def get_canonical_name(name: str) -> str:
        cleaned = EntityNormalizer.clean_name(name)
        lower = cleaned.lower()
        if lower in CANONICAL_ALIASES:
            return CANONICAL_ALIASES[lower]
        # Title case standard entities if lowercase
        if cleaned.islower() and len(cleaned) > 2:
            return cleaned.title()
        return cleaned

    @staticmethod
    def normalize_rel_type(rel_type: str) -> str:
        """Ensure standard UPPER_SNAKE_CASE relationship labels."""
        cleaned = re.sub(r'[^a-zA-Z0-9_]', '_', rel_type.strip()).upper()
        cleaned = re.sub(r'_+', '_', cleaned).strip('_')
        valid_types = {
            "EXTENDS", "USES", "AUTHORED_BY", "RELATED_TO", "PART_OF",
            "DEPENDS_ON", "IMPLEMENTS", "CREATES", "MENTIONS", "INTEGRATES_WITH",
            "CONTAINS", "ENABLES", "PROVIDES", "STORED_IN", "TRANSFORMS"
        }
        if cleaned in valid_types:
            return cleaned
        # Default fallback
        return cleaned if len(cleaned) > 1 else "RELATED_TO"

    def deduplicate_and_normalize(
        self,
        entities: List[Entity],
        relationships: List[Relationship]
    ) -> Tuple[List[Entity], List[Relationship]]:
        """
        Merge duplicate entities into single canonical entities with aggregated aliases.
        Normalize relationship endpoints to canonical names and deduplicate edges.
        Respects explicit canonical_name when provided (e.g. for structural columns/sheets).
        """
        # 1. Deduplicate & merge entities
        merged_entities: Dict[str, Entity] = {}
        alias_to_canonical: Dict[str, str] = {}

        for ent in entities:
            clean = self.clean_name(ent.name) if ent.name else ""
            raw_canonical = (ent.canonical_name or "").strip()
            canonical = self.get_canonical_name(raw_canonical) if raw_canonical else self.get_canonical_name(clean)

            if not canonical or len(canonical) < 2:
                continue

            alias_to_canonical[canonical.lower()] = canonical
            if clean:
                alias_to_canonical[clean.lower()] = canonical
            if raw_canonical:
                alias_to_canonical[raw_canonical.lower()] = canonical

            for alias in ent.aliases:
                clean_alias = self.clean_name(alias)
                if clean_alias:
                    alias_to_canonical[clean_alias.lower()] = canonical

            display_name = ent.name if (ent.name and ent.name.strip()) else canonical

            if canonical not in merged_entities:
                merged_entities[canonical] = Entity(
                    name=display_name,
                    canonical_name=canonical,
                    type=ent.type if ent.type else "Concept",
                    description=ent.description,
                    aliases=list(set(ent.aliases + ([clean] if clean and clean != canonical else []))),
                    source=ent.source,
                    confidence=ent.confidence
                )
            else:
                existing = merged_entities[canonical]
                # Merge aliases
                all_aliases = set(existing.aliases + ent.aliases + ([clean] if clean and clean != canonical else []))
                existing.aliases = sorted(list(all_aliases))
                # Promote to specific type if existing is generic Concept
                if ent.type and ent.type != "Concept" and existing.type == "Concept":
                    existing.type = ent.type
                # Preserve richer display name if available
                if ent.name and ent.name != canonical and existing.name == canonical:
                    existing.name = ent.name
                # Preserve richer description
                if ent.description and (not existing.description or len(ent.description) > len(existing.description)):
                    existing.description = ent.description
                # Retain highest confidence
                existing.confidence = max(existing.confidence, ent.confidence)

        # 2. Deduplicate and normalize relationships
        merged_relationships: Dict[Tuple[str, str, str], Relationship] = {}

        for rel in relationships:
            src_raw = rel.source_entity.strip() if rel.source_entity else ""
            tgt_raw = rel.target_entity.strip() if rel.target_entity else ""
            src_clean = self.clean_name(src_raw)
            tgt_clean = self.clean_name(tgt_raw)

            # Check direct canonical key match first, then alias lookup, then fallback
            src_canonical = src_raw if src_raw in merged_entities else alias_to_canonical.get(src_clean.lower(), self.get_canonical_name(src_clean))
            tgt_canonical = tgt_raw if tgt_raw in merged_entities else alias_to_canonical.get(tgt_clean.lower(), self.get_canonical_name(tgt_clean))

            # Avoid self-loops and empty entities
            if not src_canonical or not tgt_canonical or src_canonical.lower() == tgt_canonical.lower():
                continue

            # Ensure both source and target entities exist in merged entities catalog
            if src_canonical not in merged_entities:
                merged_entities[src_canonical] = Entity(
                    name=src_canonical,
                    canonical_name=src_canonical,
                    type="Concept",
                    aliases=[],
                    source=rel.source,
                    confidence=0.8
                )
            if tgt_canonical not in merged_entities:
                merged_entities[tgt_canonical] = Entity(
                    name=tgt_canonical,
                    canonical_name=tgt_canonical,
                    type="Concept",
                    aliases=[],
                    source=rel.source,
                    confidence=0.8
                )

            norm_rel_type = self.normalize_rel_type(rel.relationship_type)
            key = (src_canonical, norm_rel_type, tgt_canonical)

            if key not in merged_relationships:
                merged_relationships[key] = Relationship(
                    source_entity=src_canonical,
                    target_entity=tgt_canonical,
                    relationship_type=norm_rel_type,
                    description=rel.description,
                    source=rel.source,
                    weight=rel.weight
                )
            else:
                existing_rel = merged_relationships[key]
                existing_rel.weight += 0.5 # boost weight for repeated evidence
                if rel.description and (not existing_rel.description or len(rel.description) > len(existing_rel.description)):
                    existing_rel.description = rel.description

        return list(merged_entities.values()), list(merged_relationships.values())
