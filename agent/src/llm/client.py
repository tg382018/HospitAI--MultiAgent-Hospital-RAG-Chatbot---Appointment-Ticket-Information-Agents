"""Shared LLM client factory for the chat workflow."""

from __future__ import annotations

from functools import lru_cache

from langchain_openai import ChatOpenAI

from llm.profile import LLMProfile, get_llm_profile


@lru_cache
def _cached_llm(
    model: str,
    api_key: str,
    temperature: float,
    base_url: str | None,
) -> ChatOpenAI:
    kwargs: dict = {
        "model": model,
        "api_key": api_key,
        "temperature": temperature,
    }
    if base_url:
        kwargs["base_url"] = base_url
    return ChatOpenAI(**kwargs)


def get_llm(
    profile: LLMProfile | None = None,
    *,
    temperature: float | None = None,
) -> ChatOpenAI:
    """Return a ChatOpenAI instance for the active LLM profile.

    Pass ``temperature`` to override the profile (e.g. 0.1 for intent classification).
    """
    p = profile or get_llm_profile()
    api_key = p.llm_api_key or p.embedding_api_key or "no-key-provided"
    temp = p.llm_temperature if temperature is None else temperature
    return _cached_llm(p.llm_model, api_key, temp, p.llm_base_url)


def clear_llm_cache() -> None:
    _cached_llm.cache_clear()
