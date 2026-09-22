# -*- coding: utf-8 -*-

from langchain_openai import ChatOpenAI


def create_chat_model(config):
    """Create an OpenAI-compatible chat model from runtime config."""
    kwargs = {
        "model": config.model,
        "api_key": config.api_key,
        "temperature": config.temperature,
        "timeout": config.timeout or 30.0,
        "max_retries": config.max_retries,
    }
    if config.base_url:
        kwargs["base_url"] = config.base_url
    return ChatOpenAI(**kwargs)


def structured_output_method(config):
    """Pick structured-output strategy for the configured provider endpoint.

    OpenAI-compatible cloud APIs reliably follow tool/function calling.
    Local Ollama endpoints often advertise tools but return plain text instead of
    tool_calls; json_mode keeps the agent schema working for 7B/14B models.
    """
    base = (getattr(config, 'base_url', None) or '').strip().lower()
    if not base:
        return 'function_calling'
    local_markers = (
        '11434',
        'ollama',
        'host.docker.internal',
        'localhost',
        '127.0.0.1',
    )
    if any(marker in base for marker in local_markers):
        return 'json_mode'
    return 'function_calling'
