import os
import logging
from typing import Optional
from dotenv import load_dotenv
from langchain_core.language_models.chat_models import BaseChatModel

load_dotenv()
logger = logging.getLogger(__name__)


def get_chat_model(
    provider: str = "openai",
    model_name: Optional[str] = None,
    temperature: float = 0.1
) -> Optional[BaseChatModel]:
    """
    Instantiates a LangChain ChatModel instance based on the specified provider.
    Returns None if the provider is set to 'mock' or if required API credentials are absent.
    """
    provider = provider.lower()

    if provider == "mock":
        logger.info("Using mock reasoning provider; LLM invocation will bypass to heuristic reasoning.")
        return None

    if provider == "openai":
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            logger.warning("OPENAI_API_KEY not found; falling back to heuristic engine.")
            return None
        from langchain_openai import ChatOpenAI
        base_url = os.getenv("OPENAI_API_BASE")
        return ChatOpenAI(
            model=model_name or "gpt-4o-mini",
            temperature=temperature,
            api_key=api_key,
            base_url=base_url
        )

    elif provider == "groq":
        api_key = os.getenv("GROQ_API_KEY")
        if not api_key:
            logger.warning("GROQ_API_KEY not found; falling back to heuristic engine.")
            return None
        try:
            from langchain_groq import ChatGroq
            return ChatGroq(
                model_name=model_name or "llama-3.3-70b-versatile",
                temperature=temperature,
                groq_api_key=api_key
            )
        except ImportError:
            logger.warning("langchain-groq not installed; falling back to heuristic engine.")
            return None

    elif provider == "gemini":
        api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        if not api_key:
            logger.warning("GEMINI_API_KEY not found; falling back to heuristic engine.")
            return None
        try:
            from langchain_google_genai import ChatGoogleGenerativeAI
            return ChatGoogleGenerativeAI(
                model=model_name or "gemini-1.5-flash",
                temperature=temperature,
                google_api_key=api_key
            )
        except ImportError:
            logger.warning("langchain-google-genai not installed; falling back to heuristic engine.")
            return None

    logger.warning("Unrecognized provider '%s'; using deterministic heuristic fallback.", provider)
    return None
