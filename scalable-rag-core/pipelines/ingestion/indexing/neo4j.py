# pipelines/ingestion/indexing/neo4j.py
from neo4j import GraphDatabase

class Neo4jIndexer:
    """Writes graph data using idempotent MERGE queries."""
    def __init__(self):
        self.driver = GraphDatabase.driver("bolt://neo4j-cluster:7687", auth=("neo4j", "pass"))
    def write(self, batch):
        with self.driver.session() as session:
            # Flattens batch and executes a single transaction for high performance
            session.execute_write(self._merge_graph_data, batch)