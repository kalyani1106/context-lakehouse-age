"""
Markdown and Documentation Parser
=================================
Analyzes README.md and documentation files to extract repository descriptions,
architecture concepts, mentioned technologies, and components with exact provenance.
"""

import re
import logging
from pathlib import Path
from typing import List, Dict, Optional, Any, Set
from pydantic import BaseModel, Field

logger = logging.getLogger("markdown_parser")

KNOWN_TECHNOLOGY_KEYWORDS: Dict[str, str] = {
    "apache age": "Apache AGE",
    "age": "Apache AGE",
    "postgresql": "PostgreSQL",
    "postgres": "PostgreSQL",
    "fastapi": "FastAPI",
    "streamlit": "Streamlit",
    "docker": "Docker",
    "docker compose": "Docker Compose",
    "docker-compose": "Docker Compose",
    "duckdb": "DuckDB",
    "dbt": "dbt",
    "python": "Python",
    "typescript": "TypeScript",
    "javascript": "JavaScript",
    "openai": "OpenAI",
    "gemini": "Google Gemini",
    "networkx": "NetworkX",
    "parquet": "Apache Parquet",
    "pyarrow": "PyArrow",
    "pydantic": "Pydantic",
    "uvicorn": "Uvicorn",
    "redis": "Redis",
    "graphql": "GraphQL",
    "vis.js": "Vis.js",
}

KNOWN_CONCEPT_KEYWORDS: Dict[str, str] = {
    "knowledge graph": "Knowledge Graph",
    "context lakehouse": "Context Lakehouse",
    "data lakehouse": "Context Lakehouse",
    "lakehouse": "Context Lakehouse",
    "semantic layer": "Semantic Layer",
    "context layer": "Context Layer",
    "ast parser": "AST Code Parsing",
    "abstract syntax tree": "AST Code Parsing",
    "provenance": "Provenance Traceability",
    "traceability": "Provenance Traceability",
    "idempotent": "Idempotent Ingestion",
    "idempotency": "Idempotent Ingestion",
    "graph database": "Graph Database",
    "property graph": "Property Graph",
    "cypher": "openCypher",
    "opencypher": "openCypher",
}

class ParsedDocConcept(BaseModel):
    name: str
    concept_type: str # Architecture, Domain, Feature
    mention_count: int = 1
    start_line: int = 1
    source_snippet: str = ""

class ParsedDocTechnology(BaseModel):
    name: str
    canonical_name: str
    mention_count: int = 1
    start_line: int = 1
    source_snippet: str = ""

class ParsedMarkdownDoc(BaseModel):
    relative_path: str
    title: Optional[str] = None
    summary: Optional[str] = None
    sections: List[str] = Field(default_factory=list)
    technologies: List[ParsedDocTechnology] = Field(default_factory=list)
    concepts: List[ParsedDocConcept] = Field(default_factory=list)
    line_count: int = 0
    parse_errors: List[str] = Field(default_factory=list)

class MarkdownParser:
    @staticmethod
    def _clean_snippet(text: str, max_chars: int = 350) -> str:
        s = re.sub(r'\s+', ' ', text).strip()
        return s[:max_chars] + "..." if len(s) > max_chars else s

    @classmethod
    def parse_content(cls, content: str, relative_path: str) -> ParsedMarkdownDoc:
        lines = content.splitlines()
        line_count = len(lines)

        # 1. Extract Title: First # heading or filename
        title = None
        for idx, line in enumerate(lines, start=1):
            if line.strip().startswith("# "):
                title = line.strip("# ").strip()
                break
        if not title:
            title = Path(relative_path).stem.replace("_", " ").title()

        # 2. Extract Summary: First non-heading, non-empty paragraph
        summary_lines = []
        in_summary = False
        for line in lines:
            trimmed = line.strip()
            if not in_summary:
                if trimmed and not trimmed.startswith("#") and not trimmed.startswith("!") and not trimmed.startswith("["):
                    in_summary = True
                    summary_lines.append(trimmed)
            else:
                if trimmed and not trimmed.startswith("#"):
                    summary_lines.append(trimmed)
                elif not trimmed or trimmed.startswith("#"):
                    break
        summary = " ".join(summary_lines) if summary_lines else f"Documentation for {title}"
        if len(summary) > 400:
            summary = summary[:400] + "..."

        # 3. Extract Section Headings (##, ###)
        sections = []
        for line in lines:
            m = re.match(r'^(#{1,4})\s+(.+)$', line.strip())
            if m:
                sections.append(m.group(2).strip())

        # 4. Extract Technologies with Line Provenance
        tech_map: Dict[str, ParsedDocTechnology] = {}
        content_lower = content.lower()

        for term, canon in KNOWN_TECHNOLOGY_KEYWORDS.items():
            pattern = re.compile(rf'\b{re.escape(term)}\b', re.IGNORECASE)
            for m in pattern.finditer(content):
                line_no = content[:m.start()].count("\n") + 1
                snip = cls._clean_snippet(lines[max(0, line_no - 1)])
                if canon not in tech_map:
                    tech_map[canon] = ParsedDocTechnology(
                        name=canon,
                        canonical_name=canon,
                        mention_count=1,
                        start_line=line_no,
                        source_snippet=snip
                    )
                else:
                    tech_map[canon].mention_count += 1

        # 5. Extract Concepts with Line Provenance
        concept_map: Dict[str, ParsedDocConcept] = {}
        for term, canon in KNOWN_CONCEPT_KEYWORDS.items():
            pattern = re.compile(rf'\b{re.escape(term)}\b', re.IGNORECASE)
            for m in pattern.finditer(content):
                line_no = content[:m.start()].count("\n") + 1
                snip = cls._clean_snippet(lines[max(0, line_no - 1)])
                if canon not in concept_map:
                    concept_map[canon] = ParsedDocConcept(
                        name=canon,
                        concept_type="Architecture Concept",
                        mention_count=1,
                        start_line=line_no,
                        source_snippet=snip
                    )
                else:
                    concept_map[canon].mention_count += 1

        return ParsedMarkdownDoc(
            relative_path=relative_path,
            title=title,
            summary=summary,
            sections=sections,
            technologies=list(tech_map.values()),
            concepts=list(concept_map.values()),
            line_count=line_count,
            parse_errors=[]
        )

    @classmethod
    def parse_file(cls, file_path: Path, workspace_root: Path) -> ParsedMarkdownDoc:
        try:
            rel = file_path.relative_to(workspace_root).as_posix()
        except ValueError:
            rel = str(file_path)
        try:
            content = file_path.read_text(encoding="utf-8", errors="ignore")
            return cls.parse_content(content, rel)
        except Exception as e:
            return ParsedMarkdownDoc(
                relative_path=rel,
                parse_errors=[f"Markdown read error: {str(e)}"]
            )
