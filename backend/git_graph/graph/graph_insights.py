"""
Human-Readable Knowledge Graph Insights Service
===============================================
Translates Apache AGE graph structures (vertices and directed edges)
into structured, deterministic, and human-readable architectural insights,
technology stacks, project hierarchies, file rankings, class/function definitions,
dependency analyses, execution flows, and predefined interactive Q&A.
"""

import re
import json
import logging
from typing import List, Dict, Any, Optional, Tuple, Set
from datetime import datetime, timezone
from pydantic import BaseModel, Field

from backend.config import settings
from backend.git_graph.config import git_settings
from backend.graph.age_client import AGEClient
from backend.git_graph.graph.git_graph_service import GitGraphService

logger = logging.getLogger("graph_insights")

# -------------------------------------------------------------------------
# Pydantic Insight Data Models
# -------------------------------------------------------------------------

class ProvenanceInfo(BaseModel):
    file_path: Optional[str] = None
    start_line: Optional[int] = None
    end_line: Optional[int] = None
    commit_sha: Optional[str] = None
    extraction_method: Optional[str] = None
    source_snippet: Optional[str] = None

class TechStackItem(BaseModel):
    name: str
    category: str  # 'Technology' or 'Library'
    description: Optional[str] = None
    version: Optional[str] = None
    used_in_files_count: int = 0
    provenance: Optional[ProvenanceInfo] = None

class FileInsight(BaseModel):
    file_path: str
    name: str
    file_type: str = "SOURCE_CODE"
    line_count: int = 0
    definitions_count: int = 0
    imports_count: int = 0
    in_degree: int = 0
    out_degree: int = 0
    importance_score: float = 0.0
    defined_classes: List[str] = Field(default_factory=list)
    defined_functions: List[str] = Field(default_factory=list)
    imported_libraries: List[str] = Field(default_factory=list)
    provenance: Optional[ProvenanceInfo] = None

class ClassInsight(BaseModel):
    name: str
    canonical_id: str
    file_path: str
    line_range: str = ""
    commit_sha: Optional[str] = None
    extraction_method: Optional[str] = None
    methods: List[str] = Field(default_factory=list)
    description: Optional[str] = None
    source_snippet: Optional[str] = None

class FunctionInsight(BaseModel):
    name: str
    canonical_id: str
    file_path: str
    line_range: str = ""
    is_async: bool = False
    parent_class: Optional[str] = None
    commit_sha: Optional[str] = None
    extraction_method: Optional[str] = None
    description: Optional[str] = None
    source_snippet: Optional[str] = None

class ApiInsight(BaseModel):
    endpoint: str
    http_method: str = "GET"
    handler_name: Optional[str] = None
    file_path: str = ""
    line_number: int = 1
    provenance: Optional[ProvenanceInfo] = None

class DependencyInsight(BaseModel):
    source_file: str
    relationship_type: str  # IMPORTS, DEPENDS_ON, USES
    target_entity: str
    target_type: str  # Library, Technology, File, Module
    line_number: Optional[int] = None

class CodeFlowItem(BaseModel):
    step_number: int
    from_entity: str
    from_type: str
    to_entity: str
    to_type: str
    relationship_type: str
    file_path: Optional[str] = None
    description: Optional[str] = None

class GraphStatsSummary(BaseModel):
    total_vertices: int = 0
    total_edges: int = 0
    vertices_by_label: Dict[str, int] = Field(default_factory=dict)
    edges_by_type: Dict[str, int] = Field(default_factory=dict)

class GraphInsights(BaseModel):
    repository_name: str
    repository_url: str = ""
    branch: str = "main"
    commit_sha: str = ""
    overview: str = ""
    architecture_summary: str = ""
    dependency_summary: str = ""
    statistics: GraphStatsSummary = Field(default_factory=GraphStatsSummary)
    technologies: List[TechStackItem] = Field(default_factory=list)
    libraries: List[TechStackItem] = Field(default_factory=list)
    project_structure_text: str = ""
    project_tree: Dict[str, Any] = Field(default_factory=dict)
    important_files: List[FileInsight] = Field(default_factory=list)
    classes: List[ClassInsight] = Field(default_factory=list)
    functions: List[FunctionInsight] = Field(default_factory=list)
    apis: List[ApiInsight] = Field(default_factory=list)
    services: List[str] = Field(default_factory=list)
    concepts: List[str] = Field(default_factory=list)
    dependencies: List[DependencyInsight] = Field(default_factory=list)
    code_flows: List[CodeFlowItem] = Field(default_factory=list)
    generated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return self.model_dump()


# -------------------------------------------------------------------------
# GraphInsightsService
# -------------------------------------------------------------------------

class GraphInsightsService:
    """
    Analyzes vertices and edges in Apache AGE to generate structured,
    deterministic knowledge graph insights for any ingested repository.
    """

    def __init__(self, age_client: Optional[AGEClient] = None, graph_name: Optional[str] = None):
        self.age_client = age_client or AGEClient()
        self.graph_name = graph_name or git_settings.GIT_AGE_GRAPH_NAME
        self.git_service = GitGraphService(self.age_client, self.graph_name)

    @staticmethod
    def cypher_val(val: Any) -> str:
        return GitGraphService.cypher_val(val)

    def get_repository_insights(self, repo_name: str) -> GraphInsights:
        """
        Generate complete structured insights for a specific repository.
        """
        # 1. Fetch Repository Metadata
        repo_q = f"MATCH (r:Repository) WHERE r.name = {self.cypher_val(repo_name)} OR r.repository_name = {self.cypher_val(repo_name)} RETURN r LIMIT 1"
        repo_res = self.age_client.execute_cypher(repo_q, columns=["r"], graph_name=self.graph_name)
        
        repo_url = ""
        branch = "main"
        commit_sha = ""
        if repo_res and isinstance(repo_res[0].get("r"), dict):
            r_props = repo_res[0]["r"].get("properties", {})
            repo_url = r_props.get("url") or r_props.get("repository_url") or ""
            branch = r_props.get("branch") or "main"
            commit_sha = r_props.get("commit_sha") or ""

        # 2. Fetch Graph Raw Elements for this repository
        raw_graph = self.git_service.get_repository_graph(repo_name=repo_name, limit=1000)
        nodes = raw_graph.get("nodes", [])
        edges = raw_graph.get("edges", [])

        # If repo_url/commit_sha still empty, pull from nodes
        if not commit_sha:
            for n in nodes:
                props = n.get("properties", {})
                if props.get("commit_sha"):
                    commit_sha = props.get("commit_sha")
                if not repo_url and (props.get("repository_url") or props.get("url")):
                    repo_url = props.get("repository_url") or props.get("url")
                if commit_sha and repo_url:
                    break

        # 3. Calculate Statistics
        stats_by_label: Dict[str, int] = {}
        for n in nodes:
            lbl = n.get("entity_type") or n.get("label", "Concept")
            stats_by_label[lbl] = stats_by_label.get(lbl, 0) + 1

        edges_by_type: Dict[str, int] = {}
        for e in edges:
            rel = e.get("relationship_type") or e.get("label", "RELATED_TO")
            edges_by_type[rel] = edges_by_type.get(rel, 0) + 1

        stats_summary = GraphStatsSummary(
            total_vertices=len(nodes),
            total_edges=len(edges),
            vertices_by_label=stats_by_label,
            edges_by_type=edges_by_type
        )

        # 4. Extract Technologies and Libraries
        technologies, libraries = self._extract_tech_and_libraries(nodes, edges)

        # 5. Build Project Tree
        project_tree, project_structure_text = self._build_project_tree(nodes)

        # 6. Extract and Rank Files
        important_files = self._extract_important_files(nodes, edges)

        # 7. Extract Classes and Methods
        classes = self._extract_classes(nodes, edges)

        # 8. Extract Standalone Functions
        functions = self._extract_functions(nodes, classes)

        # 9. Extract APIs
        apis = self._extract_apis(nodes)

        # 10. Extract Services and Concepts
        services = sorted(list({n["name"] for n in nodes if (n.get("entity_type") or n.get("label")) == "Service"}))
        concepts = sorted(list({n["name"] for n in nodes if (n.get("entity_type") or n.get("label")) == "Concept"}))

        # 11. Extract Dependencies
        dependencies = self._extract_dependencies(nodes, edges)

        # 12. Extract Code Flows
        code_flows = self._extract_code_flows(nodes, edges)

        # 13. Deterministic Summaries
        overview = self._generate_overview(repo_name, len(nodes), len(edges), len(important_files), len(classes), len(functions), technologies, libraries, apis)
        architecture_summary = self._generate_architecture_summary(repo_name, important_files, classes, apis, services, technologies)
        dependency_summary = self._generate_dependency_summary(libraries, dependencies)

        return GraphInsights(
            repository_name=repo_name,
            repository_url=repo_url,
            branch=branch,
            commit_sha=commit_sha,
            overview=overview,
            architecture_summary=architecture_summary,
            dependency_summary=dependency_summary,
            statistics=stats_summary,
            technologies=technologies,
            libraries=libraries,
            project_structure_text=project_structure_text,
            project_tree=project_tree,
            important_files=important_files,
            classes=classes,
            functions=functions,
            apis=apis,
            services=services,
            concepts=concepts,
            dependencies=dependencies,
            code_flows=code_flows
        )

    # -------------------------------------------------------------------------
    # Helper Extractors
    # -------------------------------------------------------------------------

    def _extract_tech_and_libraries(self, nodes: List[Dict[str, Any]], edges: List[Dict[str, Any]]) -> Tuple[List[TechStackItem], List[TechStackItem]]:
        """Extract technologies and libraries with usage counts and provenance."""
        tech_map: Dict[str, TechStackItem] = {}
        lib_map: Dict[str, TechStackItem] = {}

        # Count incoming edges to find how many files import/use each library/tech
        target_counts: Dict[str, int] = {}
        node_id_to_name: Dict[Any, str] = {n["id"]: n["name"] for n in nodes if "id" in n}

        for e in edges:
            tgt_id = e.get("target")
            if tgt_id in node_id_to_name:
                tname = node_id_to_name[tgt_id]
                target_counts[tname] = target_counts.get(tname, 0) + 1

        for n in nodes:
            lbl = n.get("entity_type") or n.get("label")
            props = n.get("properties", {})
            name = n.get("name", "")
            if not name:
                continue

            prov = ProvenanceInfo(
                file_path=n.get("file_path") or props.get("file_path"),
                start_line=n.get("start_line") or props.get("start_line"),
                end_line=n.get("end_line") or props.get("end_line"),
                commit_sha=props.get("commit_sha"),
                extraction_method=n.get("extraction_method") or props.get("extraction_method"),
                source_snippet=n.get("source_snippet") or props.get("source_snippet")
            )

            if lbl == "Technology":
                if name not in tech_map:
                    tech_map[name] = TechStackItem(
                        name=name,
                        category="Technology",
                        description=props.get("description"),
                        version=props.get("version"),
                        used_in_files_count=target_counts.get(name, 0),
                        provenance=prov
                    )
            elif lbl == "Library":
                if name not in lib_map:
                    lib_map[name] = TechStackItem(
                        name=name,
                        category="Library",
                        description=props.get("description"),
                        version=props.get("version"),
                        used_in_files_count=target_counts.get(name, 0),
                        provenance=prov
                    )

        tech_list = sorted(list(tech_map.values()), key=lambda x: x.used_in_files_count, reverse=True)
        lib_list = sorted(list(lib_map.values()), key=lambda x: x.used_in_files_count, reverse=True)
        return tech_list, lib_list

    def _build_project_tree(self, nodes: List[Dict[str, Any]]) -> Tuple[Dict[str, Any], str]:
        """Construct a hierarchical directory tree and ascii visualization."""
        file_paths = []
        for n in nodes:
            lbl = n.get("entity_type") or n.get("label")
            if lbl in ("File", "Directory"):
                p = n.get("file_path") or n.get("name")
                if p and p != "Unnamed":
                    file_paths.append(p.replace("\\", "/"))

        if not file_paths:
            # Fallback to any file_paths present in other vertices
            for n in nodes:
                p = n.get("file_path")
                if p:
                    file_paths.append(p.replace("\\", "/"))

        file_paths = sorted(list(set(file_paths)))

        tree: Dict[str, Any] = {}
        for path in file_paths:
            parts = [part for part in path.split("/") if part]
            curr = tree
            for part in parts:
                if part not in curr:
                    curr[part] = {}
                curr = curr[part]

        # Generate ASCII Tree Representation
        lines: List[str] = ["📁 / (repository root)"]

        def render_branch(node: Dict[str, Any], prefix: str = ""):
            items = sorted(node.keys())
            for idx, item in enumerate(items):
                is_last = (idx == len(items) - 1)
                connector = "└── " if is_last else "├── "
                sub_prefix = "    " if is_last else "│   "
                is_dir = bool(node[item])
                icon = "📁 " if is_dir else "📄 "
                lines.append(f"{prefix}{connector}{icon}{item}")
                if is_dir:
                    render_branch(node[item], prefix + sub_prefix)

        render_branch(tree)
        return tree, "\n".join(lines)

    def _extract_important_files(self, nodes: List[Dict[str, Any]], edges: List[Dict[str, Any]]) -> List[FileInsight]:
        """Rank files based on architectural weight, definitions count, imports, and degree."""
        file_nodes = [n for n in nodes if (n.get("entity_type") or n.get("label")) == "File"]
        node_id_to_file = {n["id"]: n for n in file_nodes if "id" in n}

        # Calculate degrees
        in_degrees: Dict[Any, int] = {}
        out_degrees: Dict[Any, int] = {}
        for e in edges:
            src = e.get("source")
            tgt = e.get("target")
            out_degrees[src] = out_degrees.get(src, 0) + 1
            in_degrees[tgt] = in_degrees.get(tgt, 0) + 1

        # Associate definitions and imports by file_path
        file_classes: Dict[str, List[str]] = {}
        file_functions: Dict[str, List[str]] = {}
        file_libraries: Dict[str, List[str]] = {}

        for n in nodes:
            lbl = n.get("entity_type") or n.get("label")
            fp = n.get("file_path", "")
            name = n.get("name", "")
            if not fp or not name:
                continue

            if lbl == "Class":
                file_classes.setdefault(fp, []).append(name)
            elif lbl == "Function":
                file_functions.setdefault(fp, []).append(name)
            elif lbl == "Library":
                file_libraries.setdefault(fp, []).append(name)

        results: List[FileInsight] = []
        for fn in file_nodes:
            nid = fn.get("id")
            props = fn.get("properties", {})
            fp = fn.get("file_path") or fn.get("name", "")
            name = fn.get("name") or fp.split("/")[-1]

            classes_def = file_classes.get(fp, [])
            funcs_def = file_functions.get(fp, [])
            libs_imp = file_libraries.get(fp, [])

            definitions_count = len(classes_def) + len(funcs_def)
            imports_count = len(libs_imp)
            in_deg = in_degrees.get(nid, 0)
            out_deg = out_degrees.get(nid, 0)
            line_count = props.get("line_count") or props.get("total_lines") or (props.get("end_line", 0) - props.get("start_line", 0) + 1) or 0

            # Deterministic importance scoring formula:
            # Importance = 3.0 * in_degree + 2.0 * definitions + 1.0 * out_degree + 0.01 * line_count
            score = (3.0 * in_deg) + (2.0 * definitions_count) + (1.0 * out_deg) + (0.01 * float(line_count))

            prov = ProvenanceInfo(
                file_path=fp,
                start_line=fn.get("start_line") or props.get("start_line") or 1,
                end_line=fn.get("end_line") or props.get("end_line") or max(1, line_count),
                commit_sha=props.get("commit_sha"),
                extraction_method=fn.get("extraction_method") or props.get("extraction_method"),
                source_snippet=fn.get("source_snippet") or props.get("source_snippet")
            )

            insight = FileInsight(
                file_path=fp,
                name=name,
                file_type=props.get("file_type", "SOURCE_CODE"),
                line_count=line_count,
                definitions_count=definitions_count,
                imports_count=imports_count,
                in_degree=in_deg,
                out_degree=out_deg,
                importance_score=round(score, 2),
                defined_classes=classes_def,
                defined_functions=funcs_def,
                imported_libraries=libs_imp,
                provenance=prov
            )
            results.append(insight)

        # Sort by importance score descending
        results.sort(key=lambda x: x.importance_score, reverse=True)
        return results

    def _extract_classes(self, nodes: List[Dict[str, Any]], edges: List[Dict[str, Any]]) -> List[ClassInsight]:
        """Extract classes along with their defined methods and line provenance."""
        class_nodes = [n for n in nodes if (n.get("entity_type") or n.get("label")) == "Class"]
        node_id_to_name = {n["id"]: n["name"] for n in nodes if "id" in n}

        # Find methods linked to classes via DEFINES edges
        class_methods: Dict[str, List[str]] = {}
        for e in edges:
            rel = e.get("relationship_type") or e.get("label")
            if rel == "DEFINES":
                src_name = node_id_to_name.get(e.get("source"))
                tgt_name = node_id_to_name.get(e.get("target"))
                if src_name and tgt_name:
                    class_methods.setdefault(src_name, []).append(tgt_name)

        classes: List[ClassInsight] = []
        for cn in class_nodes:
            props = cn.get("properties", {})
            name = cn.get("name", "")
            cid = cn.get("canonical_id") or props.get("canonical_id") or f"class:{name}"
            fp = cn.get("file_path") or props.get("file_path", "")
            sline = cn.get("start_line") or props.get("start_line", 1)
            eline = cn.get("end_line") or props.get("end_line", 1)
            line_str = f"L{sline}-L{eline}" if eline > sline else f"L{sline}"

            methods = sorted(list(set(class_methods.get(name, []))))

            classes.append(ClassInsight(
                name=name,
                canonical_id=cid,
                file_path=fp,
                line_range=line_str,
                commit_sha=props.get("commit_sha"),
                extraction_method=cn.get("extraction_method") or props.get("extraction_method"),
                methods=methods,
                description=props.get("description"),
                source_snippet=cn.get("source_snippet") or props.get("source_snippet")
            ))

        classes.sort(key=lambda x: (x.file_path, x.name))
        return classes

    def _extract_functions(self, nodes: List[Dict[str, Any]], classes: List[ClassInsight]) -> List[FunctionInsight]:
        """Extract standalone and top-level functions."""
        func_nodes = [n for n in nodes if (n.get("entity_type") or n.get("label")) in ("Function", "Method")]
        
        # Build map of class methods
        class_method_set: Set[Tuple[str, str]] = set()
        for c in classes:
            for m in c.methods:
                class_method_set.add((c.file_path, m))

        functions: List[FunctionInsight] = []
        for fn in func_nodes:
            props = fn.get("properties", {})
            name = fn.get("name", "")
            cid = fn.get("canonical_id") or props.get("canonical_id") or f"func:{name}"
            fp = fn.get("file_path") or props.get("file_path", "")
            sline = fn.get("start_line") or props.get("start_line", 1)
            eline = fn.get("end_line") or props.get("end_line", 1)
            line_str = f"L{sline}-L{eline}" if eline > sline else f"L{sline}"

            parent_class = None
            for c in classes:
                if c.file_path == fp and name in c.methods:
                    parent_class = c.name
                    break

            is_async = "async" in (props.get("description", "") or "").lower() or "async" in (fn.get("source_snippet", "") or "").lower()

            functions.append(FunctionInsight(
                name=name,
                canonical_id=cid,
                file_path=fp,
                line_range=line_str,
                is_async=is_async,
                parent_class=parent_class,
                commit_sha=props.get("commit_sha"),
                extraction_method=fn.get("extraction_method") or props.get("extraction_method"),
                description=props.get("description"),
                source_snippet=fn.get("source_snippet") or props.get("source_snippet")
            ))

        functions.sort(key=lambda x: (x.file_path, x.name))
        return functions

    def _extract_apis(self, nodes: List[Dict[str, Any]]) -> List[ApiInsight]:
        """Extract API endpoints, HTTP methods, and handler provenance."""
        api_nodes = [n for n in nodes if (n.get("entity_type") or n.get("label")) == "API"]
        apis: List[ApiInsight] = []

        for an in api_nodes:
            props = an.get("properties", {})
            endpoint = an.get("name") or props.get("endpoint") or props.get("name", "/")
            method = props.get("http_method") or props.get("method", "GET")
            handler = props.get("handler_name") or props.get("handler")
            fp = an.get("file_path") or props.get("file_path", "")
            sline = an.get("start_line") or props.get("start_line", 1)

            prov = ProvenanceInfo(
                file_path=fp,
                start_line=sline,
                end_line=an.get("end_line") or props.get("end_line", sline),
                commit_sha=props.get("commit_sha"),
                extraction_method=an.get("extraction_method") or props.get("extraction_method"),
                source_snippet=an.get("source_snippet") or props.get("source_snippet")
            )

            apis.append(ApiInsight(
                endpoint=endpoint,
                http_method=method.upper(),
                handler_name=handler,
                file_path=fp,
                line_number=sline,
                provenance=prov
            ))

        apis.sort(key=lambda x: (x.endpoint, x.http_method))
        return apis

    def _extract_dependencies(self, nodes: List[Dict[str, Any]], edges: List[Dict[str, Any]]) -> List[DependencyInsight]:
        """Extract dependency edges (IMPORTS, DEPENDS_ON, USES)."""
        node_id_map = {n["id"]: n for n in nodes if "id" in n}
        deps: List[DependencyInsight] = []

        for e in edges:
            rel = e.get("relationship_type") or e.get("label")
            if rel in ("IMPORTS", "DEPENDS_ON", "USES"):
                src_node = node_id_map.get(e.get("source"), {})
                tgt_node = node_id_map.get(e.get("target"), {})

                src_file = src_node.get("file_path") or src_node.get("name", "Unknown")
                tgt_name = tgt_node.get("name", "Unknown")
                tgt_type = tgt_node.get("entity_type") or tgt_node.get("label", "Unknown")
                props = e.get("properties", {})

                deps.append(DependencyInsight(
                    source_file=src_file,
                    relationship_type=rel,
                    target_entity=tgt_name,
                    target_type=tgt_type,
                    line_number=props.get("start_line") or e.get("start_line")
                ))

        deps.sort(key=lambda x: (x.source_file, x.relationship_type, x.target_entity))
        return deps

    def _extract_code_flows(self, nodes: List[Dict[str, Any]], edges: List[Dict[str, Any]]) -> List[CodeFlowItem]:
        """Trace deterministic call and usage chains."""
        node_id_map = {n["id"]: n for n in nodes if "id" in n}
        flows: List[CodeFlowItem] = []
        step = 1

        for e in edges:
            rel = e.get("relationship_type") or e.get("label")
            if rel in ("CALLS", "USES", "IMPLEMENTED_BY", "DEFINES"):
                src = node_id_map.get(e.get("source"), {})
                tgt = node_id_map.get(e.get("target"), {})
                props = e.get("properties", {})

                s_name = src.get("name", "Unknown")
                s_type = src.get("entity_type") or src.get("label", "Unknown")
                t_name = tgt.get("name", "Unknown")
                t_type = tgt.get("entity_type") or tgt.get("label", "Unknown")

                flows.append(CodeFlowItem(
                    step_number=step,
                    from_entity=s_name,
                    from_type=s_type,
                    to_entity=t_name,
                    to_type=t_type,
                    relationship_type=rel,
                    file_path=props.get("file_path") or src.get("file_path"),
                    description=props.get("description") or f"{s_type} '{s_name}' {rel.lower()} {t_type} '{t_name}'"
                ))
                step += 1

        return flows[:100]  # Cap to first 100 flow links

    # -------------------------------------------------------------------------
    # Summarization Generators
    # -------------------------------------------------------------------------

    def _generate_overview(self, repo_name: str, total_nodes: int, total_edges: int,
                           file_cnt: int, class_cnt: int, func_cnt: int,
                           technologies: List[TechStackItem], libraries: List[TechStackItem],
                           apis: List[ApiInsight]) -> str:
        tech_names = ", ".join([t.name for t in technologies[:5]]) or "Python / Modern Web"
        lib_names = ", ".join([l.name for l in libraries[:6]]) or "Standard Libraries"
        api_cnt = len(apis)

        return (
            f"Repository **{repo_name}** represents a modular software system modeled into an Apache AGE Knowledge Graph "
            f"containing **{total_nodes} vertices** and **{total_edges} directed relationships**.\n\n"
            f"- **Codebase Scope**: {file_cnt} analyzed files, {class_cnt} classes, and {func_cnt} function/method definitions.\n"
            f"- **Core Technologies**: {tech_names}.\n"
            f"- **Key Libraries**: {lib_names}.\n"
            f"- **API Surface**: {api_cnt} discovered HTTP endpoints/routes."
        )

    def _generate_architecture_summary(self, repo_name: str, important_files: List[FileInsight],
                                      classes: List[ClassInsight], apis: List[ApiInsight],
                                      services: List[str], technologies: List[TechStackItem]) -> str:
        top_files = [f.file_path for f in important_files[:4]]
        top_classes = [c.name for c in classes[:5]]
        top_apis = [f"{a.http_method} {a.endpoint}" for a in apis[:4]]

        parts = [
            f"### System Architecture for `{repo_name}`",
            "",
            "1. **Core Processing & Control Layer**:",
            f"   - Primary architectural hubs: {', '.join([f'`{p}`' for p in top_files]) if top_files else 'Modular source packages'}.",
            f"   - Key Domain Models / Controllers: {', '.join([f'`{c}`' for c in top_classes]) if top_classes else 'Procedural modules'}.",
            "",
            "2. **API & Interface Boundary**:",
            f"   - Exposes {len(apis)} API routes including: {', '.join([f'`{a}`' for a in top_apis]) if top_apis else 'Internal CLI/Library interface'}.",
            "",
            "3. **Services & Subsystems**:",
            f"   - Discovered services: {', '.join([f'`{s}`' for s in services]) if services else 'Single monolith / library'}.",
            "",
            "4. **Graph Topology**:",
            "   - Deterministic structural extraction maps explicit file-level containment (`CONTAINS`), symbol definitions (`DEFINES`), dependency imports (`IMPORTS`), and cross-component calls (`CALLS`)."
        ]
        return "\n".join(parts)

    def _generate_dependency_summary(self, libraries: List[TechStackItem], dependencies: List[DependencyInsight]) -> str:
        top_libs = [f"`{l.name}`" for l in libraries[:8]]
        total_imports = len([d for d in dependencies if d.relationship_type == "IMPORTS"])

        return (
            f"The project references **{len(libraries)} third-party and standard libraries** with **{total_imports} import linkages**.\n\n"
            f"Prominent libraries include: {', '.join(top_libs) if top_libs else 'Standard library dependencies'}."
        )

    # -------------------------------------------------------------------------
    # Interactive Q&A / Ask the Graph
    # -------------------------------------------------------------------------

    def ask_question(self, repo_name: str, question_id: str, param: Optional[str] = None) -> Dict[str, Any]:
        """
        Deterministic, graph-grounded query engine to answer natural architecture questions.
        """
        insights = self.get_repository_insights(repo_name)
        param_clean = (param or "").strip()

        if question_id == "tech_stack":
            techs = [t.model_dump() for t in insights.technologies]
            libs = [l.model_dump() for l in insights.libraries]
            return {
                "question": "What technologies and libraries does this repository use?",
                "answer": f"Repository `{repo_name}` uses {len(techs)} technologies and {len(libs)} external/standard libraries.",
                "technologies": techs,
                "libraries": libs,
                "source": "Apache AGE (Technology & Library vertices with IMPORTS/DEPENDS_ON edges)"
            }

        elif question_id == "important_files":
            files = [f.model_dump() for f in insights.important_files[:10]]
            return {
                "question": "What are the most important files and entrypoints?",
                "answer": f"Top ranked files based on graph degree centrality, definitions, and linkages.",
                "files": files,
                "source": "Apache AGE (File vertices ranked by graph degree and definitions)"
            }

        elif question_id == "classes_methods":
            classes = [c.model_dump() for c in insights.classes]
            return {
                "question": "What classes exist and what methods do they have?",
                "answer": f"Found {len(classes)} classes defined across the repository.",
                "classes": classes,
                "source": "Apache AGE (Class vertices and DEFINES edges)"
            }

        elif question_id == "apis":
            apis = [a.model_dump() for a in insights.apis]
            return {
                "question": "What APIs or endpoints are exposed?",
                "answer": f"Found {len(apis)} HTTP endpoints registered in the repository.",
                "apis": apis,
                "source": "Apache AGE (API vertices with line provenance)"
            }

        elif question_id == "entity_search":
            if not param_clean:
                return {"error": "Please provide an entity name or class/function identifier to search."}
            prov = self.git_service.get_entity_provenance(param_clean)
            return {
                "question": f"Where is '{param_clean}' defined and how is it used?",
                "result": prov,
                "source": f"Apache AGE (Exact vertex lookup for '{param_clean}')"
            }

        elif question_id == "file_details":
            if not param_clean:
                return {"error": "Please provide a file path to inspect."}
            matching_files = [f.model_dump() for f in insights.important_files if param_clean.lower() in f.file_path.lower()]
            return {
                "question": f"What does file '{param_clean}' import and define?",
                "files": matching_files,
                "source": f"Apache AGE (File vertex and connected DEFINES/IMPORTS edges)"
            }

        elif question_id == "code_flows":
            flows = [f.model_dump() for f in insights.code_flows[:30]]
            return {
                "question": "What are the primary code call and usage flows?",
                "answer": f"Traced {len(flows)} execution and usage links.",
                "flows": flows,
                "source": "Apache AGE (CALLS, USES, DEFINES directed edges)"
            }

        else:
            return {
                "question": f"General inquiry for `{repo_name}`",
                "answer": insights.overview,
                "architecture_summary": insights.architecture_summary,
                "statistics": insights.statistics.model_dump(),
                "source": "Apache AGE Graph Overview"
            }
