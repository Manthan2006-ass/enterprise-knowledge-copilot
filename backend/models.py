from pydantic import BaseModel, EmailStr


class UserSignupSchema(BaseModel):
    email: EmailStr
    password: str


class CreateWorkspaceRequest(BaseModel):
    name: str
    is_public: bool = False  # True = visible/usable by ALL logged-in users, not just the creator


class UpdateWorkspaceRequest(BaseModel):
    name: str | None = None
    is_public: bool | None = None


class CreateThreadRequest(BaseModel):
    title: str
    workspace_id: str | None = None  # None = normal chat, no RAG


class CreateMessageRequest(BaseModel):
    thread_id: str
    content: str


class ChatPayloadSchema(BaseModel):
    thread_id: str
    workspace_id: str | None = None
    question: str
