# pipelines/ingestion/indexing/neo4j.py
from neo4j import GraphDatabase

class Neo4jIndexer:
    """Writes graph data using idempotent MERGE queries."""
    def __init__(self):
        self.driver = GraphDatabase.driver("bolt://192.168.214.21:7687", auth=("neo4j", "password"))
    
    def write(self, batch):
        with self.driver.session() as session:
            # Flattens batch and executes a single transaction for high performance
            session.execute_write(self._merge_graph_data, batch)
    
    def _merge_graph_data(self, tx, batch):
        """Merge nodes and edges into Neo4j graph database."""
        for item in batch:
            # Merge nodes
            for node in item.get("nodes", []):
                label = node["label"]
                node_id = node["id"]
                properties = node.get("properties", {})
                
                # Build property string for Cypher query
                props_str = ", ".join([f"n.{key} = ${key}" for key in properties.keys()])
                
                # MERGE node by id and set properties
                query = f"""
                MERGE (n:{label} {{id: $id}})
                SET {props_str if props_str else ''}
                """
                tx.run(query, id=node_id, **properties)
            
            # Merge edges
            for edge in item.get("edges", []):
                from_id = edge["from"]
                to_id = edge["to"]
                rel_type = edge["type"]
                properties = edge.get("properties", {})
                
                # Build property string for relationship
                props_str = ", ".join([f"r.{key} = ${key}" for key in properties.keys()])
                
                # MERGE relationship between nodes
                query = f"""
                MATCH (a {{id: $from_id}})
                MATCH (b {{id: $to_id}})
                MERGE (a)-[r:{rel_type}]->(b)
                {f'SET {props_str}' if props_str else ''}
                """
                tx.run(query, from_id=from_id, to_id=to_id, **properties)
    
    def close(self):
        """Close the Neo4j driver connection."""
        self.driver.close()

                
if __name__ == "__main__":
    indexer = Neo4jIndexer()
    try:
        sample_batch = [
            {
                "nodes": [
                    {"id": "1", "label": "Person", "properties": {"name": "Alice"}},
                    {"id": "2", "label": "Person", "properties": {"name": "Bob"}}
                ],
                "edges": [
                    {"from": "1", "to": "2", "type": "KNOWS", "properties": {"since": 2020}}
                ]
            }
        ]
        indexer.write(sample_batch)
        print("✓ Data successfully written to Neo4j")
    finally:
        indexer.close()