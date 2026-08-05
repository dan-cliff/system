"""
Monkey-patches Odoo Enterprise's AI module to add Anthropic Claude support.

This module is loaded AFTER the enterprise 'ai' module, so all imports resolve
to already-existing class objects that we can safely extend in place.

Provider flow:
  ai.agent.llm_model  →  _get_llm_model_selection() iterates PROVIDERS
  ai.agent._get_provider()  →  get_provider(env, llm_model)  →  PROVIDERS
  LLMApiService(provider='anthropic')  →  routes to _request_llm_anthropic
"""

import json
import logging
import os

from odoo.addons.ai.utils import llm_providers as _llm_providers
from odoo.addons.ai.utils.llm_providers import Provider
from odoo.addons.ai.utils.llm_api_service import LLMApiService
from odoo.addons.ai.utils.ai_logging import api_call_logging

_logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# 1. Register Anthropic in the PROVIDERS list
#    PROVIDERS is a plain Python list, so append() works at import time.
#    EMBEDDING_MODELS_SELECTION was already computed when 'ai' loaded, so our
#    empty embedding_model ("") never appears in that selection — which is
#    correct, since Anthropic has no native embedding model.
# ─────────────────────────────────────────────────────────────────────────────

_ANTHROPIC_PROVIDER = Provider(
    name="anthropic",
    display_name="Anthropic",
    embedding_model="",   # Anthropic has no native embedding model
    embedding_config={},
    llms=[
        ("claude-opus-4-5", "Claude Opus 4.5"),
        ("claude-sonnet-4-5", "Claude Sonnet 4.5"),
        ("claude-3-7-sonnet-20250219", "Claude 3.7 Sonnet"),
        ("claude-3-5-sonnet-20241022", "Claude 3.5 Sonnet"),
        ("claude-3-5-haiku-20241022", "Claude 3.5 Haiku"),
    ],
    deprecated_models=[],
)

if not any(p.name == "anthropic" for p in _llm_providers.PROVIDERS):
    _llm_providers.PROVIDERS.append(_ANTHROPIC_PROVIDER)


# ─────────────────────────────────────────────────────────────────────────────
# 2. Patch LLMApiService.__init__ to handle provider='anthropic'
# ─────────────────────────────────────────────────────────────────────────────

_orig_init = LLMApiService.__init__


def _patched_init(self, env, provider='openai'):
    if provider == 'anthropic':
        self.provider = provider
        self.base_url = "https://api.anthropic.com/v1"
        self.env = env
    else:
        _orig_init(self, env, provider)


LLMApiService.__init__ = _patched_init


# ─────────────────────────────────────────────────────────────────────────────
# 3. Patch _get_api_token to resolve the Anthropic key
# ─────────────────────────────────────────────────────────────────────────────

_orig_get_api_token = LLMApiService._get_api_token


def _patched_get_api_token(self):
    if self.provider != 'anthropic':
        return _orig_get_api_token(self)

    key = (
        self.env["ir.config_parameter"].sudo().get_param("ai.anthropic_key")
        or os.getenv("ODOO_AI_ANTHROPIC_TOKEN", "")
    )
    if not key:
        from odoo.exceptions import UserError
        from odoo import _
        raise UserError(
            _("No Anthropic API key is configured. "
              "Please add your key in Settings → Technical → AI Settings.")
        )
    return key


LLMApiService._get_api_token = _patched_get_api_token


# ─────────────────────────────────────────────────────────────────────────────
# 4. Helpers: Anthropic-specific headers and message building
# ─────────────────────────────────────────────────────────────────────────────

def _get_anthropic_headers(self):
    """Return HTTP headers required by the Anthropic Messages API."""
    return {
        "x-api-key": self._get_api_token(),
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }


LLMApiService._get_anthropic_headers = _get_anthropic_headers


def _build_anthropic_messages(self, inputs, user_prompts, files):
    """Convert mixed-format inputs into a clean Anthropic messages list.

    The initial ``inputs`` arrive in an OpenAI-like format
    ``{"role": "user"|"assistant", "content": str}``.
    After the first tool-call round-trip, ``inputs`` already contain
    Anthropic-format messages (``"content"`` is a list of blocks).
    We detect and handle both forms transparently.
    """
    messages = []

    # --- user_prompts go first (matches OpenAI behaviour) ---
    if user_prompts or files:
        user_content = [{"type": "text", "text": p} for p in (user_prompts or []) if p]
        for f in (files or []):
            mt = f.get("mimetype", "")
            val = f.get("value", "")
            if mt.startswith("image/"):
                user_content.append({
                    "type": "image",
                    "source": {"type": "base64", "media_type": mt, "data": val},
                })
            elif mt == "application/pdf":
                user_content.append({
                    "type": "document",
                    "source": {"type": "base64", "media_type": "application/pdf", "data": val},
                })
            elif mt == "text/plain":
                user_content.append({"type": "text", "text": val})
        if user_content:
            messages.append({"role": "user", "content": user_content})

    # --- conversation history / tool-call continuation ---
    for inp in (inputs or []):
        content = inp.get("content")
        role = inp.get("role", "user")
        if role == "model":
            role = "assistant"

        if isinstance(content, str):
            # OpenAI-style plain-text message → convert
            messages.append({"role": role, "content": [{"type": "text", "text": content}]})
        elif isinstance(content, list):
            # Already in Anthropic block format (assistant tool_use, tool_result, etc.)
            messages.append({"role": role, "content": content})
        else:
            _logger.debug("ai_anthropic: skipping unrecognised input format: %s", inp)

    # --- merge consecutive tool_result user messages into one ---
    # Anthropic requires all tool results for a single turn to share one
    # user message.  The base _request_llm_silent loop appends them
    # individually via _build_tool_call_response, so we coalesce here.
    messages = self._merge_consecutive_tool_results(messages)

    return messages


LLMApiService._build_anthropic_messages = _build_anthropic_messages


def _merge_consecutive_tool_results(self, messages):
    """Merge back-to-back user messages that only contain tool_result blocks."""
    result = []
    i = 0
    while i < len(messages):
        msg = messages[i]
        is_tool_result_msg = (
            msg.get("role") == "user"
            and isinstance(msg.get("content"), list)
            and msg["content"]
            and all(c.get("type") == "tool_result" for c in msg["content"])
        )
        if is_tool_result_msg:
            combined = list(msg["content"])
            j = i + 1
            while j < len(messages):
                nxt = messages[j]
                if (
                    nxt.get("role") == "user"
                    and isinstance(nxt.get("content"), list)
                    and nxt["content"]
                    and all(c.get("type") == "tool_result" for c in nxt["content"])
                ):
                    combined.extend(nxt["content"])
                    j += 1
                else:
                    break
            result.append({"role": "user", "content": combined})
            i = j
        else:
            result.append(msg)
            i += 1
    return result


LLMApiService._merge_consecutive_tool_results = _merge_consecutive_tool_results


# ─────────────────────────────────────────────────────────────────────────────
# 5. The main Anthropic request method (analogous to _request_llm_openai /
#    _request_llm_google)
# ─────────────────────────────────────────────────────────────────────────────

def _request_llm_anthropic(
    self, llm_model, system_prompts, user_prompts, tools=None,
    files=None, schema=None, temperature=0.2, inputs=(), web_grounding=False,
):
    """Send a request to the Anthropic Messages API.

    Structured output (``schema``) is implemented by injecting a forced tool
    called ``structured_output`` and setting ``tool_choice`` to it.
    Regular tools and schema are mutually exclusive here; schema takes
    precedence if both are supplied.
    """
    # Build the ordered messages list
    messages = self._build_anthropic_messages(inputs, user_prompts, files)

    # System prompt: join all system messages into one string
    system_str = "\n\n".join(p for p in (system_prompts or []) if p)

    body = {
        "model": llm_model,
        "max_tokens": 8192,
        "messages": messages,
    }

    if system_str:
        body["system"] = system_str

    if temperature is not None:
        # Anthropic clamps temperature to [0, 1]
        body["temperature"] = max(0.0, min(1.0, float(temperature)))

    # Build tools list
    if schema:
        # Force the model to return a structured JSON object via a dedicated tool
        body["tools"] = [{
            "name": "structured_output",
            "description": "Return the result in the required structured format.",
            "input_schema": schema,
        }]
        body["tool_choice"] = {"type": "tool", "name": "structured_output"}
    elif tools:
        body["tools"] = [
            {
                "name": tool_name,
                "description": tool_description,
                "input_schema": tool_parameter_schema,
            }
            for tool_name, (tool_description, __, __, tool_parameter_schema) in tools.items()
        ]

    with api_call_logging(messages, tools) as record_response:
        response, to_call, next_inputs, token_usage = self._request_llm_anthropic_helper(
            body, tools, messages, schema
        )
        if record_response:
            record_response(to_call, response, token_usage)
        return response, to_call, next_inputs


LLMApiService._request_llm_anthropic = _request_llm_anthropic


def _request_llm_anthropic_helper(self, body, tools=None, messages=(), schema=None):
    """Process the raw Anthropic API response.

    Returns the same ``(response, to_call, next_inputs, token_usage)`` tuple
    expected by ``_request_llm_silent``.
    """
    llm_response = self._request(
        method="post",
        endpoint="/messages",
        headers=self._get_anthropic_headers(),
        body=body,
    )

    content_blocks = llm_response.get("content") or []
    response = []
    to_call = []

    # next_inputs = everything we sent + the assistant's reply (for the next turn)
    next_inputs = list(messages)
    next_inputs.append({"role": "assistant", "content": content_blocks})

    has_tool_use = any(b.get("type") == "tool_use" for b in content_blocks)

    for block in content_blocks:
        btype = block.get("type")

        if btype == "text":
            # Only include text when there are no tool calls in this response
            # (mirrors OpenAI behaviour — text alongside tool_use is skipped)
            if not has_tool_use:
                text = block.get("text", "")
                if text:
                    response.append(text)

        elif btype == "tool_use":
            name = block.get("name", "")
            call_id = block.get("id", "")
            arguments = block.get("input", {})

            if schema and name == "structured_output":
                # Structured output: serialise the result as a JSON string
                # and treat it as a regular text response
                response.append(json.dumps(arguments))
            else:
                to_call.append((name, call_id, arguments))

    # Token accounting
    token_usage = {}
    if usage := llm_response.get("usage"):
        token_usage["input_tokens"] = usage.get("input_tokens", 0)
        token_usage["cached_tokens"] = usage.get("cache_read_input_tokens", 0)
        token_usage["output_tokens"] = usage.get("output_tokens", 0)

    return response, to_call, next_inputs, token_usage


LLMApiService._request_llm_anthropic_helper = _request_llm_anthropic_helper


# ─────────────────────────────────────────────────────────────────────────────
# 6. Patch _request_llm to route Anthropic models through our new method
# ─────────────────────────────────────────────────────────────────────────────

_orig_request_llm = LLMApiService._request_llm


def _patched_request_llm(self, *args, **kwargs):
    # Honour the original deprecation check
    model = kwargs.get("llm_model") or (args[0] if args else None)
    from odoo.addons.ai.utils.llm_providers import check_model_depreciation
    check_model_depreciation(self.env, model)

    if self.provider == 'anthropic':
        return self._request_llm_anthropic(*args, **kwargs)

    return _orig_request_llm(self, *args, **kwargs)


LLMApiService._request_llm = _patched_request_llm


# ─────────────────────────────────────────────────────────────────────────────
# 7. Patch _build_tool_call_response for Anthropic format
#
#    Anthropic expects tool results as:
#       {"role": "user", "content": [{"type": "tool_result", "tool_use_id": …}]}
#    Each call produces ONE such message; _merge_consecutive_tool_results
#    coalesces multiple into a single user message before the next API call.
# ─────────────────────────────────────────────────────────────────────────────

_orig_build_tool_call_response = LLMApiService._build_tool_call_response


def _patched_build_tool_call_response(self, tool_call_id, return_value):
    if self.provider == "anthropic":
        return {
            "role": "user",
            "content": [{
                "type": "tool_result",
                "tool_use_id": tool_call_id,
                "content": str(return_value),
            }],
        }
    return _orig_build_tool_call_response(self, tool_call_id, return_value)


LLMApiService._build_tool_call_response = _patched_build_tool_call_response
