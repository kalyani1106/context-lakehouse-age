"""
Query Analyzer for Context Engine
=================================
Deterministic query intent classification, entity extraction, symbol identification,
and keyword parsing for targeted hybrid retrieval.
"""

import re
from typing import List, Dict, Any, Set, Tuple
from .models import QueryIntent, QueryAnalysisResult


class QueryAnalyzer:
    """
    Deterministic rule-based and NLP-assisted query analyzer.
    Extracts semantic intent, code symbols, file paths, domain entities,
    and search keywords without external LLM dependencies.
    """

    STOPWORDS: Set[str] = {
        "a", "about", "above", "after", "again", "against", "all", "am", "an", "and",
        "any", "are", "aren't", "as", "at", "be", "because", "been", "before", "being",
        "below", "between", "both", "but", "by", "can", "can't", "cannot", "could",
        "couldn't", "did", "didn't", "do", "does", "doesn't", "doing", "don't", "down",
        "during", "each", "few", "for", "from", "further", "had", "hadn't", "has",
        "hasn't", "have", "haven't", "having", "he", "he'd", "he'll", "he's", "her",
        "here", "here's", "hers", "herself", "him", "himself", "his", "how", "how's",
        "i", "i'd", "i'll", "i'm", "i've", "if", "in", "into", "is", "isn't", "it",
        "it's", "its", "itself", "let's", "me", "more", "most", "mustn't", "my",
        "myself", "no", "nor", "not", "of", "off", "on", "once", "only", "or",
        "other", "ought", "our", "ours", "ourselves", "out", "over", "own", "same",
        "shan't", "she", "she'd", "she'll", "she's", "should", "shouldn't", "so",
        "some", "such", "than", "that", "that's", "the", "their", "theirs", "them",
        "themselves", "then", "there", "there's", "these", "they", "they'd", "they'll",
        "they're", "they've", "this", "those", "through", "to", "too", "under",
        "until", "up", "very", "was", "wasn't", "we", "we'd", "we'll", "we're",
        "we've", "were", "weren't", "what", "what's", "when", "when's", "where",
        "where's", "which", "while", "who", "who's", "whom", "why", "why's", "with",
        "won't", "would", "wouldn't", "you", "you'd", "you'll", "you're", "you've",
        "your", "yours", "yourself", "yourselves", "tell", "show", "give", "find",
        "explain", "describe", "list", "work", "works", "working", "get"
    }

    INTENT_PATTERNS: List[Tuple[QueryIntent, List[str]]] = [
        (QueryIntent.AUTHENTICATION, [
            r"\bauth\w*\b", r"\blogin\b", r"\bjwt\b", r"\btoken[s]?\b", r"\bbearer\b",
            r"\bpassword[s]?\b", r"\bpermission[s]?\b", r"\brole[s]?\b", r"\bcredential[s]?\b",
            r"\boauth\b", r"\bsession[s]?\b", r"\bapi[-_ ]?key[s]?\b", r"\bverif\w*\b"
        ]),
        (QueryIntent.API_ROUTES, [
            r"\bapi[s]?\b", r"\broute[s]?\b", r"\bendpoint[s]?\b", r"\brest\b",
            r"\bhttp\b", r"\bget\b", r"\bpost\b", r"\bput\b", r"\bdelete\b",
            r"\bpatch\b", r"\bhandler[s]?\b", r"\bfastapi\b", r"\brouter[s]?\b",
            r"\bcontroller[s]?\b", r"\brequest[s]?\b", r"\bresponse[s]?\b"
        ]),
        (QueryIntent.DEPENDENCY, [
            r"\bdepend\w*\b", r"\bimport[s]?\b", r"\brequire\w*\b",
            r"\bpackage[s]?\b", r"\blibrar\w*\b", r"\bmodule[s]?\b", r"\binherit\w*\b",
            r"\bextend[s]?\b", r"\bsubclass\w*\b", r"\bcaller[s]?\b", r"\bcallee[s]?\b"
        ]),
        (QueryIntent.DATA_FLOW, [
            r"\bflow\b", r"\bdata[-_ ]?flow\b", r"\bpipeline[s]?\b", r"\bprocess\w*\b",
            r"\betl\b", r"\bingest\w*\b", r"\blifecycle\b", r"\bstream\w*\b",
            r"\btransform\w*\b", r"\bstep[s]?\b", r"\bstage[s]?\b"
        ]),
        (QueryIntent.SCHEMA, [
            r"\bschema[s]?\b", r"\btable[s]?\b", r"\bcolumn[s]?\b",
            r"\bsheet[s]?\b", r"\bworkbook[s]?\b", r"\bfield[s]?\b", r"\bentity\b",
            r"\bentities\b", r"\brelationship[s]?\b", r"\bvertex\b", r"\bvertices\b",
            r"\bedge[s]?\b", r"\bgraph[s]?\b", r"\bage\b", r"\bcypher\b", r"\bmodel[s]?\b",
            r"\bdatabase[s]?\b", r"\bpostgres\w*\b", r"\bsql\b", r"\bconnect\w*\b"
        ]),
        (QueryIntent.ARCHITECTURE, [
            r"\barchitect\w*\b", r"\bstructure[s]?\b", r"\boverview\b", r"\bhigh[-_ ]?level\b",
            r"\bcomponent[s]?\b", r"\bdesign\b", r"\bsystem[s]?\b", r"\blayer[s]?\b",
            r"\blakehouse\b", r"\bframework[s]?\b", r"\bstack[s]?\b"
        ])
    ]

    def analyze(self, query: str, default_filters: Optional[Dict[str, Any]] = None) -> QueryAnalysisResult:
        """
        Analyze a query string and extract semantic intent, entities, symbols, and keywords.
        """
        raw_query = query.strip()
        if not raw_query:
            return QueryAnalysisResult(
                raw_query="",
                intent=QueryIntent.GENERAL,
                extracted_entities=[],
                keywords=[],
                detected_targets=[],
                filters=default_filters or {}
            )

        intent = self._classify_intent(raw_query)
        extracted_entities = self._extract_entities(raw_query)
        detected_targets = self._extract_targets(raw_query)
        keywords = self._extract_keywords(raw_query, extracted_entities)

        filters = dict(default_filters or {})
        # If query contains explicit file path or repo hint, enrich filters
        for target in detected_targets:
            if "." in target and any(target.endswith(ext) for ext in [".py", ".js", ".json", ".md", ".pdf", ".xlsx", ".csv"]):
                filters.setdefault("target_file", target)

        return QueryAnalysisResult(
            raw_query=raw_query,
            intent=intent,
            extracted_entities=extracted_entities,
            keywords=keywords,
            detected_targets=detected_targets,
            filters=filters
        )

    def _classify_intent(self, query: str) -> QueryIntent:
        """Score intents based on keyword matches and return top-scoring intent."""
        scores: Dict[QueryIntent, int] = {intent: 0 for intent, _ in self.INTENT_PATTERNS}
        query_lower = query.lower()

        for intent, patterns in self.INTENT_PATTERNS:
            for pattern in patterns:
                matches = re.findall(pattern, query_lower)
                if matches:
                    scores[intent] += len(matches)

        best_intent = QueryIntent.GENERAL
        max_score = 0
        for intent, score in scores.items():
            if score > max_score:
                max_score = score
                best_intent = intent

        return best_intent

    def _extract_entities(self, query: str) -> List[str]:
        """Extract capitalized multi-word phrases, quoted entities, and distinct code tokens."""
        entities: List[str] = []

        # 1. Quoted terms: "Apache AGE", 'Git Graphify'
        quoted = re.findall(r'["\']([^"\']+)["\']', query)
        for q in quoted:
            cleaned = q.strip()
            if cleaned and cleaned not in entities:
                entities.append(cleaned)

        # 2. PascalCase / CamelCase symbols: ContextEngine, LakehouseStorage, age_client
        camel_case = re.findall(r'\b[A-Z][a-zA-Z0-9]+(?:[A-Z][a-zA-Z0-9]+)+\b', query)
        for cc in camel_case:
            if cc not in entities and len(cc) > 3:
                entities.append(cc)

        # 3. Capitalized multi-word noun phrases: "Knowledge Graph", "FastAPI App"
        noun_phrases = re.findall(r'\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)+\b', query)
        for np in noun_phrases:
            if np not in entities and np.lower() not in self.STOPWORDS:
                entities.append(np)

        # 4. Acronyms: JWT, API, AST, AGE, SQL, PDF, CSV, REST, LLM, ETL
        acronyms = re.findall(r'\b[A-Z]{2,6}\b', query)
        for ac in acronyms:
            if ac not in entities and ac.lower() not in self.STOPWORDS:
                entities.append(ac)

        return entities

    def _extract_targets(self, query: str) -> List[str]:
        """Extract file names, module paths, or code symbols from the query."""
        targets: List[str] = []

        # File paths: foo.py, app/main.py, test.pdf, etc.
        file_matches = re.findall(r'\b[\w\-_/\\]+\.(?:py|js|json|md|pdf|xlsx|xls|csv|tsv|parquet|html|xml|yaml|yml)\b', query, re.IGNORECASE)
        for fm in file_matches:
            if fm not in targets:
                targets.append(fm)

        # Python / JS function or method signatures: def foo(), get_data(), Class.method
        code_identifiers = re.findall(r'\b[a-zA-Z_][a-zA-Z0-9_]{2,}\(\)', query)
        for ci in code_identifiers:
            clean_name = ci.rstrip("()")
            if clean_name not in targets and clean_name.lower() not in self.STOPWORDS:
                targets.append(clean_name)

        # snake_case tokens with underscores: git_graph_service, age_client
        snake_case = re.findall(r'\b[a-z]+(?:_[a-z0-9]+)+\b', query)
        for sc in snake_case:
            if sc not in targets and sc.lower() not in self.STOPWORDS:
                targets.append(sc)

        return targets

    def _extract_keywords(self, query: str, extracted_entities: List[str]) -> List[str]:
        """Extract meaningful, clean keywords from the query text."""
        # Clean text
        text = re.sub(r'[^a-zA-Z0-9_\-\s]', ' ', query.lower())
        tokens = text.split()

        keywords: List[str] = []
        for t in tokens:
            t_clean = t.strip()
            if len(t_clean) >= 2 and t_clean not in self.STOPWORDS:
                if t_clean not in keywords:
                    keywords.append(t_clean)

        # Ensure lowercase versions of extracted entities are present
        for ent in extracted_entities:
            ent_low = ent.lower()
            if ent_low not in keywords and len(ent_low) >= 2:
                keywords.append(ent_low)

        return keywords
