"""
Apache AGE PostgreSQL Client
=============================
Handles connection management, graph initialization, Cypher query execution,
and agtype conversion against PostgreSQL with the Apache AGE extension.
"""

import logging
from typing import List, Dict, Any, Optional, Tuple
import psycopg2
from psycopg2.extras import RealDictCursor

from backend.config import settings
from backend.graph.agtype_parser import parse_agtype

logger = logging.getLogger("age_client")

class AGEClient:
    def __init__(
        self,
        host: Optional[str] = None,
        port: Optional[int] = None,
        dbname: Optional[str] = None,
        user: Optional[str] = None,
        password: Optional[str] = None,
        graph_name: Optional[str] = None
    ):
        self.host = host or settings.POSTGRES_HOST
        self.port = port or settings.POSTGRES_PORT
        self.dbname = dbname or settings.POSTGRES_DB
        self.user = user or settings.POSTGRES_USER
        self.password = password or settings.POSTGRES_PASSWORD
        self.graph_name = graph_name or settings.AGE_GRAPH_NAME

    def get_connection(self):
        conn = psycopg2.connect(
            host=self.host,
            port=self.port,
            dbname=self.dbname,
            user=self.user,
            password=self.password
        )
        conn.autocommit = False
        self._init_session(conn)
        return conn

    def _init_session(self, conn):
        """Load the AGE extension and set search_path on the connection."""
        with conn.cursor() as cur:
            cur.execute("CREATE EXTENSION IF NOT EXISTS age;")
            cur.execute("LOAD 'age';")
            cur.execute('SET search_path = ag_catalog, "$user", public;')
        conn.commit()

    def ensure_graph_exists(self, graph_name: Optional[str] = None) -> bool:
        """Check if graph exists, create it if not."""
        target_graph = graph_name or self.graph_name
        conn = self.get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT 1 FROM ag_catalog.ag_graph WHERE name = %s;", (target_graph,))
                row = cur.fetchone()
                if not row:
                    logger.info(f"Creating Apache AGE graph: {target_graph}")
                    cur.execute(f"SELECT create_graph('{target_graph}');")
                    conn.commit()
                    return True
                return False
        finally:
            conn.close()

    def execute_cypher(
        self,
        cypher_query: str,
        columns: Optional[List[str]] = None,
        graph_name: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Execute a Cypher query against Apache AGE.
        `cypher_query` is the Cypher snippet (e.g. MATCH (n) RETURN n).
        `columns` defines the alias names returned in the AS (...) clause.
        """
        target_graph = graph_name or self.graph_name
        
        # Format the SQL wrapper for Cypher
        # Default single column 'result' if columns not specified
        col_defs = ", ".join([f"{col} agtype" for col in (columns or ["result"])])
        
        # Use dynamic tag to avoid collisions with source code snippets
        import uuid
        tag = f"AGE_TAG_{uuid.uuid4().hex[:8]}"

        sql = f"""
        SELECT *
        FROM cypher('{target_graph}', ${tag}$
            {cypher_query}
        ${tag}$) AS ({col_defs});
        """
        
        conn = self.get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(sql)
                rows = cur.fetchall()
                col_names = [desc[0] for desc in cur.description]
                
                results = []
                for row in rows:
                    row_dict = {}
                    for col_idx, col_name in enumerate(col_names):
                        row_dict[col_name] = parse_agtype(row[col_idx])
                    results.append(row_dict)
                conn.commit()
                return results
        except Exception as e:
            conn.rollback()
            logger.error(f"Error executing Cypher query: {cypher_query} -> {e}")
            raise e
        finally:
            conn.close()

    def execute_cypher_mutate(
        self,
        cypher_query: str,
        graph_name: Optional[str] = None
    ) -> None:
        """Execute a mutating Cypher query (CREATE, MERGE, SET, DELETE) without expecting return rows."""
        target_graph = graph_name or self.graph_name
        import uuid
        tag = f"AGE_TAG_{uuid.uuid4().hex[:8]}"

        sql = f"""
        SELECT *
        FROM cypher('{target_graph}', ${tag}$
            {cypher_query}
        ${tag}$) AS (v agtype);
        """
        conn = self.get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(sql)
                conn.commit()
        except Exception as e:
            conn.rollback()
            logger.error(f"Error executing Cypher mutation: {cypher_query} -> {e}")
            raise e
        finally:
            conn.close()

    def test_connection(self) -> Dict[str, Any]:
        """Verify connectivity to PostgreSQL and Apache AGE."""
        conn = self.get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT version();")
                pg_ver = cur.fetchone()[0]
                cur.execute("SELECT name FROM ag_catalog.ag_graph;")
                graphs = [row[0] for row in cur.fetchall()]
            return {
                "status": "connected",
                "postgres_version": pg_ver,
                "available_graphs": graphs,
                "current_graph": self.graph_name,
                "host": self.host,
                "port": self.port
            }
        finally:
            conn.close()
