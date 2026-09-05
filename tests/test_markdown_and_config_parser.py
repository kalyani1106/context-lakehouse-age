"""
Unit Tests for Markdown and Configuration Parsers
================================================
"""

import unittest
from backend.git_graph.parsing.javascript_parser import JavaScriptParser
from backend.git_graph.parsing.config_parser import ConfigParser
from backend.git_graph.parsing.markdown_parser import MarkdownParser

SAMPLE_JS_CODE = """
import express from 'express';
import { AGEClient, formatQuery } from './age_client';

const app = express();

export class Visualizer {
    constructor() {
        this.client = new AGEClient();
    }
}

export async function fetchGraph(repoId) {
    return { id: repoId };
}

app.get('/api/v1/graph', (req, res) => {
    res.json({ status: "ok" });
});
"""

SAMPLE_REQUIREMENTS = """
# Production dependencies
fastapi>=0.110.0
psycopg2-binary>=2.9.9
networkx==3.2.0
"""

SAMPLE_DOCKER_COMPOSE = """
version: '3.8'
services:
  age-postgres:
    image: apache/age:latest
    ports:
      - "5455:5432"
    environment:
      POSTGRES_USER: postgres
      POSTGRES_DB: postgres
  api:
    build: .
    ports:
      - "8000:8000"
    depends_on:
      - age-postgres
"""

SAMPLE_README = """
# Context Lakehouse & Knowledge Graph

An end-to-end framework combining Data Lakehouse architecture with Apache AGE and PostgreSQL.

## Features
- Knowledge Graph extraction
- Deterministic AST Parser for code analysis
- FastAPI backend and Streamlit UI with Vis.js visualizer
"""

class TestParsers(unittest.TestCase):
    def test_javascript_parser(self):
        parsed = JavaScriptParser.parse_source(SAMPLE_JS_CODE, "src/visualizer.js")
        self.assertEqual(len(parsed.imports), 2)
        self.assertEqual(len(parsed.classes), 1)
        self.assertEqual(parsed.classes[0].name, "Visualizer")
        self.assertEqual(len(parsed.functions), 1)
        self.assertEqual(parsed.functions[0].name, "fetchGraph")
        self.assertEqual(len(parsed.routes), 1)
        self.assertEqual(parsed.routes[0].http_method, "GET")
        self.assertEqual(parsed.routes[0].path, "/api/v1/graph")

    def test_config_parser_requirements(self):
        parsed = ConfigParser.parse_requirements(SAMPLE_REQUIREMENTS, "requirements.txt")
        self.assertEqual(len(parsed.libraries), 3)
        lib_names = [lib.canonical_name for lib in parsed.libraries]
        self.assertIn("fastapi", lib_names)
        self.assertIn("psycopg2", lib_names) # normalized from psycopg2-binary
        self.assertIn("networkx", lib_names)

    def test_config_parser_docker_compose(self):
        parsed = ConfigParser.parse_docker_compose(SAMPLE_DOCKER_COMPOSE, "docker-compose.yml")
        self.assertEqual(len(parsed.docker_services), 2)
        s_names = [s.service_name for s in parsed.docker_services]
        self.assertIn("age-postgres", s_names)
        self.assertIn("api", s_names)
        
        age_service = next(s for s in parsed.docker_services if s.service_name == "age-postgres")
        self.assertEqual(age_service.inferred_technology, "Apache AGE")

    def test_markdown_parser(self):
        parsed = MarkdownParser.parse_content(SAMPLE_README, "README.md")
        self.assertEqual(parsed.title, "Context Lakehouse & Knowledge Graph")
        self.assertTrue(len(parsed.summary) > 0)
        
        tech_names = [t.canonical_name for t in parsed.technologies]
        self.assertIn("Apache AGE", tech_names)
        self.assertIn("PostgreSQL", tech_names)
        self.assertIn("FastAPI", tech_names)
        self.assertIn("Streamlit", tech_names)
        self.assertIn("Vis.js", tech_names)

        concept_names = [c.name for c in parsed.concepts]
        self.assertIn("Knowledge Graph", concept_names)
        self.assertIn("Context Lakehouse", concept_names)
        self.assertIn("AST Code Parsing", concept_names)

if __name__ == "__main__":
    unittest.main()
