# -*- coding: utf-8 -*-

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class GatewayConfig(BaseModel):
    provider: str = "openai_compatible"
    model: str
    api_key: str
    base_url: str = ""
    timeout: float = 30.0
    max_retries: int = 2
    temperature: float = 0.0


class ToolDefinition(BaseModel):
    name: str
    description: str = ""
    parameters: Dict[str, Any] = Field(default_factory=dict)


class ToolCallback(BaseModel):
    url: str
    token: str
    context: Dict[str, Any] = Field(default_factory=dict)
    timeout: float = 30.0


class ChatMessage(BaseModel):
    role: str
    content: str


class AgentRunRequest(BaseModel):
    message: str
    system_prompt: str = ""
    config: GatewayConfig
    tools: List[ToolDefinition] = Field(default_factory=list)
    tool_callback: Optional[ToolCallback] = None
    messages: List[ChatMessage] = Field(default_factory=list)
    thread_id: str = ""

