"""
Unit Tests for Python AST Parser
=================================
"""

import unittest
from backend.git_graph.parsing.python_parser import PythonParser

SAMPLE_PYTHON_CODE = """\"\"\"
Sample Module Docstring
\"\"\"

import os
from pathlib import Path
from fastapi import APIRouter, HTTPException

router = APIRouter()

class BaseService:
    def base_method(self):
        pass

@router.prefix
class GraphService(BaseService):
    \"\"\"Service managing knowledge graph connections.\"\"\"
    def __init__(self, host: str = "localhost"):
        self.host = host

    @router.post("/repositories/analyze")
    async def analyze_repo(self, repo_url: str):
        \"\"\"Analyze a repository.\"\"\"
        self.base_method()
        return {"status": "ok"}

def standalone_helper(x: int) -> int:
    \"\"\"Helper calculation.\"\"\"
    return x * 2
"""

class TestPythonASTParser(unittest.TestCase):
    def test_ast_parsing_classes_and_methods(self):
        parsed = PythonParser.parse_source(SAMPLE_PYTHON_CODE, "services/graph_service.py")
        
        self.assertEqual(parsed.module_name, "services.graph_service")
        self.assertEqual(parsed.docstring, "Sample Module Docstring")
        self.assertEqual(len(parsed.classes), 2)

        # BaseService
        base_cls = parsed.classes[0]
        self.assertEqual(base_cls.name, "BaseService")
        self.assertEqual(len(base_cls.methods), 1)
        self.assertEqual(base_cls.methods[0].name, "base_method")

        # GraphService
        graph_cls = parsed.classes[1]
        self.assertEqual(graph_cls.name, "GraphService")
        self.assertEqual(graph_cls.bases, ["BaseService"])
        self.assertEqual(len(graph_cls.methods), 2)
        
        init_m = graph_cls.methods[0]
        self.assertEqual(init_m.name, "__init__")
        self.assertEqual(init_m.class_name, "GraphService")
        self.assertEqual(init_m.qualified_name, "GraphService.__init__")

        analyze_m = graph_cls.methods[1]
        self.assertEqual(analyze_m.name, "analyze_repo")
        self.assertTrue(analyze_m.is_async)
        self.assertEqual(analyze_m.start_line, 22)
        self.assertTrue(len(analyze_m.source_snippet) > 0)
        
        # Verify route detection
        self.assertEqual(len(parsed.routes), 1)
        self.assertEqual(parsed.routes[0].http_method, "POST")
        self.assertEqual(parsed.routes[0].path, "/repositories/analyze")

    def test_imports_extraction(self):
        parsed = PythonParser.parse_source(SAMPLE_PYTHON_CODE, "services/graph_service.py")
        self.assertEqual(len(parsed.imports), 3)

        imp_os = parsed.imports[0]
        self.assertEqual(imp_os.module, "os")
        self.assertFalse(imp_os.is_from_import)

        imp_path = parsed.imports[1]
        self.assertEqual(imp_path.module, "pathlib")
        self.assertIn("Path", imp_path.imported_symbols)

        imp_fastapi = parsed.imports[2]
        self.assertEqual(imp_fastapi.module, "fastapi")
        self.assertIn("APIRouter", imp_fastapi.imported_symbols)
        self.assertIn("HTTPException", imp_fastapi.imported_symbols)

    def test_functions_and_calls(self):
        parsed = PythonParser.parse_source(SAMPLE_PYTHON_CODE, "services/graph_service.py")
        self.assertEqual(len(parsed.functions), 1)
        
        fn = parsed.functions[0]
        self.assertEqual(fn.name, "standalone_helper")
        self.assertFalse(fn.is_method)
        self.assertIn("x", fn.args)

        # Check call graph inside analyze_repo
        graph_cls = parsed.classes[1]
        analyze_m = graph_cls.methods[1]
        self.assertTrue(any(c.called_name == "base_method" for c in analyze_m.calls))

    def test_graceful_syntax_error_handling(self):
        bad_code = "def broken_syntax(x\nreturn x"
        parsed = PythonParser.parse_source(bad_code, "bad.py")
        self.assertEqual(len(parsed.parse_errors), 1)
        self.assertIn("SyntaxError", parsed.parse_errors[0])

if __name__ == "__main__":
    unittest.main()
