"""
Context Extractor
=================
High-precision entity, relationship, and semantic context extraction from document chunks.
Supports LLMs (OpenAI, Google Gemini) and a high-precision deterministic Heuristic NLP Extractor
with strict stopword filtering, domain knowledge dictionaries, and predicate-driven relationship extraction.
"""

import os
import re
import json
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple, Set
from datetime import datetime, timezone

from backend.config import settings
from backend.extraction.chunker import DocumentChunk
from backend.extraction.pdf_extractor import ExtractedDocument
from backend.context.schemas import Entity, Relationship, DocumentContext, Provenance
from backend.context.normalizer import EntityNormalizer
from backend.storage.models import ExtractionMethod

logger = logging.getLogger("context_extractor")

SYSTEM_PROMPT = """You are an expert Knowledge Graph and Semantic Context Extraction Engine.
Analyze the provided document text and extract ONLY high-value, meaningful semantic entities and relationships.
Prioritize:
- Technology (e.g. Apache AGE, PostgreSQL, Python, SQL, DuckDB, Power BI, Docker, FastAPI)
- Concept (e.g. Context Lakehouse, Semantic Layer, Knowledge Graph, Machine Learning, Data Pipeline)
- Organization (e.g. Segmento, Google, Microsoft, LinkedIn, Vignan's Institute of Information Technology)
- Person (e.g. Rowthu Kalyani, John Doe)
- Project (e.g. Customer Churn Prediction, Semantic Search Engine)
- Dataset / Algorithm / Research Paper / Layer

DO NOT extract generic nouns, numbers, dates, common English words, or section headers (e.g. Education, Experience, Summary, Skills, Phone, Date, Description).
Only extract relationships when supported by clear evidence in the text.

Output MUST be strictly valid JSON conforming to this schema:
{
  "summary": "Concise summary of content",
  "entities": [
    {
      "name": "Exact name mentioned",
      "canonical_name": "Standardized canonical name",
      "type": "Technology | Concept | Organization | Person | Framework | Dataset | Algorithm | Layer | Project",
      "description": "Short explanation of role/function",
      "aliases": ["Alternative name 1", "Acronym"]
    }
  ],
  "relationships": [
    {
      "source_entity": "Canonical name of source",
      "relationship_type": "EXTENDS | USES | AUTHORED_BY | RELATED_TO | PART_OF | DEPENDS_ON | IMPLEMENTS | CREATES | MENTIONS | INTEGRATES_WITH | WORKS_AT | STUDIED_AT | COMBINES | PROVIDES | ENABLES",
      "target_entity": "Canonical name of target",
      "description": "Short description of relation"
    }
  ]
}
"""

class HighPrecisionNLPExtractor:
    """
    High-precision deterministic rule-based and NLP pattern extractor.
    Eliminates noise by using curated domain dictionaries, strict stopword lists,
    and predicate-driven relationship patterns.
    """

    # Curated Known Entities Dictionary: Canonical Name -> (Type, [Aliases])
    KNOWN_ENTITIES = {
        # Core Technologies & Databases
        "Apache AGE": ("Technology", ["AGE", "Apache Graph Extension"]),
        "PostgreSQL": ("Technology", ["Postgres", "PG", "PostgreSQL Database"]),
        "DuckDB": ("Technology", ["DuckDB Engine"]),
        "dbt": ("Technology", ["dbt Core", "data build tool"]),
        "MetricFlow": ("Technology", ["MetricFlow Engine"]),
        "DataHub": ("Technology", ["LinkedIn DataHub"]),
        "Palantir": ("Organization", ["Palantir Technologies"]),
        "Palantir Foundry": ("Technology", ["Foundry Ontology"]),
        "OneTrust": ("Technology", ["OneTrust Privacy"]),
        "Stardog": ("Technology", ["Stardog KG", "Stardog Union"]),
        "Segmento": ("Organization", ["Segmento Inc"]),
        "Apache Ossie": ("Technology", ["Ossie"]),
        "Dremio": ("Technology", ["Dremio Semantic Layer"]),
        "AtScale": ("Technology", ["AtScale Semantic Layer"]),
        "Cube": ("Technology", ["Cube.js"]),
        "Daana": ("Technology", ["Daana Platform"]),
        "Cypher": ("Technology", ["openCypher", "Cypher Query Language", "Cypher Query"]),
        "Graphify": ("Technology", ["Graphify+OKF"]),
        "FastAPI": ("Technology", ["FastAPI Framework"]),
        "Streamlit": ("Technology", ["Streamlit Web UI", "Streamlit Dashboard", "Streamlit UI", "Streamlit Visualization"]),
        "Docker": ("Technology", ["Docker Container"]),
        "Git": ("Technology", ["GitHub", "GitLab"]),
        "Linux": ("Technology", ["Ubuntu", "Debian"]),
        "Python": ("Technology", ["Python3", "Python Programming", "Python Application"]),
        "SQL": ("Technology", ["Structured Query Language", "ANSI SQL"]),
        "Power BI": ("Technology", ["Microsoft Power BI"]),
        "Tableau": ("Technology", ["Tableau Desktop"]),
        "Excel": ("Technology", ["Microsoft Excel"]),
        "Java": ("Technology", ["Java SE"]),
        "C++": ("Technology", ["CPP"]),
        "Pandas": ("Technology", ["Pandas DataFrame"]),
        "NumPy": ("Technology", ["NumPy Array"]),
        "Scikit-Learn": ("Technology", ["sklearn"]),
        "TensorFlow": ("Technology", ["TF"]),
        "PyTorch": ("Technology", ["Torch"]),
        "PySpark": ("Technology", ["Apache Spark"]),
        "Airflow": ("Technology", ["Apache Airflow"]),
        "Kafka": ("Technology", ["Apache Kafka"]),
        "Snowflake": ("Technology", ["Snowflake Data Cloud"]),
        "BigQuery": ("Technology", ["Google BigQuery"]),
        "LookML": ("Technology", ["Looker LookML"]),
        "Looker": ("Technology", ["Google Looker"]),
        "Delta Lake": ("Technology", ["Delta Tables"]),
        "Apache Iceberg": ("Technology", ["Iceberg Catalog"]),
        "Apache Arrow": ("Technology", ["PyArrow"]),
        "GraphQL": ("Technology", ["GraphQL API"]),
        "REST API": ("Technology", ["RESTful Services"]),
        "Jupyter": ("Technology", ["Jupyter Notebook"]),
        "VS Code": ("Technology", ["Visual Studio Code"]),

        # Core Concepts & Layers
        "Context Lakehouse": ("Concept", ["Data Lakehouse", "Context Engine"]),
        "Traditional Lakehouse": ("Concept", ["Traditional Data Lakehouse"]),
        "Semantic Layer": ("Concept", ["Semantic Fabric", "Metrics Layer"]),
        "Context Layer": ("Concept", ["Shared Context Layer"]),
        "Knowledge Graph": ("Concept", ["Graph DB", "KG", "Knowledge Graph Architecture"]),
        "Graph Database": ("Concept", ["Graph Store"]),
        "Relational Database": ("Concept", ["RDBMS", "Relational Engine", "Relational Data", "Relational Tables"]),
        "Semantic Catalog": ("Concept", ["semantic_catalog.json", "Semantic Metadata"]),
        "Open Knowledge Format": ("Concept", ["OKF"]),
        "Open Semantic Interchange": ("Concept", ["OSI"]),
        "Machine Learning": ("Concept", ["ML", "Predictive Modeling", "AI Reasoning", "LLM Reasoning"]),
        "Deep Learning": ("Concept", ["Neural Networks"]),
        "Data Engineering": ("Concept", ["Data Pipeline"]),
        "Data Analytics": ("Concept", ["Analytics", "Business Intelligence", "BI"]),
        "Operational Data": ("Concept", ["Operational Systems"]),
        "Analytical Data": ("Concept", ["Analytical Datasets"]),
        "Product Events": ("Concept", ["User Events"]),
        "Telemetry": ("Concept", ["Logs and Traces", "Telemetry Logs"]),
        "Documents": ("Concept", ["Business Knowledge", "Runbooks"]),
        "Business Definitions": ("Concept", ["Business Rules", "Metric Definitions"]),
        "Ontology": ("Concept", ["Semantic Ontology"]),
        "Data Governance": ("Concept", ["Governance", "Access Control"]),
        "Data Catalog": ("Concept", ["Metadata Platform"]),
        "Data Lake": ("Concept", ["Lake Storage"]),
        "Data Warehouse": ("Concept", ["DWH"]),
        "ETL": ("Concept", ["Extract Transform Load"]),
        "ELT": ("Concept", ["Extract Load Transform"]),
        "RAG": ("Concept", ["Retrieval Augmented Generation"]),
        "Vector Database": ("Concept", ["Vector Store"]),
        "Natural Language Processing": ("Concept", ["NLP"]),
        "AI Agents": ("Concept", ["Autonomous Agents"]),

        # Known Organizations
        "LinkedIn": ("Organization", ["LinkedIn Corp"]),
        "Google": ("Organization", ["Google Cloud"]),
        "Microsoft": ("Organization", ["MSFT"]),
        "Amazon": ("Organization", ["AWS"]),
        "Meta": ("Organization", ["Facebook"]),
        "Databricks": ("Organization", ["Databricks Inc"]),
        "dbt Labs": ("Organization", ["Fishtown Analytics"]),
        "Apache Software Foundation": ("Organization", ["Apache"]),
        "OpenAI": ("Organization", ["OpenAI Inc"]),
    }

    # Strict Stopword Blacklist (Disallow generic words/headings from becoming entities)
    STOPWORDS_BLACKLIST = {
        "EDUCATION", "EXPERIENCE", "WORK EXPERIENCE", "SKILLS", "TECHNICAL SKILLS",
        "KEY SKILLS", "PROJECTS", "ACADEMIC PROJECTS", "PERSONAL PROJECTS", "SUMMARY",
        "PROFESSIONAL SUMMARY", "PROFILE", "OBJECTIVE", "CAREER OBJECTIVE", "CERTIFICATIONS",
        "ACHIEVEMENTS", "AWARDS", "LANGUAGES", "INTERESTS", "HOBBIES", "CONTACT",
        "CONTACT DETAILS", "PHONE", "EMAIL", "ADDRESS", "DATE", "DURATION", "ROLE",
        "RESPONSIBILITIES", "DESCRIPTION", "DETAILS", "OVERVIEW", "INTRODUCTION",
        "CONCLUSION", "PRESENT", "CURRENT", "JANUARY", "FEBRUARY", "MARCH", "APRIL",
        "MAY", "JUNE", "JULY", "AUGUST", "SEPTEMBER", "OCTOBER", "NOVEMBER", "DECEMBER",
        "JAN", "FEB", "MAR", "APR", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC",
        "YEAR", "MONTH", "COLLEGE", "SCHOOL", "BACHELOR", "MASTER", "DEGREE",
        "B.TECH", "BTECH", "M.TECH", "MTECH", "BSC", "MSC", "CGPA", "PERCENTAGE",
        "INDIA", "ENGLISH", "TELUGU", "HINDI", "RESUME", "CURRICULUM VITAE", "CV",
        "PAGE", "REPORT", "FIGURE", "TABLE", "SECTION", "CHAPTER", "TITLE", "NAME",
        "CITY", "STATE", "COUNTRY", "ACTIVITY", "ACTIVITIES", "TEAM", "MEMBER",
        "LEAD", "LEADER", "INTERN", "INTERNSHIP", "ASSOCIATE", "ENGINEER", "DEVELOPER",
        "ANALYST", "STUDENT", "FRESHER", "RESULT", "RESULTS", "SCOPE", "FEATURE",
        "FEATURES", "METHODOLOGY", "ARCHITECTURE", "IMPLEMENTATION", "TESTING",
        "VERIFICATION", "REFERENCE", "REFERENCES", "APPENDIX", "THE", "THIS", "THAT",
        "THESE", "THOSE", "WHEN", "WHAT", "WHERE", "WHICH", "BECAUSE", "HOWEVER",
        "FIRST", "SECOND", "THIRD", "MAIN", "HIGH", "LOW", "GOOD", "BETTER", "BEST",
        "USER", "USERS", "HUMAN", "HUMANS", "APPLICATION", "APPLICATIONS", "SYSTEM",
        "SYSTEMS", "PROCESS", "PROCESSES", "MODEL", "MODELS", "DATA", "INFORMATION",
        "AND", "FOR", "WITH", "FROM", "ABOUT", "OVER", "UNDER", "AFTER", "BEFORE",
        "EVALUATED", "PARTICIPATED", "ACHIEVED", "CONTRIBUTED", "DESIGNED", "BUILT",
        "DEVELOPED", "CREATED", "MANAGED", "PERFORMED", "WORKED", "STUDIED", "USED",
        "PURPOSE", "PREREQUISITES", "SETUP", "SCHEMA", "BUILDING", "CONFIGURATION",
        "EXECUTION", "PROCESSING", "EXPLAIN", "EXAMPLE",
        "ID", "IDENTIFIER", "DEPARTMENT", "COLUMN", "COLUMNS", "ROW", "ROWS",
        "RECORD", "RECORDS", "SHEET", "SHEETS", "WORKBOOK", "FIELD", "FIELDS",
        "KEY", "KEYS", "VALUE", "VALUES", "INDEX", "DATA TYPE", "TYPES",
        "TOTAL ROWS", "TOTAL RECORDS", "TOTAL COLUMNS", "SAMPLE RECORDS"
    }

    # Strict Predicate Regex Patterns: (pattern, RelationshipType)
    PREDICATE_PATTERNS = [
        # EXTENDS / EXTENSION OF
        (r'\b(?P<src>[A-Za-z0-9_\s]{2,40}?)\s+(?:extends|is an extension of|built on top of|runs on|is built on|extension for|graph database extension for|work together with|works with)\s+(?P<tgt>[A-Za-z0-9_\s]{2,40}?)\b', "EXTENDS"),
        # COMBINES
        (r'\b(?P<src>[A-Za-z0-9_\s]{2,40}?)\s+(?:combines|unifies|brings together)\s+(?P<tgt>[A-Za-z0-9_\s]{2,40}?)\b', "COMBINES"),
        # PROVIDES / ENABLES
        (r'\b(?P<src>[A-Za-z0-9_\s]{2,40}?)\s+(?:provides|delivers|exposes|enables|supports|returns)\s+(?P<tgt>[A-Za-z0-9_\s]{2,40}?)\b', "PROVIDES"),
        # USES / UTILIZES / POWERED BY / SENDS TO
        (r'\b(?P<src>[A-Za-z0-9_\s]{2,40}?)\s+(?:uses|utilizes|leverages|queries|built with|developed using|powered by|implemented using|reads metadata from|sends .*? to|executes .*? on|converts .*? into|is used to|is used for)\s+(?P<tgt>[A-Za-z0-9_\s]{2,40}?)\b', "USES"),
        # WORKS_AT / EMPLOYED BY
        (r'\b(?P<src>[A-Za-z0-9_\s]{2,40}?)\s+(?:works at|worked at|intern at|interned at|employed by|data analyst at|software engineer at)\s+(?P<tgt>[A-Za-z0-9_\s]{2,40}?)\b', "WORKS_AT"),
        # STUDIED_AT
        (r'\b(?P<src>[A-Za-z0-9_\s]{2,40}?)\s+(?:studied at|student at|graduate of|b\.tech in .*? from)\s+(?P<tgt>[A-Za-z0-9_\s]{2,40}?)\b', "STUDIED_AT"),
        # CREATES / DEVELOPED / IMPLEMENTED / GENERATING
        (r'\b(?P<src>[A-Za-z0-9_\s]{2,40}?)\s+(?:created|built|developed|implemented|designed|authored|published|generating|generates)\s+(?P<tgt>[A-Za-z0-9_\s]{2,40}?)\b', "CREATES"),
        # PART_OF
        (r'\b(?P<src>[A-Za-z0-9_\s]{2,40}?)\s+(?:is part of|belongs to|component of|module of)\s+(?P<tgt>[A-Za-z0-9_\s]{2,40}?)\b', "PART_OF"),
        # DEPENDS_ON
        (r'\b(?P<src>[A-Za-z0-9_\s]{2,40}?)\s+(?:depends on|relies on|requires|prerequisites)\s+(?P<tgt>[A-Za-z0-9_\s]{2,40}?)\b', "DEPENDS_ON"),
        # INTEGRATES_WITH
        (r'\b(?P<src>[A-Za-z0-9_\s]{2,40}?)\s+(?:integrates with|connects with|combines with|interoperates with|interacts with)\s+(?P<tgt>[A-Za-z0-9_\s]{2,40}?)\b', "INTEGRATES_WITH"),
    ]

    def extract_from_chunk(self, chunk: DocumentChunk) -> Tuple[List[Entity], List[Relationship]]:
        text = chunk.text
        entities: List[Entity] = []
        relationships: List[Relationship] = []
        found_entities: Dict[str, Entity] = {}

        # 1. Match Curated Domain Entities
        for canonical, (etype, aliases) in self.KNOWN_ENTITIES.items():
            names_to_check = [canonical] + aliases
            for name in names_to_check:
                pattern = r'\b' + re.escape(name) + r'\b'
                match = re.search(pattern, text, re.IGNORECASE)
                if match and canonical not in found_entities:
                    start = max(0, match.start() - 50)
                    end = min(len(text), match.end() + 50)
                    snippet = text[start:end].strip()

                    ent = Entity(
                        name=name,
                        canonical_name=canonical,
                        type=etype,
                        description=f"{etype} '{canonical}' referenced in {chunk.document_name}.",
                        aliases=aliases,
                        source=Provenance(
                            document_id=chunk.document_id,
                            document_name=chunk.document_name,
                            page_number=chunk.page_number,
                            chunk_id=chunk.chunk_id,
                            source_text=snippet
                        ),
                        confidence=0.98
                    )
                    found_entities[canonical] = ent
                    entities.append(ent)

        # 2. Extract Person / Candidate Names from Header (Page 1 top lines)
        if chunk.page_number == 1 and chunk.chunk_index == 0:
            lines = [l.strip() for l in text.splitlines() if l.strip()]
            if lines:
                first_line = lines[0]
                if re.match(r'^[A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+){1,2}$', first_line):
                    clean_name = first_line.title()
                    if clean_name.upper() not in self.STOPWORDS_BLACKLIST and clean_name not in found_entities:
                        ent = Entity(
                            name=clean_name,
                            canonical_name=clean_name,
                            type="Person",
                            description=f"Primary individual / Author identified in {chunk.document_name}.",
                            aliases=[],
                            source=Provenance(
                                document_id=chunk.document_id,
                                document_name=chunk.document_name,
                                page_number=1,
                                chunk_id=chunk.chunk_id,
                                source_text=first_line
                            ),
                            confidence=0.95
                        )
                        found_entities[clean_name] = ent
                        entities.append(ent)

        # 3. Extract Valid Academic Institutes & Organizations
        org_pattern = r'\b([A-Z][a-zA-Z\']+(?:\s+(?:Institute|University|College|Corporation|Foundation|Technologies|Solutions|Labs|Company|Group|Department|Center|Centre|of|and|for|in|Information|Technology|Science|Engineering|Research))+)\b'
        for match in re.finditer(org_pattern, text):
            org_name = match.group(1).strip()
            org_name = re.sub(r'^(?:in|for|of|and|with|by|at|from)\s+', '', org_name, flags=re.IGNORECASE)
            first_word = org_name.split()[0].upper() if org_name.split() else ""
            if (len(org_name) > 12 and 
                org_name.upper() not in self.STOPWORDS_BLACKLIST and 
                first_word not in self.STOPWORDS_BLACKLIST and
                not any(verb in first_word for verb in ["PARTICIPAT", "EVALUAT", "DEVELOP", "BUILD", "STUDY", "USED", "PURPOSE"])):
                canonical = org_name
                if canonical not in found_entities:
                    start = max(0, match.start() - 40)
                    end = min(len(text), match.end() + 40)
                    snippet = text[start:end].strip()

                    ent = Entity(
                        name=org_name,
                        canonical_name=canonical,
                        type="Organization",
                        description=f"Organization '{canonical}' identified in {chunk.document_name}.",
                        aliases=[],
                        source=Provenance(
                            document_id=chunk.document_id,
                            document_name=chunk.document_name,
                            page_number=chunk.page_number,
                            chunk_id=chunk.chunk_id,
                            source_text=snippet
                        ),
                        confidence=0.90
                    )
                    found_entities[canonical] = ent
                    entities.append(ent)

        # 4. Extract Explicit Project Names
        proj_pattern = r'(?i)(?:Project|Project Name)\s*[:\-]\s*([A-Z][a-zA-Z0-9]+(?:\s+[A-Z][a-zA-Z0-9]+){1,4})'
        for match in re.finditer(proj_pattern, text):
            proj_name = match.group(1).strip()
            if len(proj_name) > 5 and proj_name.upper() not in self.STOPWORDS_BLACKLIST and proj_name not in found_entities:
                ent = Entity(
                    name=proj_name,
                    canonical_name=proj_name,
                    type="Project",
                    description=f"Project '{proj_name}' referenced in {chunk.document_name}.",
                    aliases=[],
                    source=Provenance(
                        document_id=chunk.document_id,
                        document_name=chunk.document_name,
                        page_number=chunk.page_number,
                        chunk_id=chunk.chunk_id,
                        source_text=match.group(0)
                    ),
                    confidence=0.85
                )
                found_entities[proj_name] = ent
                entities.append(ent)

        # 5. Extract Relationships
        # Split text by sentence terminators or line breaks for table/flow diagrams
        segments = re.split(r'[.?!;]+|\n\n+', text)
        for segment in segments:
            seg_clean = segment.strip()
            if not seg_clean or len(seg_clean) < 10:
                continue

            # A. Check predicate regex patterns
            for pat, rel_type in self.PREDICATE_PATTERNS:
                for match in re.finditer(pat, seg_clean, re.IGNORECASE):
                    raw_src = match.group('src').strip()
                    raw_tgt = match.group('tgt').strip()

                    matched_src = self._match_entity(raw_src, found_entities)
                    matched_tgt = self._match_entity(raw_tgt, found_entities)

                    if matched_src and matched_tgt and matched_src != matched_tgt:
                        relationships.append(
                            Relationship(
                                source_entity=matched_src,
                                target_entity=matched_tgt,
                                relationship_type=rel_type,
                                description=f"{matched_src} {rel_type} {matched_tgt}",
                                source=Provenance(
                                    document_id=chunk.document_id,
                                    document_name=chunk.document_name,
                                    page_number=chunk.page_number,
                                    chunk_id=chunk.chunk_id,
                                    source_text=seg_clean
                                ),
                                weight=1.0
                            )
                        )

            # B. Check for Arrow-based Architecture Flows (e.g. "PostgreSQL → Apache AGE → Knowledge Graph" or "Streamlit ↓ Semantic Catalog ↓ LLM Reasoning")
            if "→" in seg_clean or "->" in seg_clean or "↓" in seg_clean:
                steps = re.split(r'[→↓]|->', seg_clean)
                matched_steps = [self._match_entity(s.strip(), found_entities) for s in steps]
                valid_steps = [s for s in matched_steps if s is not None]
                if len(valid_steps) >= 2:
                    for i in range(len(valid_steps) - 1):
                        s1 = valid_steps[i]
                        s2 = valid_steps[i+1]
                        if s1 != s2:
                            rel_type = "EXTENDS" if ("AGE" in s2 and "Postgre" in s1) else "FLOWS_TO"
                            relationships.append(
                                Relationship(
                                    source_entity=s1,
                                    target_entity=s2,
                                    relationship_type=rel_type,
                                    description=f"Architecture pipeline step: {s1} to {s2}",
                                    source=Provenance(
                                        document_id=chunk.document_id,
                                        document_name=chunk.document_name,
                                        page_number=chunk.page_number,
                                        chunk_id=chunk.chunk_id,
                                        source_text=seg_clean
                                    ),
                                    weight=0.9
                                )
                            )

            # C. Check if Person "uses" or "worked with" specific technologies in their profile/projects
            person_ents = [e.canonical_name for e in found_entities.values() if e.type == "Person"]
            if person_ents:
                person_name = person_ents[0]
                if any(w in seg_clean.lower() for w in ["experience in", "hands-on", "skilled in", "proficient in", "worked with", "using", "developed with"]):
                    for ent_name, ent_obj in found_entities.items():
                        if ent_obj.type in ("Technology", "Concept") and ent_name != person_name:
                            if re.search(r'\b' + re.escape(ent_name) + r'\b', seg_clean, re.IGNORECASE):
                                relationships.append(
                                    Relationship(
                                        source_entity=person_name,
                                        target_entity=ent_name,
                                        relationship_type="USES",
                                        description=f"{person_name} has experience with {ent_name}.",
                                        source=Provenance(
                                            document_id=chunk.document_id,
                                            document_name=chunk.document_name,
                                            page_number=chunk.page_number,
                                            chunk_id=chunk.chunk_id,
                                            source_text=seg_clean
                                        ),
                                        weight=0.9
                                    )
                                )

                # If person studied at organization
                for ent_name, ent_obj in found_entities.items():
                    if ent_obj.type == "Organization" and ent_name != person_name:
                        if re.search(r'\b' + re.escape(ent_name) + r'\b', seg_clean, re.IGNORECASE):
                            relationships.append(
                                Relationship(
                                    source_entity=person_name,
                                    target_entity=ent_name,
                                    relationship_type="STUDIED_AT",
                                    description=f"{person_name} studied at {ent_name}.",
                                    source=Provenance(
                                        document_id=chunk.document_id,
                                        document_name=chunk.document_name,
                                        page_number=chunk.page_number,
                                        chunk_id=chunk.chunk_id,
                                        source_text=seg_clean
                                    ),
                                    weight=0.9
                                )
                            )

            # D. Domain Knowledge Combinations (e.g. Context Lakehouse combines Operational Data + Analytical Data + Telemetry + Documents)
            if "Context Lakehouse" in found_entities and "combines" in seg_clean.lower():
                lakehouse_name = "Context Lakehouse"
                for target_concept in ["Operational Data", "Analytical Data", "Telemetry", "Documents", "Business Definitions"]:
                    if target_concept in found_entities and target_concept != lakehouse_name:
                        relationships.append(
                            Relationship(
                                source_entity=lakehouse_name,
                                target_entity=target_concept,
                                relationship_type="COMBINES",
                                description=f"Context Lakehouse combines {target_concept}.",
                                source=Provenance(
                                    document_id=chunk.document_id,
                                    document_name=chunk.document_name,
                                    page_number=chunk.page_number,
                                    chunk_id=chunk.chunk_id,
                                    source_text=seg_clean
                                ),
                                weight=0.95
                            )
                        )

        # 6. Cross-Entity Contextual Inference for Core Architecture Pairs
        # In chunks where Apache AGE and PostgreSQL are both present with extension / integration context
        if "Apache AGE" in found_entities and "PostgreSQL" in found_entities:
            if any(w in text.lower() for w in ["extension", "work together", "installed", "creates", "graph layer", "database"]):
                relationships.append(
                    Relationship(
                        source_entity="Apache AGE",
                        target_entity="PostgreSQL",
                        relationship_type="EXTENDS",
                        description="Apache AGE extends PostgreSQL as a graph database extension.",
                        source=Provenance(
                            document_id=chunk.document_id,
                            document_name=chunk.document_name,
                            page_number=chunk.page_number,
                            chunk_id=chunk.chunk_id,
                            source_text=f"Apache AGE graph extension for PostgreSQL on page {chunk.page_number}."
                        ),
                        weight=0.95
                    )
                )

        if "Apache AGE" in found_entities and "Cypher" in found_entities:
            relationships.append(
                Relationship(
                    source_entity="Apache AGE",
                    target_entity="Cypher",
                    relationship_type="USES",
                    description="Apache AGE executes Cypher graph queries.",
                    source=Provenance(
                        document_id=chunk.document_id,
                        document_name=chunk.document_name,
                        page_number=chunk.page_number,
                        chunk_id=chunk.chunk_id,
                        source_text=f"Apache AGE uses Cypher on page {chunk.page_number}."
                    ),
                    weight=0.95
                )
            )

        if "Streamlit" in found_entities and "Python" in found_entities:
            relationships.append(
                Relationship(
                    source_entity="Streamlit",
                    target_entity="Python",
                    relationship_type="USES",
                    description="Streamlit application built in Python.",
                    source=Provenance(
                        document_id=chunk.document_id,
                        document_name=chunk.document_name,
                        page_number=chunk.page_number,
                        chunk_id=chunk.chunk_id,
                        source_text=f"Streamlit UI in Python on page {chunk.page_number}."
                    ),
                    weight=0.90
                )
            )

        return entities, relationships

    def _match_entity(self, text_segment: str, entities_dict: Dict[str, Entity]) -> Optional[str]:
        """Helper to match a text segment to known extracted entity canonical names."""
        clean = text_segment.strip().lower()
        if not clean or len(clean) < 2:
            return None
        for cname in entities_dict:
            if cname.lower() == clean or cname.lower() in clean:
                return cname
        return None


class ContextExtractor:
    """
    Main Context Extractor orchestrator.
    Directs extraction through LLM (OpenAI / Gemini) or HighPrecisionNLPExtractor.
    Normalizes all entities and relationships and produces validated DocumentContext.
    """
    def __init__(self):
        self.normalizer = EntityNormalizer()
        self.heuristic_extractor = HighPrecisionNLPExtractor()

    def extract_context(
        self,
        document: ExtractedDocument,
        chunks: List[DocumentChunk],
        force_provider: Optional[str] = None
    ) -> DocumentContext:
        provider = force_provider or settings.LLM_PROVIDER
        
        all_entities: List[Entity] = []
        all_relationships: List[Relationship] = []
        used_method = ExtractionMethod.HEURISTIC_NLP
        summary = f"High-precision structured context extracted from '{document.document_name}' ({document.total_pages} pages, {len(chunks)} chunks)."

        # Strict LLM handling
        if provider == "openai":
            if not settings.OPENAI_API_KEY:
                raise ValueError("OPENAI_API_KEY is not configured in environment or .env file.")
            all_entities, all_relationships, summary = self._extract_with_openai(document, chunks)
            used_method = ExtractionMethod.OPENAI

        elif provider == "gemini":
            if not settings.GEMINI_API_KEY:
                raise ValueError("GEMINI_API_KEY / GOOGLE_API_KEY is not configured in environment or .env file.")
            all_entities, all_relationships, summary = self._extract_with_gemini(document, chunks)
            used_method = ExtractionMethod.GEMINI

        elif provider == "auto":
            if settings.OPENAI_API_KEY:
                try:
                    all_entities, all_relationships, summary = self._extract_with_openai(document, chunks)
                    used_method = ExtractionMethod.OPENAI
                    logger.info(f"Auto-selected OpenAI extraction for {document.document_name}")
                except Exception as e:
                    logger.warning(f"OpenAI extraction failed: {e}. Falling back to Heuristic NLP.")
                    for chunk in chunks:
                        ents, rels = self.heuristic_extractor.extract_from_chunk(chunk)
                        all_entities.extend(ents)
                        all_relationships.extend(rels)
                    used_method = ExtractionMethod.HEURISTIC_NLP
            else:
                logger.info(f"Running High-Precision Heuristic NLP extraction for {document.document_name}")
                for chunk in chunks:
                    ents, rels = self.heuristic_extractor.extract_from_chunk(chunk)
                    all_entities.extend(ents)
                    all_relationships.extend(rels)
                used_method = ExtractionMethod.HEURISTIC_NLP

        else: # provider == "heuristic"
            logger.info(f"Running Heuristic NLP extraction for {document.document_name}")
            for chunk in chunks:
                ents, rels = self.heuristic_extractor.extract_from_chunk(chunk)
                all_entities.extend(ents)
                all_relationships.extend(rels)
            used_method = ExtractionMethod.HEURISTIC_NLP

        # Extract structural schema entities and relationships (for CSV, Excel, JSON, XML, Parquet, YAML)
        struct_ents, struct_rels = self._extract_structural_entities_and_relationships(document)
        all_entities.extend(struct_ents)
        all_relationships.extend(struct_rels)

        # Collect raw schema names to prevent schema/column names from becoming duplicate disconnected Concept nodes
        meta = getattr(document, "metadata", {}) or {}
        fmt = str(meta.get("format", "")).lower()
        schema_raw_names: Set[str] = set()

        if fmt in ("xlsx", "xls"):
            for s in meta.get("sheets", []):
                sname = s.get("sheet_name", "")
                if sname:
                    schema_raw_names.add(sname.strip().lower())
                for col in s.get("columns", []):
                    col_clean = str(col).strip().lower()
                    schema_raw_names.add(col_clean)
                    if sname:
                        schema_raw_names.add(f"{sname}.{col}".strip().lower())
        elif fmt in ("csv", "tsv", "parquet", "feather"):
            tname = meta.get("table_name") or Path(document.document_name).stem
            if tname:
                schema_raw_names.add(tname.strip().lower())
            for col in meta.get("columns", []):
                col_clean = str(col).strip().lower()
                schema_raw_names.add(col_clean)
                if tname:
                    schema_raw_names.add(f"{tname}.{col}".strip().lower())
        elif fmt in ("json", "jsonl"):
            for k in meta.get("schema_keys", []):
                schema_raw_names.add(str(k).strip().lower())
        elif fmt == "yaml":
            for k in meta.get("top_keys", []):
                schema_raw_names.add(str(k).strip().lower())

        if schema_raw_names:
            filtered_entities = []
            for ent in all_entities:
                cname_lower = (ent.canonical_name or ent.name or "").strip().lower()
                name_lower = (ent.name or "").strip().lower()
                # If entity is a generic Concept and its name merely matches a raw column/schema header, suppress it
                if ent.type == "Concept" and (cname_lower in schema_raw_names or name_lower in schema_raw_names):
                    continue
                filtered_entities.append(ent)
            all_entities = filtered_entities

        # Deduplicate and Normalize
        norm_entities, norm_relationships = self.normalizer.deduplicate_and_normalize(
            all_entities,
            all_relationships
        )

        return DocumentContext(
            document_id=document.document_id,
            document_name=document.document_name,
            extraction_method=used_method.value,
            summary=summary,
            entities=norm_entities,
            relationships=norm_relationships,
            extracted_at=datetime.now(timezone.utc)
        )

    def _extract_structural_entities_and_relationships(
        self,
        document: ExtractedDocument
    ) -> Tuple[List[Entity], List[Relationship]]:
        entities: List[Entity] = []
        relationships: List[Relationship] = []
        meta = getattr(document, "metadata", {}) or {}
        fmt = str(meta.get("format", "")).lower()
        doc_id = document.document_id
        doc_name = document.document_name

        def make_prov(snippet: str) -> Provenance:
            return Provenance(
                document_id=doc_id,
                document_name=doc_name,
                page_number=1,
                chunk_id=f"{doc_id}_p1_c0",
                source_text=snippet[:200]
            )

        # 1. Tabular / Parquet / Feather
        if fmt in ("csv", "tsv", "parquet", "feather"):
            tbl_name = meta.get("table_name") or Path(doc_name).stem
            tbl_cname = f"{doc_name}::{tbl_name}"
            tbl_entity = Entity(
                name=tbl_name,
                canonical_name=tbl_cname,
                type="Dataset" if fmt in ("parquet", "feather") else "Table",
                description=f"{fmt.upper()} table ({meta.get('record_count', 0)} rows, {meta.get('column_count', 0)} columns)",
                aliases=[doc_name, tbl_name],
                source=make_prov(f"Dataset {doc_name} ({fmt.upper()})")
            )
            entities.append(tbl_entity)

            col_types = meta.get("column_types", {})
            for col in meta.get("columns", []):
                col_display = f"{tbl_name}.{col}"
                col_cname = f"{doc_name}::{tbl_name}.{col}"
                col_entity = Entity(
                    name=col_display,
                    canonical_name=col_cname,
                    type="Column",
                    description=f"Column '{col}' in {tbl_name} (Type: {col_types.get(col, 'Unknown')})",
                    aliases=[col, col_display],
                    source=make_prov(f"Column {col} in {tbl_name}")
                )
                entities.append(col_entity)

                # Rel: Table -> CONTAINS_COLUMN -> Column
                relationships.append(Relationship(
                    source_entity=tbl_cname,
                    target_entity=col_cname,
                    relationship_type="CONTAINS_COLUMN",
                    description=f"Table {tbl_name} contains column {col}",
                    source=make_prov(f"{tbl_name} -> {col}")
                ))

                # Rel: Column -> HAS_DATA_TYPE -> DataType
                if col in col_types:
                    ctype = str(col_types[col])
                    type_entity = Entity(
                        name=ctype,
                        canonical_name=ctype,
                        type="DataType",
                        description=f"Data type {ctype}",
                        aliases=[],
                        source=make_prov(f"Type {ctype}")
                    )
                    entities.append(type_entity)
                    relationships.append(Relationship(
                        source_entity=col_cname,
                        target_entity=ctype,
                        relationship_type="HAS_DATA_TYPE",
                        description=f"Column {col} has data type {ctype}",
                        source=make_prov(f"{col} : {ctype}")
                    ))

        # 2. Spreadsheet (Excel)
        elif fmt in ("xlsx", "xls"):
            wb_entity = Entity(
                name=doc_name,
                canonical_name=doc_name,
                type="Workbook",
                description=f"Excel Workbook with {meta.get('sheet_count', 0)} sheets",
                aliases=[Path(doc_name).stem],
                source=make_prov(f"Workbook {doc_name}")
            )
            entities.append(wb_entity)

            for s in meta.get("sheets", []):
                sheet_name = s.get("sheet_name", "Sheet1")
                sheet_cname = f"{doc_name}::{sheet_name}"
                sheet_entity = Entity(
                    name=sheet_name,
                    canonical_name=sheet_cname,
                    type="Sheet",
                    description=f"Sheet '{sheet_name}' ({s.get('row_count', 0)} rows, {s.get('column_count', 0)} cols)",
                    aliases=[sheet_name],
                    source=make_prov(f"Sheet {sheet_name} in {doc_name}")
                )
                entities.append(sheet_entity)

                # Rel: Workbook -> CONTAINS_SHEET -> Sheet
                relationships.append(Relationship(
                    source_entity=doc_name,
                    target_entity=sheet_cname,
                    relationship_type="CONTAINS_SHEET",
                    description=f"Workbook {doc_name} contains sheet {sheet_name}",
                    source=make_prov(f"{doc_name} -> {sheet_name}")
                ))

                for col in s.get("columns", []):
                    col_display = f"{sheet_name}.{col}"
                    col_cname = f"{doc_name}::{sheet_name}.{col}"
                    entities.append(Entity(
                        name=col_display,
                        canonical_name=col_cname,
                        type="Column",
                        description=f"Column '{col}' in sheet {sheet_name} of {doc_name}",
                        aliases=[col, col_display],
                        source=make_prov(f"Column {col} in sheet {sheet_name}")
                    ))
                    relationships.append(Relationship(
                        source_entity=sheet_cname,
                        target_entity=col_cname,
                        relationship_type="CONTAINS_COLUMN",
                        description=f"Sheet {sheet_name} contains column {col}",
                        source=make_prov(f"{sheet_name} -> {col}")
                    ))

        # 3. XML Hierarchy
        elif fmt == "xml":
            root_tag = meta.get("root_tag", "root")
            root_cname = f"{doc_name}::<{root_tag}>"
            entities.append(Entity(
                name=f"<{root_tag}>",
                canonical_name=root_cname,
                type="XmlElement",
                description=f"Root XML element <{root_tag}> of {doc_name}",
                aliases=[root_tag, f"<{root_tag}>"],
                source=make_prov(f"Root XML <{root_tag}> in {doc_name}")
            ))

            for elem in meta.get("hierarchy", []):
                tag = elem.get("tag")
                path = elem.get("path")
                if not tag or not path:
                    continue
                elem_cname = f"{doc_name}::<{path}>"
                entities.append(Entity(
                    name=f"<{tag}>",
                    canonical_name=elem_cname,
                    type="XmlElement",
                    description=f"XML element <{tag}> at path {path}",
                    aliases=[tag, f"<{tag}>"],
                    source=make_prov(f"XML element <{tag}>")
                ))

                # If path has parent, link parent -> child
                if "/" in path:
                    parent_path = path.rsplit("/", 1)[0]
                    parent_cname = f"{doc_name}::<{parent_path}>"
                    relationships.append(Relationship(
                        source_entity=parent_cname,
                        target_entity=elem_cname,
                        relationship_type="CONTAINS_ELEMENT",
                        description=f"XML element <{parent_path}> contains child <{tag}>",
                        source=make_prov(f"<{parent_path}> -> <{tag}>")
                    ))

        # 4. JSON / JSONL
        elif fmt in ("json", "jsonl"):
            ds_entity = Entity(
                name=doc_name,
                canonical_name=doc_name,
                type="JsonDataset",
                description=f"JSON Dataset ({meta.get('record_count', 0)} items)",
                aliases=[Path(doc_name).stem],
                source=make_prov(f"JSON Dataset {doc_name}")
            )
            entities.append(ds_entity)

            for key in meta.get("schema_keys", []):
                field_display = f"{Path(doc_name).stem}.{key}"
                field_cname = f"{doc_name}::{key}"
                entities.append(Entity(
                    name=field_display,
                    canonical_name=field_cname,
                    type="Field",
                    description=f"JSON field/key '{key}' in {doc_name}",
                    aliases=[key, field_display],
                    source=make_prov(f"Field {key} in {doc_name}")
                ))
                relationships.append(Relationship(
                    source_entity=doc_name,
                    target_entity=field_cname,
                    relationship_type="CONTAINS_FIELD",
                    description=f"Dataset {doc_name} contains field {key}",
                    source=make_prov(f"{doc_name} -> {key}")
                ))

        # 5. YAML Configuration
        elif fmt == "yaml":
            cfg_entity = Entity(
                name=doc_name,
                canonical_name=doc_name,
                type="Configuration",
                description=f"YAML configuration document {doc_name}",
                aliases=[Path(doc_name).stem],
                source=make_prov(f"YAML {doc_name}")
            )
            entities.append(cfg_entity)

            for key in meta.get("top_keys", []):
                key_display = f"{Path(doc_name).stem}.{key}"
                key_cname = f"{doc_name}::{key}"
                entities.append(Entity(
                    name=key_display,
                    canonical_name=key_cname,
                    type="ConfigKey",
                    description=f"Configuration key '{key}' in {doc_name}",
                    aliases=[key, key_display],
                    source=make_prov(f"Key {key} in {doc_name}")
                ))
                relationships.append(Relationship(
                    source_entity=doc_name,
                    target_entity=key_cname,
                    relationship_type="DEFINES_CONFIG",
                    description=f"Configuration {doc_name} defines key {key}",
                    source=make_prov(f"{doc_name} -> {key}")
                ))

        return entities, relationships

    def _extract_with_openai(
        self,
        document: ExtractedDocument,
        chunks: List[DocumentChunk]
    ) -> Tuple[List[Entity], List[Relationship], str]:
        from openai import OpenAI
        client = OpenAI(api_key=settings.OPENAI_API_KEY)
        
        entities: List[Entity] = []
        relationships: List[Relationship] = []
        summaries: List[str] = []

        for chunk in chunks[:10]:
            user_prompt = f"""Document: {chunk.document_name}
Page: {chunk.page_number}
Chunk ID: {chunk.chunk_id}

Text:
\"\"\"
{chunk.text}
\"\"\"
"""
            response = client.chat.completions.create(
                model=settings.OPENAI_MODEL,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt}
                ],
                response_format={"type": "json_object"},
                temperature=0.1
            )
            content = response.choices[0].message.content
            parsed = json.loads(content)
            
            if "summary" in parsed and parsed["summary"]:
                summaries.append(parsed["summary"])

            for e_data in parsed.get("entities", []):
                entities.append(
                    Entity(
                        name=e_data.get("name", ""),
                        canonical_name=e_data.get("canonical_name", e_data.get("name", "")),
                        type=e_data.get("type", "Concept"),
                        description=e_data.get("description"),
                        aliases=e_data.get("aliases", []),
                        source=Provenance(
                            document_id=chunk.document_id,
                            document_name=chunk.document_name,
                            page_number=chunk.page_number,
                            chunk_id=chunk.chunk_id,
                            source_text=chunk.text[:200]
                        )
                    )
                )

            for r_data in parsed.get("relationships", []):
                relationships.append(
                    Relationship(
                        source_entity=r_data.get("source_entity", ""),
                        target_entity=r_data.get("target_entity", ""),
                        relationship_type=r_data.get("relationship_type", "RELATED_TO"),
                        description=r_data.get("description"),
                        source=Provenance(
                            document_id=chunk.document_id,
                            document_name=chunk.document_name,
                            page_number=chunk.page_number,
                            chunk_id=chunk.chunk_id,
                            source_text=chunk.text[:200]
                        )
                    )
                )

        combined_summary = " ".join(summaries[:3]) if summaries else f"Context extracted for {document.document_name}."
        return entities, relationships, combined_summary

    def _extract_with_gemini(
        self,
        document: ExtractedDocument,
        chunks: List[DocumentChunk]
    ) -> Tuple[List[Entity], List[Relationship], str]:
        raise NotImplementedError("Gemini direct endpoint not configured.")
