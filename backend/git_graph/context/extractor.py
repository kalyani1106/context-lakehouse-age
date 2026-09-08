"""
Git Graph Multi-Source Semantic Extractor
=========================================
Orchestrates structural AST, configuration, and documentation parsers to extract
canonical entities, directed relationships, and line-level source provenance.
"""

import logging
from pathlib import Path
from typing import List, Dict, Set, Tuple, Optional

from backend.git_graph.repository.models import RepoSource, FileInfo, RepoInventory
from backend.git_graph.context.schemas import (
    GitProvenance, GitGraphEntity, GitGraphRelationship, GitRepoContext
)
from backend.git_graph.context.normalizer import EntityNormalizer
from backend.git_graph.parsing.python_parser import PythonParser
from backend.git_graph.parsing.javascript_parser import JavaScriptParser
from backend.git_graph.parsing.config_parser import ConfigParser
from backend.git_graph.parsing.markdown_parser import MarkdownParser

logger = logging.getLogger("git_extractor")

STANDARD_STDLIB_MODULES = {
    "os", "sys", "re", "json", "time", "datetime", "math", "random",
    "pathlib", "typing", "collections", "itertools", "functools",
    "subprocess", "shutil", "tempfile", "logging", "unittest", "ast",
    "io", "copy", "threading", "multiprocessing", "hashlib", "base64",
    "contextlib", "dataclasses", "enum", "abc", "traceback", "inspect"
}

class GitGraphExtractor:
    def __init__(self):
        self.normalizer = EntityNormalizer()

    def extract(self, workspace_path: Path, inventory: RepoInventory) -> GitRepoContext:
        """
        Execute full deterministic extraction across all inventory files.
        """
        workspace = Path(workspace_path).resolve()
        repo_src = inventory.repo_source
        repo_name = repo_src.repo_name
        repo_url = repo_src.repository_url
        branch = repo_src.branch or "main"
        commit_sha = inventory.commit_sha

        entities: List[GitGraphEntity] = []
        relationships: List[GitGraphRelationship] = []

        # Root provenance builder helper
        def make_prov(
            file_path: Optional[str] = None,
            start_line: Optional[int] = None,
            end_line: Optional[int] = None,
            snippet: Optional[str] = None,
            method: str = "STRUCTURAL_AST"
        ) -> GitProvenance:
            return GitProvenance(
                repository_url=repo_url,
                repository_name=repo_name,
                branch=branch,
                commit_sha=commit_sha,
                file_path=file_path,
                start_line=start_line,
                end_line=end_line,
                source_snippet=snippet,
                extraction_method=method
            )

        # 1. Root Repository Entity
        repo_cid = self.normalizer.repo_id(repo_name)
        entities.append(GitGraphEntity(
            canonical_id=repo_cid,
            name=repo_name,
            entity_type="Repository",
            description=f"Git repository {repo_name} ({branch})",
            properties={
                "url": repo_url,
                "repository_url": repo_url,
                "name": repo_name,
                "repository_name": repo_name,
                "branch": branch,
                "commit_sha": commit_sha,
                "total_files": inventory.total_files,
                "total_lines": inventory.total_lines,
                "languages": inventory.languages,
                "file_types": inventory.file_types
            },
            provenance=make_prov(method="REPOSITORY_METADATA"),
            confidence=1.0
        ))

        # Track directory canonical IDs to avoid re-creation
        created_dirs: Set[str] = set()
        file_cid_map: Dict[str, str] = {} # rel_path -> file_cid
        symbol_cid_map: Dict[str, str] = {} # unqualified symbol name -> cid

        # 2. Extract Directories & Files
        for f in inventory.files:
            rel_path = f.relative_path
            file_cid = self.normalizer.file_id(repo_name, rel_path)
            file_cid_map[rel_path] = file_cid

            full_file_path = workspace / rel_path

            # Create File Entity
            entities.append(GitGraphEntity(
                canonical_id=file_cid,
                name=f.filename,
                entity_type="File",
                description=f"{f.language or 'Source'} file ({f.line_count} lines)",
                properties={
                    "relative_path": rel_path,
                    "filename": f.filename,
                    "extension": f.extension,
                    "language": f.language,
                    "file_type": f.file_type,
                    "line_count": f.line_count,
                    "size_bytes": f.size_bytes,
                    "is_test_file": f.is_test_file
                },
                provenance=make_prov(file_path=rel_path, start_line=1, end_line=f.line_count or 1),
                confidence=1.0
            ))

            # Handle Parent Directories
            parts = Path(rel_path).parent.parts
            if not parts or parts == ('.',):
                # File is at repository root
                relationships.append(GitGraphRelationship(
                    source_canonical_id=repo_cid,
                    target_canonical_id=file_cid,
                    relationship_type="CONTAINS",
                    provenance=make_prov(file_path=rel_path, start_line=1, end_line=1)
                ))
            else:
                curr_dir = ""
                parent_dir_cid = repo_cid
                for part in parts:
                    curr_dir = f"{curr_dir}/{part}" if curr_dir else part
                    dir_cid = self.normalizer.dir_id(repo_name, curr_dir)
                    if dir_cid not in created_dirs:
                        created_dirs.add(dir_cid)
                        entities.append(GitGraphEntity(
                            canonical_id=dir_cid,
                            name=part,
                            entity_type="Directory",
                            properties={"directory_path": curr_dir},
                            provenance=make_prov(file_path=curr_dir, method="REPOSITORY_METADATA")
                        ))
                        relationships.append(GitGraphRelationship(
                            source_canonical_id=parent_dir_cid,
                            target_canonical_id=dir_cid,
                            relationship_type="CONTAINS",
                            provenance=make_prov(file_path=curr_dir, method="REPOSITORY_METADATA")
                        ))
                    parent_dir_cid = dir_cid

                # Link last directory to file
                relationships.append(GitGraphRelationship(
                    source_canonical_id=parent_dir_cid,
                    target_canonical_id=file_cid,
                    relationship_type="CONTAINS",
                    provenance=make_prov(file_path=rel_path, start_line=1, end_line=1)
                ))

            # 3. Language & File Specific Structural Parsing
            if f.language == "Python":
                self._extract_python_file(
                    full_file_path=full_file_path,
                    rel_path=rel_path,
                    file_cid=file_cid,
                    repo_name=repo_name,
                    repo_cid=repo_cid,
                    make_prov=make_prov,
                    entities=entities,
                    relationships=relationships,
                    symbol_cid_map=symbol_cid_map
                )

            elif f.language in {"JavaScript", "TypeScript"}:
                self._extract_js_file(
                    full_file_path=full_file_path,
                    rel_path=rel_path,
                    file_cid=file_cid,
                    repo_name=repo_name,
                    repo_cid=repo_cid,
                    make_prov=make_prov,
                    entities=entities,
                    relationships=relationships
                )

            elif f.language == "Requirements" or f.filename.startswith("requirements"):
                self._extract_requirements(
                    full_file_path=full_file_path,
                    rel_path=rel_path,
                    file_cid=file_cid,
                    repo_cid=repo_cid,
                    make_prov=make_prov,
                    entities=entities,
                    relationships=relationships
                )

            elif f.language == "PackageJSON" or f.filename == "package.json":
                self._extract_package_json(
                    full_file_path=full_file_path,
                    rel_path=rel_path,
                    file_cid=file_cid,
                    repo_cid=repo_cid,
                    make_prov=make_prov,
                    entities=entities,
                    relationships=relationships
                )

            elif f.language == "Dockerfile" or f.filename.lower().startswith("dockerfile"):
                self._extract_dockerfile(
                    full_file_path=full_file_path,
                    rel_path=rel_path,
                    file_cid=file_cid,
                    repo_cid=repo_cid,
                    make_prov=make_prov,
                    entities=entities,
                    relationships=relationships
                )

            elif f.language == "DockerCompose" or "docker-compose" in f.filename or "compose." in f.filename:
                self._extract_docker_compose(
                    full_file_path=full_file_path,
                    rel_path=rel_path,
                    file_cid=file_cid,
                    repo_name=repo_name,
                    repo_cid=repo_cid,
                    make_prov=make_prov,
                    entities=entities,
                    relationships=relationships
                )

            elif f.language == "Markdown" or f.filename.lower().startswith("readme"):
                self._extract_markdown(
                    full_file_path=full_file_path,
                    rel_path=rel_path,
                    file_cid=file_cid,
                    repo_cid=repo_cid,
                    make_prov=make_prov,
                    entities=entities,
                    relationships=relationships
                )

        # 4. Normalize, Deduplicate, and Return Context
        norm_entities, norm_relationships = self.normalizer.deduplicate_and_normalize(entities, relationships)

        return GitRepoContext(
            repository_name=repo_name,
            repository_url=repo_url,
            branch=branch,
            commit_sha=commit_sha,
            entities=norm_entities,
            relationships=norm_relationships,
            inventory_summary={
                "total_files": inventory.total_files,
                "total_lines": inventory.total_lines,
                "languages": inventory.languages,
                "file_types": inventory.file_types
            }
        )

    def _extract_python_file(self, full_file_path: Path, rel_path: str, file_cid: str, repo_name: str, repo_cid: str, make_prov, entities, relationships, symbol_cid_map):
        parsed = PythonParser.parse_file(full_file_path, full_file_path.parent)

        # Module Entity
        mod_cid = self.normalizer.module_id(repo_name, parsed.module_name)
        entities.append(GitGraphEntity(
            canonical_id=mod_cid,
            name=parsed.module_name,
            entity_type="Module",
            description=parsed.docstring,
            properties={"module_path": parsed.module_name},
            provenance=make_prov(file_path=rel_path, start_line=1, end_line=parsed.line_count, snippet=parsed.docstring),
            confidence=1.0
        ))
        relationships.append(GitGraphRelationship(
            source_canonical_id=file_cid,
            target_canonical_id=mod_cid,
            relationship_type="DEFINES",
            provenance=make_prov(file_path=rel_path, start_line=1, end_line=1)
        ))

        # Classes
        for cls in parsed.classes:
            cls_cid = self.normalizer.class_id(repo_name, rel_path, cls.name)
            symbol_cid_map[cls.name] = cls_cid

            entities.append(GitGraphEntity(
                canonical_id=cls_cid,
                name=cls.name,
                entity_type="Class",
                description=cls.docstring,
                properties={
                    "bases": cls.bases,
                    "decorators": cls.decorators,
                    "start_line": cls.start_line,
                    "end_line": cls.end_line
                },
                provenance=make_prov(file_path=rel_path, start_line=cls.start_line, end_line=cls.end_line, snippet=cls.source_snippet),
                confidence=1.0
            ))
            relationships.append(GitGraphRelationship(
                source_canonical_id=file_cid,
                target_canonical_id=cls_cid,
                relationship_type="DEFINES",
                provenance=make_prov(file_path=rel_path, start_line=cls.start_line, end_line=cls.start_line, snippet=cls.source_snippet)
            ))

            # Methods inside Class
            for m in cls.methods:
                method_cid = self.normalizer.method_id(repo_name, rel_path, cls.name, m.name)
                symbol_cid_map[m.qualified_name] = method_cid
                symbol_cid_map[m.name] = method_cid

                entities.append(GitGraphEntity(
                    canonical_id=method_cid,
                    name=m.name,
                    entity_type="Method",
                    description=m.docstring,
                    properties={
                        "class_name": cls.name,
                        "args": m.args,
                        "is_async": m.is_async,
                        "decorators": m.decorators,
                        "start_line": m.start_line,
                        "end_line": m.end_line
                    },
                    provenance=make_prov(file_path=rel_path, start_line=m.start_line, end_line=m.end_line, snippet=m.source_snippet),
                    confidence=1.0
                ))
                relationships.append(GitGraphRelationship(
                    source_canonical_id=cls_cid,
                    target_canonical_id=method_cid,
                    relationship_type="CONTAINS",
                    provenance=make_prov(file_path=rel_path, start_line=m.start_line, end_line=m.start_line, snippet=m.source_snippet)
                ))

        # Top-level standalone functions
        for fn in parsed.functions:
            fn_cid = self.normalizer.function_id(repo_name, rel_path, fn.name)
            symbol_cid_map[fn.name] = fn_cid

            entities.append(GitGraphEntity(
                canonical_id=fn_cid,
                name=fn.name,
                entity_type="Function",
                description=fn.docstring,
                properties={
                    "args": fn.args,
                    "is_async": fn.is_async,
                    "decorators": fn.decorators,
                    "start_line": fn.start_line,
                    "end_line": fn.end_line
                },
                provenance=make_prov(file_path=rel_path, start_line=fn.start_line, end_line=fn.end_line, snippet=fn.source_snippet),
                confidence=1.0
            ))
            relationships.append(GitGraphRelationship(
                source_canonical_id=file_cid,
                target_canonical_id=fn_cid,
                relationship_type="DEFINES",
                provenance=make_prov(file_path=rel_path, start_line=fn.start_line, end_line=fn.start_line, snippet=fn.source_snippet)
            ))

        # Imports -> Library or Module
        for imp in parsed.imports:
            root_mod = imp.module.split(".")[0] if imp.module else ""
            if not root_mod:
                continue

            if root_mod in STANDARD_STDLIB_MODULES:
                continue # Skip stdlib clutter

            lib_cid = self.normalizer.library_id(root_mod)
            entities.append(GitGraphEntity(
                canonical_id=lib_cid,
                name=root_mod,
                entity_type="Library",
                provenance=make_prov(file_path=rel_path, start_line=imp.start_line, end_line=imp.end_line, snippet=imp.source_snippet)
            ))
            relationships.append(GitGraphRelationship(
                source_canonical_id=file_cid,
                target_canonical_id=lib_cid,
                relationship_type="IMPORTS",
                provenance=make_prov(file_path=rel_path, start_line=imp.start_line, end_line=imp.end_line, snippet=imp.source_snippet)
            ))
            relationships.append(GitGraphRelationship(
                source_canonical_id=repo_cid,
                target_canonical_id=lib_cid,
                relationship_type="USES",
                provenance=make_prov(file_path=rel_path, start_line=imp.start_line, end_line=imp.end_line, snippet=imp.source_snippet)
            ))

        # API Routes
        for r in parsed.routes:
            api_cid = self.normalizer.api_id(repo_name, r.http_method, r.path)
            entities.append(GitGraphEntity(
                canonical_id=api_cid,
                name=f"{r.http_method} {r.path}",
                entity_type="API",
                properties={"http_method": r.http_method, "path": r.path},
                provenance=make_prov(file_path=rel_path, start_line=r.start_line, end_line=r.start_line)
            ))
            
            # Link API to implementing function
            fn_target_cid = symbol_cid_map.get(r.function_name) or symbol_cid_map.get(r.function_name.split(".")[-1])
            if fn_target_cid:
                relationships.append(GitGraphRelationship(
                    source_canonical_id=api_cid,
                    target_canonical_id=fn_target_cid,
                    relationship_type="IMPLEMENTED_BY",
                    provenance=make_prov(file_path=rel_path, start_line=r.start_line, end_line=r.start_line)
                ))

    def _extract_js_file(self, full_file_path: Path, rel_path: str, file_cid: str, repo_name: str, repo_cid: str, make_prov, entities, relationships):
        parsed = JavaScriptParser.parse_file(full_file_path, full_file_path.parent)

        for cls in parsed.classes:
            cls_cid = self.normalizer.class_id(repo_name, rel_path, cls.name)
            entities.append(GitGraphEntity(
                canonical_id=cls_cid,
                name=cls.name,
                entity_type="Class",
                properties={"bases": cls.bases, "is_exported": cls.is_exported},
                provenance=make_prov(file_path=rel_path, start_line=cls.start_line, end_line=cls.end_line, snippet=cls.source_snippet)
            ))
            relationships.append(GitGraphRelationship(
                source_canonical_id=file_cid,
                target_canonical_id=cls_cid,
                relationship_type="DEFINES",
                provenance=make_prov(file_path=rel_path, start_line=cls.start_line, end_line=cls.start_line)
            ))

        for fn in parsed.functions:
            fn_cid = self.normalizer.function_id(repo_name, rel_path, fn.name)
            entities.append(GitGraphEntity(
                canonical_id=fn_cid,
                name=fn.name,
                entity_type="Function",
                properties={"args": fn.args, "is_async": fn.is_async, "is_exported": fn.is_exported},
                provenance=make_prov(file_path=rel_path, start_line=fn.start_line, end_line=fn.end_line, snippet=fn.source_snippet)
            ))
            relationships.append(GitGraphRelationship(
                source_canonical_id=file_cid,
                target_canonical_id=fn_cid,
                relationship_type="DEFINES",
                provenance=make_prov(file_path=rel_path, start_line=fn.start_line, end_line=fn.start_line)
            ))

        for imp in parsed.imports:
            mod = imp.module.strip("./")
            if mod:
                lib_cid = self.normalizer.library_id(mod)
                entities.append(GitGraphEntity(
                    canonical_id=lib_cid,
                    name=mod,
                    entity_type="Library",
                    provenance=make_prov(file_path=rel_path, start_line=imp.start_line, end_line=imp.end_line, snippet=imp.source_snippet)
                ))
                relationships.append(GitGraphRelationship(
                    source_canonical_id=file_cid,
                    target_canonical_id=lib_cid,
                    relationship_type="IMPORTS",
                    provenance=make_prov(file_path=rel_path, start_line=imp.start_line, end_line=imp.end_line)
                ))

        for r in parsed.routes:
            api_cid = self.normalizer.api_id(repo_name, r.http_method, r.path)
            entities.append(GitGraphEntity(
                canonical_id=api_cid,
                name=f"{r.http_method} {r.path}",
                entity_type="API",
                properties={"http_method": r.http_method, "path": r.path},
                provenance=make_prov(file_path=rel_path, start_line=r.start_line, end_line=r.start_line)
            ))

    def _extract_requirements(self, full_file_path: Path, rel_path: str, file_cid: str, repo_cid: str, make_prov, entities, relationships):
        try:
            content = full_file_path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            return
        parsed = ConfigParser.parse_requirements(content, rel_path)

        for lib in parsed.libraries:
            lib_cid = self.normalizer.library_id(lib.canonical_name)
            entities.append(GitGraphEntity(
                canonical_id=lib_cid,
                name=lib.name,
                entity_type="Library",
                properties={"version_spec": lib.version_spec},
                provenance=make_prov(file_path=rel_path, start_line=lib.line_number, end_line=lib.line_number, snippet=lib.source_snippet, method="CONFIG_PARSER")
            ))
            relationships.append(GitGraphRelationship(
                source_canonical_id=file_cid,
                target_canonical_id=lib_cid,
                relationship_type="DEPENDS_ON",
                provenance=make_prov(file_path=rel_path, start_line=lib.line_number, end_line=lib.line_number, snippet=lib.source_snippet, method="CONFIG_PARSER")
            ))
            relationships.append(GitGraphRelationship(
                source_canonical_id=repo_cid,
                target_canonical_id=lib_cid,
                relationship_type="USES",
                provenance=make_prov(file_path=rel_path, start_line=lib.line_number, end_line=lib.line_number, snippet=lib.source_snippet, method="CONFIG_PARSER")
            ))

    def _extract_package_json(self, full_file_path: Path, rel_path: str, file_cid: str, repo_cid: str, make_prov, entities, relationships):
        try:
            content = full_file_path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            return
        parsed = ConfigParser.parse_package_json(content, rel_path)

        for lib in parsed.libraries:
            lib_cid = self.normalizer.library_id(lib.canonical_name)
            entities.append(GitGraphEntity(
                canonical_id=lib_cid,
                name=lib.name,
                entity_type="Library",
                properties={"version_spec": lib.version_spec, "is_dev": lib.is_dev},
                provenance=make_prov(file_path=rel_path, start_line=lib.line_number, end_line=lib.line_number, snippet=lib.source_snippet, method="CONFIG_PARSER")
            ))
            relationships.append(GitGraphRelationship(
                source_canonical_id=file_cid,
                target_canonical_id=lib_cid,
                relationship_type="DEPENDS_ON",
                provenance=make_prov(file_path=rel_path, start_line=lib.line_number, end_line=lib.line_number, snippet=lib.source_snippet, method="CONFIG_PARSER")
            ))
            relationships.append(GitGraphRelationship(
                source_canonical_id=repo_cid,
                target_canonical_id=lib_cid,
                relationship_type="USES",
                provenance=make_prov(file_path=rel_path, start_line=lib.line_number, end_line=lib.line_number, snippet=lib.source_snippet, method="CONFIG_PARSER")
            ))

        for tech in parsed.technologies:
            t_cid = self.normalizer.technology_id(tech)
            entities.append(GitGraphEntity(
                canonical_id=t_cid,
                name=tech,
                entity_type="Technology",
                provenance=make_prov(file_path=rel_path, method="CONFIG_PARSER")
            ))
            relationships.append(GitGraphRelationship(
                source_canonical_id=repo_cid,
                target_canonical_id=t_cid,
                relationship_type="USES",
                provenance=make_prov(file_path=rel_path, method="CONFIG_PARSER")
            ))

    def _extract_dockerfile(self, full_file_path: Path, rel_path: str, file_cid: str, repo_cid: str, make_prov, entities, relationships):
        try:
            content = full_file_path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            return
        parsed = ConfigParser.parse_dockerfile(content, rel_path)

        for tech in parsed.technologies:
            t_cid = self.normalizer.technology_id(tech)
            entities.append(GitGraphEntity(
                canonical_id=t_cid,
                name=tech,
                entity_type="Technology",
                provenance=make_prov(file_path=rel_path, method="CONFIG_PARSER")
            ))
            relationships.append(GitGraphRelationship(
                source_canonical_id=repo_cid,
                target_canonical_id=t_cid,
                relationship_type="USES",
                provenance=make_prov(file_path=rel_path, method="CONFIG_PARSER")
            ))

    def _extract_docker_compose(self, full_file_path: Path, rel_path: str, file_cid: str, repo_name: str, repo_cid: str, make_prov, entities, relationships):
        try:
            content = full_file_path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            return
        parsed = ConfigParser.parse_docker_compose(content, rel_path)

        for s in parsed.docker_services:
            s_cid = self.normalizer.service_id(repo_name, s.service_name)
            entities.append(GitGraphEntity(
                canonical_id=s_cid,
                name=s.service_name,
                entity_type="Service",
                properties={"image": s.image, "ports": s.ports, "technology": s.inferred_technology},
                provenance=make_prov(file_path=rel_path, start_line=s.line_number, end_line=s.line_number, snippet=s.source_snippet, method="CONFIG_PARSER")
            ))
            relationships.append(GitGraphRelationship(
                source_canonical_id=file_cid,
                target_canonical_id=s_cid,
                relationship_type="DEFINES",
                provenance=make_prov(file_path=rel_path, start_line=s.line_number, end_line=s.line_number, snippet=s.source_snippet, method="CONFIG_PARSER")
            ))

            if s.inferred_technology:
                t_cid = self.normalizer.technology_id(s.inferred_technology)
                entities.append(GitGraphEntity(
                    canonical_id=t_cid,
                    name=s.inferred_technology,
                    entity_type="Technology",
                    provenance=make_prov(file_path=rel_path, method="CONFIG_PARSER")
                ))
                relationships.append(GitGraphRelationship(
                    source_canonical_id=s_cid,
                    target_canonical_id=t_cid,
                    relationship_type="CONNECTS_TO" if "DB" in s.inferred_technology or "AGE" in s.inferred_technology or "Postgres" in s.inferred_technology else "USES",
                    provenance=make_prov(file_path=rel_path, method="CONFIG_PARSER")
                ))

        for tech in parsed.technologies:
            t_cid = self.normalizer.technology_id(tech)
            entities.append(GitGraphEntity(
                canonical_id=t_cid,
                name=tech,
                entity_type="Technology",
                provenance=make_prov(file_path=rel_path, method="CONFIG_PARSER")
            ))
            relationships.append(GitGraphRelationship(
                source_canonical_id=repo_cid,
                target_canonical_id=t_cid,
                relationship_type="USES",
                provenance=make_prov(file_path=rel_path, method="CONFIG_PARSER")
            ))

    def _extract_markdown(self, full_file_path: Path, rel_path: str, file_cid: str, repo_cid: str, make_prov, entities, relationships):
        try:
            content = full_file_path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            return
        parsed = MarkdownParser.parse_content(content, rel_path)

        # Connect README -> DESCRIBES -> Repository
        relationships.append(GitGraphRelationship(
            source_canonical_id=file_cid,
            target_canonical_id=repo_cid,
            relationship_type="DESCRIBES",
            description=parsed.summary,
            provenance=make_prov(file_path=rel_path, start_line=1, end_line=min(10, parsed.line_count), snippet=parsed.summary, method="DOCS_PARSER")
        ))

        for tech in parsed.technologies:
            t_cid = self.normalizer.technology_id(tech.canonical_name)
            entities.append(GitGraphEntity(
                canonical_id=t_cid,
                name=tech.canonical_name,
                entity_type="Technology",
                provenance=make_prov(file_path=rel_path, start_line=tech.start_line, end_line=tech.start_line, snippet=tech.source_snippet, method="DOCS_PARSER")
            ))
            relationships.append(GitGraphRelationship(
                source_canonical_id=repo_cid,
                target_canonical_id=t_cid,
                relationship_type="USES",
                provenance=make_prov(file_path=rel_path, start_line=tech.start_line, end_line=tech.start_line, snippet=tech.source_snippet, method="DOCS_PARSER")
            ))

        for concept in parsed.concepts:
            c_cid = self.normalizer.concept_id(concept.name)
            entities.append(GitGraphEntity(
                canonical_id=c_cid,
                name=concept.name,
                entity_type="Concept",
                description=concept.concept_type,
                provenance=make_prov(file_path=rel_path, start_line=concept.start_line, end_line=concept.start_line, snippet=concept.source_snippet, method="DOCS_PARSER")
            ))
            relationships.append(GitGraphRelationship(
                source_canonical_id=file_cid,
                target_canonical_id=c_cid,
                relationship_type="DESCRIBES",
                provenance=make_prov(file_path=rel_path, start_line=concept.start_line, end_line=concept.start_line, snippet=concept.source_snippet, method="DOCS_PARSER")
            ))
