"""
Python AST Structural Parser
============================
Deterministic structural code parser using Python standard library `ast`.
Extracts modules, classes, methods, standalone functions, imports, decorators,
FastAPI/Flask API routes, docstrings, call invocations, and line-level source snippets.
"""

import ast
import logging
from pathlib import Path
from typing import List, Dict, Optional, Any, Set, Tuple
from pydantic import BaseModel, Field

logger = logging.getLogger("python_parser")

class ParsedImport(BaseModel):
    module: str
    imported_symbols: List[str] = Field(default_factory=list) # e.g. ["GraphService", "AGEClient"]
    alias: Optional[str] = None
    is_from_import: bool = False
    level: int = 0 # 0 for absolute, >0 for relative
    start_line: int = 1
    end_line: int = 1
    source_snippet: str = ""

class ParsedRoute(BaseModel):
    http_method: str # GET, POST, PUT, DELETE, PATCH, etc.
    path: str # e.g. "/repositories/analyze"
    function_name: str
    start_line: int = 1

class ParsedCall(BaseModel):
    caller_name: str # e.g. "ingest_context" or "Class.method"
    called_name: str # e.g. "execute_cypher" or "sanitize_label"
    full_call_expr: str # e.g. "self.age_client.execute_cypher"
    line_number: int = 1

class ParsedFunction(BaseModel):
    name: str
    qualified_name: str # e.g. "GraphService.ingest_context" or "upload_document"
    is_method: bool = False
    class_name: Optional[str] = None
    is_async: bool = False
    decorators: List[str] = Field(default_factory=list)
    docstring: Optional[str] = None
    args: List[str] = Field(default_factory=list)
    start_line: int = 1
    end_line: int = 1
    source_snippet: str = ""
    calls: List[ParsedCall] = Field(default_factory=list)
    routes: List[ParsedRoute] = Field(default_factory=list)

class ParsedClass(BaseModel):
    name: str
    bases: List[str] = Field(default_factory=list)
    decorators: List[str] = Field(default_factory=list)
    docstring: Optional[str] = None
    methods: List[ParsedFunction] = Field(default_factory=list)
    start_line: int = 1
    end_line: int = 1
    source_snippet: str = ""

class ParsedPythonFile(BaseModel):
    relative_path: str
    module_name: str
    docstring: Optional[str] = None
    imports: List[ParsedImport] = Field(default_factory=list)
    classes: List[ParsedClass] = Field(default_factory=list)
    functions: List[ParsedFunction] = Field(default_factory=list) # top-level functions
    routes: List[ParsedRoute] = Field(default_factory=list)
    all_calls: List[ParsedCall] = Field(default_factory=list)
    line_count: int = 0
    parse_errors: List[str] = Field(default_factory=list)

class PythonASTVisitor(ast.NodeVisitor):
    def __init__(self, source_code: str, relative_path: str):
        self.source_code = source_code
        self.lines = source_code.splitlines()
        self.relative_path = relative_path
        
        # Determine logical module name from relative path
        posix = relative_path.replace("\\", "/").rstrip(".py")
        if posix.endswith("/__init__"):
            posix = posix[:-9]
        self.module_name = posix.replace("/", ".")
        
        self.imports: List[ParsedImport] = []
        self.classes: List[ParsedClass] = []
        self.top_level_functions: List[ParsedFunction] = []
        self.routes: List[ParsedRoute] = []
        self.all_calls: List[ParsedCall] = []
        self.module_docstring: Optional[str] = None
        
        self.current_class: Optional[str] = None
        self.current_function: Optional[str] = None

    def _get_snippet(self, start_line: int, end_line: int, max_chars: int = 400) -> str:
        """Extract exact source snippet from 1-indexed line numbers."""
        if not self.lines:
            return ""
        s = max(0, start_line - 1)
        e = min(len(self.lines), end_line)
        snippet = "\n".join(self.lines[s:e]).strip()
        if len(snippet) > max_chars:
            return snippet[:max_chars] + "..."
        return snippet

    def _parse_decorator(self, node: ast.AST) -> str:
        """Convert AST decorator node to string representation."""
        try:
            return ast.unparse(node).strip()
        except Exception:
            if isinstance(node, ast.Name):
                return node.id
            elif isinstance(node, ast.Attribute):
                return f"{self._parse_decorator(node.value)}.{node.attr}"
            elif isinstance(node, ast.Call):
                return self._parse_decorator(node.func)
            return "decorator"

    def _extract_routes(self, decorators: List[str], func_name: str, start_line: int) -> List[ParsedRoute]:
        """Extract HTTP routes from decorators like @app.get('/path') or @router.post('/path')."""
        routes = []
        http_methods = {"get", "post", "put", "delete", "patch", "options", "head", "api_route"}
        
        for dec in decorators:
            # Matches @app.get("/..."), @router.post("..."), @bp.route("...")
            for method in http_methods:
                if f".{method}(" in dec or dec.startswith(f"{method}("):
                    # Extract path inside quotes
                    import re
                    match = re.search(r'[\'"]([^\'"]+)[\'"]', dec)
                    path = match.group(1) if match else "/"
                    routes.append(ParsedRoute(
                        http_method=method.upper(),
                        path=path,
                        function_name=func_name,
                        start_line=start_line
                    ))
        return routes

    def visit_Module(self, node: ast.Module):
        self.module_docstring = ast.get_docstring(node)
        self.generic_visit(node)

    def visit_Import(self, node: ast.Import):
        start = getattr(node, "lineno", 1)
        end = getattr(node, "end_lineno", start)
        snippet = self._get_snippet(start, end)
        for alias in node.names:
            self.imports.append(ParsedImport(
                module=alias.name,
                alias=alias.asname,
                is_from_import=False,
                start_line=start,
                end_line=end,
                source_snippet=snippet
            ))

    def visit_ImportFrom(self, node: ast.ImportFrom):
        start = getattr(node, "lineno", 1)
        end = getattr(node, "end_lineno", start)
        snippet = self._get_snippet(start, end)
        mod = node.module or ""
        symbols = [alias.name for alias in node.names]
        self.imports.append(ParsedImport(
            module=mod,
            imported_symbols=symbols,
            is_from_import=True,
            level=node.level,
            start_line=start,
            end_line=end,
            source_snippet=snippet
        ))

    def visit_ClassDef(self, node: ast.ClassDef):
        start = getattr(node, "lineno", 1)
        end = getattr(node, "end_lineno", start)
        snippet = self._get_snippet(start, end)
        
        bases = []
        for b in node.bases:
            try:
                bases.append(ast.unparse(b))
            except Exception:
                if isinstance(b, ast.Name):
                    bases.append(b.id)

        decorators = [self._parse_decorator(d) for d in node.decorator_list]
        docstring = ast.get_docstring(node)

        prev_class = self.current_class
        self.current_class = node.name

        methods = []
        for item in node.body:
            if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                fn = self._parse_function(item, is_method=True, class_name=node.name)
                methods.append(fn)

        parsed_cls = ParsedClass(
            name=node.name,
            bases=bases,
            decorators=decorators,
            docstring=docstring,
            methods=methods,
            start_line=start,
            end_line=end,
            source_snippet=snippet
        )
        self.classes.append(parsed_cls)
        self.current_class = prev_class

    def visit_FunctionDef(self, node: ast.FunctionDef):
        # If top-level function (not inside a class)
        if self.current_class is None:
            fn = self._parse_function(node, is_method=False)
            self.top_level_functions.append(fn)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef):
        if self.current_class is None:
            fn = self._parse_function(node, is_method=False)
            self.top_level_functions.append(fn)

    def _parse_function(self, node: ast.AST, is_method: bool = False, class_name: Optional[str] = None) -> ParsedFunction:
        start = getattr(node, "lineno", 1)
        end = getattr(node, "end_lineno", start)
        snippet = self._get_snippet(start, end)
        name = getattr(node, "name", "anonymous")
        qname = f"{class_name}.{name}" if class_name else name
        is_async = isinstance(node, ast.AsyncFunctionDef)
        
        decorators = [self._parse_decorator(d) for d in getattr(node, "decorator_list", [])]
        docstring = ast.get_docstring(node)
        
        args = []
        if hasattr(node, "args") and hasattr(node.args, "args"):
            args = [a.arg for a in node.args.args if a.arg not in {"self", "cls"}]

        # Extract function calls inside function body
        calls: List[ParsedCall] = []
        for sub_node in ast.walk(node):
            if isinstance(sub_node, ast.Call):
                call_info = self._parse_call(sub_node, qname)
                if call_info:
                    calls.append(call_info)
                    self.all_calls.append(call_info)

        routes = self._extract_routes(decorators, qname, start)
        self.routes.extend(routes)

        return ParsedFunction(
            name=name,
            qualified_name=qname,
            is_method=is_method,
            class_name=class_name,
            is_async=is_async,
            decorators=decorators,
            docstring=docstring,
            args=args,
            start_line=start,
            end_line=end,
            source_snippet=snippet,
            calls=calls,
            routes=routes
        )

    def _parse_call(self, node: ast.Call, caller_qname: str) -> Optional[ParsedCall]:
        line = getattr(node, "lineno", 1)
        full_expr = ""
        called_name = ""
        try:
            full_expr = ast.unparse(node.func)
        except Exception:
            full_expr = ""

        if isinstance(node.func, ast.Name):
            called_name = node.func.id
        elif isinstance(node.func, ast.Attribute):
            called_name = node.func.attr
        
        if called_name and called_name not in {"print", "len", "range", "str", "int", "dict", "list", "set"}:
            return ParsedCall(
                caller_name=caller_qname,
                called_name=called_name,
                full_call_expr=full_expr or called_name,
                line_number=line
            )
        return None

class PythonParser:
    @staticmethod
    def parse_source(source_code: str, relative_path: str) -> ParsedPythonFile:
        """Parse Python source code using AST."""
        lines = source_code.splitlines()
        line_count = len(lines)
        
        try:
            tree = ast.parse(source_code, filename=relative_path)
            visitor = PythonASTVisitor(source_code, relative_path)
            visitor.visit(tree)

            return ParsedPythonFile(
                relative_path=relative_path,
                module_name=visitor.module_name,
                docstring=visitor.module_docstring,
                imports=visitor.imports,
                classes=visitor.classes,
                functions=visitor.top_level_functions,
                routes=visitor.routes,
                all_calls=visitor.all_calls,
                line_count=line_count,
                parse_errors=[]
            )
        except SyntaxError as e:
            logger.warning(f"AST SyntaxError in {relative_path}:{e.lineno}: {e.msg}")
            return ParsedPythonFile(
                relative_path=relative_path,
                module_name=relative_path.replace("\\", "/").rstrip(".py").replace("/", "."),
                line_count=line_count,
                parse_errors=[f"SyntaxError at line {e.lineno}: {e.msg}"]
            )
        except Exception as e:
            logger.error(f"AST parsing error in {relative_path}: {e}")
            return ParsedPythonFile(
                relative_path=relative_path,
                module_name=relative_path.replace("\\", "/").rstrip(".py").replace("/", "."),
                line_count=line_count,
                parse_errors=[f"AST Error: {str(e)}"]
            )

    @classmethod
    def parse_file(cls, file_path: Path, workspace_root: Path) -> ParsedPythonFile:
        """Read and parse a Python file from disk."""
        try:
            rel = file_path.relative_to(workspace_root).as_posix()
        except ValueError:
            rel = str(file_path)
        
        try:
            content = file_path.read_text(encoding="utf-8-sig", errors="ignore")
            return cls.parse_source(content, rel)
        except Exception as e:
            return ParsedPythonFile(
                relative_path=rel,
                module_name=rel.replace("/", "."),
                parse_errors=[f"File read error: {str(e)}"]
            )
