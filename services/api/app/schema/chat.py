from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, description="The user's query")
    session_id: str = Field(
        default=None, description="UUID for the conversation thread"
    )
