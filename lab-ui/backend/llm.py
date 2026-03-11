"""LabOS LLM Service — gateway + fallback API calls."""

import json
import logging
import os

from config import ROOT_DIR

log = logging.getLogger("labos")


def _load_llm_env():
    """Load LLM config from .env file."""
    if os.environ.get("LLM_API_KEY"):
        return
    env_path = ROOT_DIR.parent / ".env"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())


def run_llm(messages, max_tokens: int = 4096) -> str:
    """Call LLM via gateway (preferred) or direct API (fallback)."""
    _load_llm_env()
    
    if isinstance(messages, str):
        messages = [{"role": "user", "content": messages}]

    # Try gateway first (OpenClaw → Claude)
    gateway_url = os.environ.get("GATEWAY_URL", "")
    gateway_token = os.environ.get("GATEWAY_TOKEN", "")
    gateway_model = os.environ.get("GATEWAY_MODEL", "")
    
    if gateway_url and gateway_token:
        try:
            from openai import OpenAI
            client = OpenAI(api_key=gateway_token, base_url=gateway_url)
            resp = client.chat.completions.create(
                model=gateway_model or "haiku",
                messages=messages,
                max_tokens=max_tokens,
                temperature=0.3,
            )
            result = (resp.choices[0].message.content or "").strip()
            if not result:
                log.warning("Gateway returned empty response")
                return "Hmm, I didn't have anything to say to that. Ask me something specific!"
            log.info(f"[LLM] Gateway OK: {result[:80]}...")
            return result
        except Exception as e:
            log.warning(f"[LLM] Gateway failed ({e}), falling back to direct API")

    # Fallback to direct API
    api_key = os.environ.get("LLM_API_KEY", "")
    if not api_key:
        return "⚠️ LLM not configured."

    try:
        from openai import OpenAI
        client = OpenAI(
            api_key=api_key,
            base_url=os.environ.get("LLM_API_BASE", "") or None,
        )
        resp = client.chat.completions.create(
            model=os.environ.get("LLM_MODEL", "deepseek-ai/DeepSeek-V3-0324"),
            messages=messages,
            max_tokens=max_tokens,
            temperature=0.3,
        )
        return (resp.choices[0].message.content or "").strip()
    except Exception as e:
        return f"⚠️ LLM error: {e}"
