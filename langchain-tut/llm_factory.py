import json
import os
import yaml
from datetime import datetime, timezone
from dotenv import load_dotenv

from langchain_core.callbacks import BaseCallbackHandler
from langchain.chat_models import init_chat_model
from langchain_openai import ChatOpenAI


class TokenLoggerCallback(BaseCallbackHandler):
    """Callback handler to automatically track and append token usage to usage_log.jsonl."""
    def __init__(self, log_file="usage_log.jsonl"):
        self.log_file = log_file

    def on_llm_end(self, response, **kwargs):
        llm_output = response.llm_output or {}
        token_usage = llm_output.get("token_usage", {})

        # Fallback check across generations if token_usage is nested inside AIMessage metadata
        if not token_usage and response.generations:
            for gen in response.generations:
                for g in gen:
                    if hasattr(g, "message") and hasattr(g.message, "usage_metadata"):
                        meta = g.message.usage_metadata or {}
                        token_usage = {
                            "prompt_tokens": meta.get("input_tokens", 0),
                            "completion_tokens": meta.get("output_tokens", 0),
                            "total_tokens": meta.get("total_tokens", 0),
                        }
                        break

        input_tokens = token_usage.get("prompt_tokens", 0)
        output_tokens = token_usage.get("completion_tokens", 0)

        if input_tokens or output_tokens:
            log_entry = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "requests": 1,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "total_tokens": input_tokens + output_tokens,
            }
            with open(self.log_file, "a") as f:
                f.write(json.dumps(log_entry) + "\n")


def get_llm(config_path="./config.yaml", temperature=0.1, **kwargs):
    """Instantiate a pre-configured LLM provider based on config.yaml with auto-logging."""
    load_dotenv()

    with open(config_path, "r") as f:
        config = yaml.safe_load(f)

    provider = config["model_setting"]["provider"]
    logger_callback = TokenLoggerCallback()

    if provider == "gemini":
        model_name = config["providers"]["gemini"]["model_name"]
        llm = init_chat_model(
            model=model_name,
            model_provider="google_genai",
            temperature=temperature,
            callbacks=[logger_callback],
            **kwargs
        )
        print(f"☁️ Initialized Gemini Provider ({model_name})")
        return llm

    elif provider == "ollama":
        selected_local = config["model_setting"]["local_model"]
        if selected_local not in config["providers"]["ollama"]["models"]:
            raise ValueError(f"Unknown local model option: '{selected_local}'")

        model_name = config["providers"]["ollama"]["models"][selected_local]
        llm = init_chat_model(
            model=model_name,
            model_provider="ollama",
            temperature=temperature,
            callbacks=[logger_callback],
            **kwargs
        )
        print(f"🤖 Initialized Ollama Provider -> {selected_local.upper()} ({model_name})")
        return llm

    elif provider == "groq":
        model_name = config["providers"]["groq"]["model_name"]
        llm = init_chat_model(
            model=model_name,
            model_provider="groq",
            temperature=temperature,
            callbacks=[logger_callback],
            **kwargs
        )
        print(f"⚡ Initialized Groq Provider ({model_name})")
        return llm

    elif provider == "openai":
        model_name = config["providers"]["openai"]["model_name"]
        llm = init_chat_model(
            model=model_name,
            model_provider="openai",
            base_url="https://api.openai.com/v1",
            temperature=temperature,
            callbacks=[logger_callback],
            **kwargs
        )
        print(f"☁️ Initialized OpenAI Provider ({model_name})")
        return llm

    elif provider == "openrouter":
        model_name = config["providers"]["openrouter"]["model_name"]
        base_url = config["providers"]["openrouter"].get("base_url", "https://openrouter.ai/api/v1")
        api_key = os.getenv("OPENROUTER_API_KEY") or os.getenv("OPENAI_API_KEY")

        if not api_key:
            raise ValueError("Neither OPENROUTER_API_KEY nor OPENAI_API_KEY was found in environment.")

        llm = ChatOpenAI(
            model=model_name,
            openai_api_key=api_key,
            openai_api_base=base_url,
            temperature=temperature,
            default_headers={
                "HTTP-Referer": "http://localhost:3000",
                "X-Title": "Agentic Autoscalar"
            },
            callbacks=[logger_callback],
            **kwargs
        )
        print(f"☁️ Initialized OpenRouter Provider ({model_name})")
        return llm

    else:
        raise ValueError(f"Unknown provider '{provider}' configured in {config_path}")