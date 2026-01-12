# pipelines/ingestion/graph/schema_graph.py
from typing import Literal

# Restrict the LLM to only these entities/relationships
VALID_NODE_LABELS = Literal["Person", "Organization", "Location", "Concept", "Product"]

VALID_RELATION_TYPES = Literal["WORKS_FOR", "LOCATED_IN", "RELATES_TO", "PART_OF"]

class GraphSchema:
    @staticmethod
    def get_system_prompt() -> str:
        return f"Extract nodes/edges. Allowed Labels: {VALID_NODE_LABELS.__args__}..."
    
    
if __name__ == "__main__":
    # Example usage
    prompt = GraphSchema.get_system_prompt()
    print(prompt)
