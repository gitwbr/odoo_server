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

