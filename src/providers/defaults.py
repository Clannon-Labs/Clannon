from __future__ import annotations

DEFAULT_MODELS = {
    "anthropic": {
        "orchestrator": "claude-4-5-sonnet-latest",
        "memory": "claude-4-5-haiku-latest",
        "code": "claude-4-5-sonnet-latest",
    },
    "openai": {
        "orchestrator": "gpt-4o",
        "memory": "gpt-4o-mini",
        "code": "gpt-4o",
    },
    "google": {
        "orchestrator": "gemini-3.1-pro",
        "memory": "gemini-3-flash",
        "code": "gemini-3.1-pro",
    },
    "xai": {
        "orchestrator": "grok-4-1-fast-non-reasoning",
        "memory": "grok-3-mini",
        "code": "grok-4-1-fast-non-reasoning",
    },
    "mistral": {
        "orchestrator": "mistral-large-latest",
        "memory": "mistral-small-latest",
        "code": "codestral-latest",
    },
    "cerebras": {
        "orchestrator": "llama3.3-70b",
        "memory": "llama3.1-8b",
        "code": "llama3.3-70b",
    },
    "cohere": {
        "orchestrator": "command-r-plus-08-2024",
        "memory": "command-r-08-2024",
        "code": "command-r-plus-08-2024",
    },
    "groq": {
        "orchestrator": "llama-3.3-70b-versatile",
        "memory": "llama-3.1-8b-instant",
        "code": "qwen-2.5-coder-32b",
    },
    "bedrock": {
        "orchestrator": "us.anthropic.claude-3-5-sonnet-20241022-v2:0",
        "memory": "amazon.nova-micro-v1:0",
        "code": "us.anthropic.claude-3-5-sonnet-20241022-v2:0",
    },
    "huggingface": {
        "orchestrator": "meta-llama/Llama-3.3-70B-Instruct",
        "memory": "meta-llama/Llama-3.1-8B-Instruct",
        "code": "Qwen/Qwen2.5-Coder-32B-Instruct",
    },
    "ollama": {
        "orchestrator": "llama3.3",
        "memory": "llama3.1:8b",
        "code": "qwen2.5-coder:32b",
    },
    "openrouter": {
        "orchestrator": "anthropic/claude-sonnet-4-5",
        "memory": "google/gemini-3-flash",
        "code": "anthropic/claude-sonnet-4-5",
    },
}
