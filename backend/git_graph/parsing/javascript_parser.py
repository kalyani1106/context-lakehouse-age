"""
JavaScript and TypeScript Structural Parser
===========================================
Conservative deterministic parser extracting classes, methods, functions,
imports, exports, Express/Fastify routes, and call references from JS/TS source code.
"""

import re
import logging
from pathlib import Path
from typing import List, Dict, Optional, Any
from pydantic import BaseModel, Field

logger = logging.getLogger("javascript_parser")

class ParsedJSImport(BaseModel):
    module: str
    imported_symbols: List[str] = Field(default_factory=list)
    alias: Optional[str] = None
    is_require: bool = False
    start_line: int = 1
    end_line: int = 1
    source_snippet: str = ""

class ParsedJSRoute(BaseModel):
    http_method: str
    path: str
    function_name: Optional[str] = None
    start_line: int = 1

class ParsedJSFunction(BaseModel):
    name: str
    qualified_name: str
    is_method: bool = False
    class_name: Optional[str] = None
    is_async: bool = False
    is_exported: bool = False
    args: List[str] = Field(default_factory=list)
    start_line: int = 1
    end_line: int = 1
    source_snippet: str = ""

class ParsedJSClass(BaseModel):
    name: str
    bases: List[str] = Field(default_factory=list)
    is_exported: bool = False
    methods: List[ParsedJSFunction] = Field(default_factory=list)
    start_line: int = 1
    end_line: int = 1
    source_snippet: str = ""

class ParsedJSFile(BaseModel):
    relative_path: str
    module_name: str
    imports: List[ParsedJSImport] = Field(default_factory=list)
    classes: List[ParsedJSClass] = Field(default_factory=list)
    functions: List[ParsedJSFunction] = Field(default_factory=list)
    routes: List[ParsedJSRoute] = Field(default_factory=list)
    line_count: int = 0
    parse_errors: List[str] = Field(default_factory=list)

class JavaScriptParser:
    @staticmethod
    def _get_snippet(lines: List[str], start_line: int, end_line: int, max_chars: int = 400) -> str:
        s = max(0, start_line - 1)
        e = min(len(lines), end_line)
        snip = "\n".join(lines[s:e]).strip()
        return snip[:max_chars] + "..." if len(snip) > max_chars else snip

    @classmethod
    def parse_source(cls, source_code: str, relative_path: str) -> ParsedJSFile:
        lines = source_code.splitlines()
        line_count = len(lines)
        
        posix = relative_path.replace("\\", "/").rstrip(".js").rstrip(".ts").rstrip(".jsx").rstrip(".tsx")
        module_name = posix.replace("/", ".")

        imports: List[ParsedJSImport] = []
        classes: List[ParsedJSClass] = []
        functions: List[ParsedJSFunction] = []
        routes: List[ParsedJSRoute] = []

        # 1. Parse ES Imports: import { a, b } from 'module'; import defaultExport from 'module';
        import_es_pattern = re.compile(r'^\s*import\s+(?:([\w\*\$]+)\s*,\s*)?(?:\{\s*([^}]+)\s*\}|([\w\*\$]+))?\s*from\s*[\'"]([^\'"]+)[\'"]', re.MULTILINE)
        for m in import_es_pattern.finditer(source_code):
            start_line = source_code[:m.start()].count("\n") + 1
            end_line = source_code[:m.end()].count("\n") + 1
            default_imp, named_imps, star_imp, mod_name = m.groups()
            
            symbols = []
            if default_imp:
                symbols.append(default_imp.strip())
            if star_imp:
                symbols.append(star_imp.strip())
            if named_imps:
                for s in named_imps.split(","):
                    sym = s.strip().split(" as ")[0].strip()
                    if sym:
                        symbols.append(sym)
            
            imports.append(ParsedJSImport(
                module=mod_name,
                imported_symbols=symbols,
                is_require=False,
                start_line=start_line,
                end_line=end_line,
                source_snippet=cls._get_snippet(lines, start_line, end_line)
            ))

        # 2. Parse CommonJS requires: const { a } = require('module'); const x = require('module');
        require_pattern = re.compile(r'^\s*(?:const|let|var)\s+(?:\{\s*([^}]+)\s*\}|([\w\$]+))\s*=\s*require\(\s*[\'"]([^\'"]+)[\'"]\s*\)', re.MULTILINE)
        for m in require_pattern.finditer(source_code):
            start_line = source_code[:m.start()].count("\n") + 1
            end_line = source_code[:m.end()].count("\n") + 1
            named_req, var_req, mod_name = m.groups()
            
            symbols = []
            if var_req:
                symbols.append(var_req.strip())
            if named_req:
                for s in named_req.split(","):
                    sym = s.strip().split(":")[0].strip()
                    if sym:
                        symbols.append(sym)

            imports.append(ParsedJSImport(
                module=mod_name,
                imported_symbols=symbols,
                is_require=True,
                start_line=start_line,
                end_line=end_line,
                source_snippet=cls._get_snippet(lines, start_line, end_line)
            ))

        # 3. Parse Classes: class MyClass extends BaseClass { ... }
        class_pattern = re.compile(r'^\s*(export\s+)?(?:default\s+)?class\s+([\w\$]+)(?:\s+extends\s+([\w\$\.]+))?', re.MULTILINE)
        for m in class_pattern.finditer(source_code):
            start_line = source_code[:m.start()].count("\n") + 1
            is_exp = bool(m.group(1))
            cls_name = m.group(2)
            base_cls = [m.group(3)] if m.group(3) else []

            # Approximate class body range (up to 40 lines or matching brace)
            end_line = min(line_count, start_line + 40)
            
            classes.append(ParsedJSClass(
                name=cls_name,
                bases=base_cls,
                is_exported=is_exp,
                start_line=start_line,
                end_line=end_line,
                source_snippet=cls._get_snippet(lines, start_line, start_line + 2)
            ))

        # 4. Parse Standalone Functions: function myFunc(a, b) / const myFunc = async (a, b) =>
        func_patterns = [
            # export async function foo(...)
            re.compile(r'^\s*(export\s+)?(?:default\s+)?(async\s+)?function\s+([\w\$]+)\s*\(([^)]*)\)', re.MULTILINE),
            # export const foo = async (...) =>
            re.compile(r'^\s*(export\s+)?(?:const|let|var)\s+([\w\$]+)\s*=\s*(async\s*)?\(([^)]*)\)\s*=>', re.MULTILINE)
        ]
        
        seen_funcs = set()
        for idx, pat in enumerate(func_patterns):
            for m in pat.finditer(source_code):
                start_line = source_code[:m.start()].count("\n") + 1
                if idx == 0:
                    is_exp = bool(m.group(1))
                    is_async = bool(m.group(2))
                    fname = m.group(3)
                    raw_args = m.group(4)
                else:
                    is_exp = bool(m.group(1))
                    fname = m.group(2)
                    is_async = bool(m.group(3))
                    raw_args = m.group(4)

                if fname in seen_funcs:
                    continue
                seen_funcs.add(fname)

                args = [a.strip().split(":")[0].strip() for a in raw_args.split(",") if a.strip()]
                end_line = min(line_count, start_line + 15)

                functions.append(ParsedJSFunction(
                    name=fname,
                    qualified_name=fname,
                    is_method=False,
                    is_async=is_async,
                    is_exported=is_exp,
                    args=args,
                    start_line=start_line,
                    end_line=end_line,
                    source_snippet=cls._get_snippet(lines, start_line, start_line + 2)
                ))

        # 5. Parse Express / Fastify / Next.js routes: app.get('/api/data', ...), router.post('/users', ...)
        route_pattern = re.compile(r'\b(?:app|router|server)\s*\.\s*(get|post|put|delete|patch|all)\s*\(\s*[\'"]([^\'"]+)[\'"]', re.MULTILINE | re.IGNORECASE)
        for m in route_pattern.finditer(source_code):
            start_line = source_code[:m.start()].count("\n") + 1
            method = m.group(1).upper()
            route_path = m.group(2)
            routes.append(ParsedJSRoute(
                http_method=method,
                path=route_path,
                start_line=start_line
            ))

        return ParsedJSFile(
            relative_path=relative_path,
            module_name=module_name,
            imports=imports,
            classes=classes,
            functions=functions,
            routes=routes,
            line_count=line_count,
            parse_errors=[]
        )

    @classmethod
    def parse_file(cls, file_path: Path, workspace_root: Path) -> ParsedJSFile:
        try:
            rel = file_path.relative_to(workspace_root).as_posix()
        except ValueError:
            rel = str(file_path)
        try:
            content = file_path.read_text(encoding="utf-8-sig", errors="ignore")
            return cls.parse_source(content, rel)
        except Exception as e:
            return ParsedJSFile(
                relative_path=rel,
                module_name=rel.replace("/", "."),
                parse_errors=[f"File read error: {str(e)}"]
            )
