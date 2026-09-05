"""
Configuration and Infrastructure Parsers
========================================
Extracts dependencies, libraries, Docker services, databases, and environment settings
from requirements.txt, package.json, Dockerfile, and docker-compose configurations.
"""

import re
import json
import logging
from pathlib import Path
from typing import List, Dict, Optional, Any
from pydantic import BaseModel, Field

logger = logging.getLogger("config_parser")

class ParsedLibrary(BaseModel):
    name: str # e.g. "fastapi", "psycopg2-binary"
    canonical_name: str # e.g. "fastapi", "psycopg2"
    version_spec: Optional[str] = None # e.g. ">=0.110.0"
    is_dev: bool = False
    source_file: str
    line_number: int = 1
    source_snippet: str = ""

class ParsedDockerService(BaseModel):
    service_name: str # e.g. "age-postgres", "api", "web"
    image: Optional[str] = None # e.g. "apache/age:latest", "postgres:15"
    ports: List[str] = Field(default_factory=list) # e.g. ["5455:5432"]
    environment_vars: Dict[str, str] = Field(default_factory=dict)
    depends_on: List[str] = Field(default_factory=list)
    inferred_technology: Optional[str] = None # e.g. "PostgreSQL", "Apache AGE", "Redis"
    source_file: str
    line_number: int = 1
    source_snippet: str = ""

class ParsedConfigFile(BaseModel):
    relative_path: str
    config_type: str # REQUIREMENTS, PACKAGE_JSON, DOCKERFILE, DOCKER_COMPOSE, PYPROJECT_TOML, ENV
    libraries: List[ParsedLibrary] = Field(default_factory=list)
    docker_services: List[ParsedDockerService] = Field(default_factory=list)
    technologies: List[str] = Field(default_factory=list)
    parse_errors: List[str] = Field(default_factory=list)

class ConfigParser:
    @staticmethod
    def _clean_snippet(text: str, max_chars: int = 400) -> str:
        s = text.strip()
        return s[:max_chars] + "..." if len(s) > max_chars else s

    @classmethod
    def parse_requirements(cls, content: str, relative_path: str) -> ParsedConfigFile:
        """Parse Python requirements.txt."""
        libraries: List[ParsedLibrary] = []
        technologies: List[str] = ["Python"]

        for idx, line in enumerate(content.splitlines(), start=1):
            raw = line.strip()
            if not raw or raw.startswith("#") or raw.startswith("-r") or raw.startswith("-e"):
                continue

            # Parse package name and version specifier
            match = re.match(r'^([a-zA-Z0-9_\-\.]+)(.*)$', raw)
            if match:
                pkg_name = match.group(1).strip()
                ver_spec = match.group(2).strip() or None
                
                # Normalize canonical name
                canon = pkg_name.lower().replace("_", "-")
                if canon.endswith("-binary"):
                    canon = canon[:-7]

                libraries.append(ParsedLibrary(
                    name=pkg_name,
                    canonical_name=canon,
                    version_spec=ver_spec,
                    source_file=relative_path,
                    line_number=idx,
                    source_snippet=raw
                ))

        return ParsedConfigFile(
            relative_path=relative_path,
            config_type="REQUIREMENTS",
            libraries=libraries,
            technologies=technologies
        )

    @classmethod
    def parse_package_json(cls, content: str, relative_path: str) -> ParsedConfigFile:
        """Parse Node.js package.json."""
        libraries: List[ParsedLibrary] = []
        technologies: List[str] = ["Node.js", "JavaScript"]

        try:
            data = json.loads(content)
        except Exception as e:
            return ParsedConfigFile(
                relative_path=relative_path,
                config_type="PACKAGE_JSON",
                parse_errors=[f"Invalid JSON: {str(e)}"]
            )

        deps = data.get("dependencies", {})
        dev_deps = data.get("devDependencies", {})

        for name, ver in deps.items():
            libraries.append(ParsedLibrary(
                name=name,
                canonical_name=name.lower(),
                version_spec=str(ver),
                is_dev=False,
                source_file=relative_path,
                line_number=1,
                source_snippet=f'"{name}": "{ver}"'
            ))

        for name, ver in dev_deps.items():
            libraries.append(ParsedLibrary(
                name=name,
                canonical_name=name.lower(),
                version_spec=str(ver),
                is_dev=True,
                source_file=relative_path,
                line_number=1,
                source_snippet=f'"{name}": "{ver}"'
            ))

        if "typescript" in deps or "typescript" in dev_deps:
            technologies.append("TypeScript")
        if "react" in deps:
            technologies.append("React")
        if "next" in deps:
            technologies.append("Next.js")
        if "express" in deps:
            technologies.append("Express")

        return ParsedConfigFile(
            relative_path=relative_path,
            config_type="PACKAGE_JSON",
            libraries=libraries,
            technologies=technologies
        )

    @classmethod
    def parse_dockerfile(cls, content: str, relative_path: str) -> ParsedConfigFile:
        """Parse Dockerfile base images and ports."""
        technologies: List[str] = ["Docker"]
        services: List[ParsedDockerService] = []

        from_matches = re.findall(r'^\s*FROM\s+([^\s]+)', content, re.MULTILINE | re.IGNORECASE)
        expose_matches = re.findall(r'^\s*EXPOSE\s+([^\s]+)', content, re.MULTILINE | re.IGNORECASE)

        for img in from_matches:
            tech = "Container"
            if "python" in img.lower():
                tech = "Python"
            elif "node" in img.lower():
                tech = "Node.js"
            elif "postgres" in img.lower():
                tech = "PostgreSQL"
            elif "age" in img.lower():
                tech = "Apache AGE"
            elif "golang" in img.lower():
                tech = "Go"
            
            technologies.append(tech)
            services.append(ParsedDockerService(
                service_name="docker-container",
                image=img,
                ports=expose_matches,
                inferred_technology=tech,
                source_file=relative_path,
                line_number=1,
                source_snippet=f"FROM {img}"
            ))

        return ParsedConfigFile(
            relative_path=relative_path,
            config_type="DOCKERFILE",
            docker_services=services,
            technologies=list(set(technologies))
        )

    @classmethod
    def parse_docker_compose(cls, content: str, relative_path: str) -> ParsedConfigFile:
        """Parse docker-compose.yml / .yaml services."""
        services: List[ParsedDockerService] = []
        technologies: List[str] = ["Docker", "Docker Compose"]

        try:
            import yaml
            data = yaml.safe_load(content)
        except Exception:
            # Fallback simple line-based regex parser if PyYAML is unavailable or malformed
            data = None

        if isinstance(data, dict) and "services" in data and isinstance(data["services"], dict):
            for sname, sconfig in data["services"].items():
                if not isinstance(sconfig, dict):
                    continue
                image = str(sconfig.get("image", ""))
                ports = [str(p) for p in sconfig.get("ports", [])]
                env_dict = sconfig.get("environment", {})
                if isinstance(env_dict, list):
                    env_dict = {item.split("=")[0]: item.split("=")[1] for item in env_dict if "=" in item}
                elif not isinstance(env_dict, dict):
                    env_dict = {}

                dep_on = sconfig.get("depends_on", [])
                if isinstance(dep_on, dict):
                    dep_on = list(dep_on.keys())
                elif not isinstance(dep_on, list):
                    dep_on = []

                inferred_tech = "Service"
                img_lower = image.lower()
                sname_lower = sname.lower()
                if "age" in img_lower or "age" in sname_lower:
                    inferred_tech = "Apache AGE"
                    technologies.append("Apache AGE")
                    technologies.append("PostgreSQL")
                elif "postgres" in img_lower or "postgres" in sname_lower:
                    inferred_tech = "PostgreSQL"
                    technologies.append("PostgreSQL")
                elif "redis" in img_lower:
                    inferred_tech = "Redis"
                    technologies.append("Redis")
                elif "mongo" in img_lower:
                    inferred_tech = "MongoDB"
                    technologies.append("MongoDB")

                services.append(ParsedDockerService(
                    service_name=sname,
                    image=image or None,
                    ports=ports,
                    environment_vars=env_dict,
                    depends_on=dep_on,
                    inferred_technology=inferred_tech,
                    source_file=relative_path,
                    line_number=1,
                    source_snippet=f"service: {sname} (image: {image})"
                ))
        else:
            # Fallback parser for compose lines
            for match in re.finditer(r'^\s*([a-zA-Z0-9_\-]+):\s*$', content, re.MULTILINE):
                sname = match.group(1).strip()
                if sname not in {"services", "version", "volumes", "networks"}:
                    services.append(ParsedDockerService(
                        service_name=sname,
                        source_file=relative_path,
                        line_number=content[:match.start()].count("\n") + 1,
                        source_snippet=f"service: {sname}"
                    ))

        return ParsedConfigFile(
            relative_path=relative_path,
            config_type="DOCKER_COMPOSE",
            docker_services=services,
            technologies=list(set(technologies))
        )
