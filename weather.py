import json
import os
import requests
import yaml

from typing import Optional
from pydantic import BaseModel, Field

from dataclasses import dataclass
from dotenv import load_dotenv

from langchain.agents import create_agent
from langchain.chat_models import init_chat_model
from langchain.tools import tool, ToolRuntime
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import InMemorySaver

# 1. Load system environment variables and project configuration
load_dotenv()

with open("./config.yaml", "r") as f:
    config = yaml.safe_load(f)

provider = config["model_setting"]["provider"]

# 2. Initialize LLM based on configured provider
if provider == "gemini":
    model_name = config["providers"]["gemini"]["model_name"]
    llm = init_chat_model(
        model=model_name,
        model_provider="google_genai",
        temperature=0.1
    )
    print(f"☁️ Initialized Cloud Provider: Gemini ({model_name})")

elif provider == "ollama":
    selected_local = config["model_setting"]["local_model"]
    if selected_local not in config["providers"]["ollama"]["models"]:
        raise ValueError(f"Unknown local model option: '{selected_local}'")
    
    model_name = config["providers"]["ollama"]["models"][selected_local]
    llm = init_chat_model(
        model=model_name,
        model_provider="ollama",
        temperature=0.1
    )
    print(f"🤖 Initialized Local Provider: Ollama -> {selected_local.upper()} ({model_name})")

elif provider == "groq":
    model_name = config["providers"]["groq"]["model_name"]
    llm = init_chat_model(
        model=model_name,
        model_provider="groq",
        temperature=0.1
    )
    print(f"⚡ Initialized Groq Provider ({model_name})")

elif provider == "openai":
    model_name = config["providers"]["openai"]["model_name"]
    # Ensure no stray environment base URL redirects OpenAI to Perplexity
    llm = init_chat_model(
        model=model_name,
        model_provider="openai",
        temperature=0.1,
        base_url="https://api.openai.com/v1"
    )
    print(f"☁️ Initialized OpenAI Provider ({model_name})")

elif provider == "openrouter":
    model_name = config["providers"]["openrouter"]["model_name"]
    base_url = config["providers"]["openrouter"].get("base_url", "https://openrouter.ai/api/v1")
    api_key = os.getenv("OPENROUTER_API_KEY") or os.getenv("OPENAI_API_KEY")
    
    llm = ChatOpenAI(
        model=model_name,
        openai_api_key=api_key,
        openai_api_base=base_url,
        temperature=0.1,
        default_headers={
            "HTTP-Referer": "http://localhost:3000",
            "X-Title": "Agentic Autoscalar"
        }
    )
    print(f"☁️ Initialized OpenRouter Provider ({model_name})")

else:
    raise ValueError(f"Unknown provider '{provider}' set in config.yaml")


# 3. Schemas & Tools
@dataclass
class Context:
    user_id: str


@dataclass
class ResponseFormat(BaseModel):
    clarification_question: Optional[str] = Field(
        default=None, 
        description="Ask the user for missing details (e.g. city) if location is unknown"
    )
    summary: Optional[str] = Field(
        default=None, 
        description="Brief textual summary of the current weather condition"
    )
    temperature_celsius: Optional[float] = Field(default=None)
    temperature_fahrenheit: Optional[float] = Field(default=None)
    humidity: Optional[float] = Field(default=None)


@tool('get_weather', description='Return weather information for a given city', return_direct=False)
def get_weather(city: str):
    response = requests.get(f'https://wttr.in/{city}?format=j1').json()
    current = response['current_condition'][0]
    return {
        "city": city,
        "temperature_celsius": float(current['temp_C']),
        "temperature_fahrenheit": float(current['temp_F']),
        "humidity": float(current['humidity']),
        "description": current['weatherDesc'][0]['value']
    }


@tool('locate_user', description="Look up a user's city based on the context")
def locate_user(runtime: ToolRuntime[Context]):
    match runtime.context.user_id:
        case 'ABC123':
            return 'Vienna'
        case 'XYZ456':
            return 'London'
        case 'HJKL111':
            return 'Paris'
        case _:
            return 'Unknown'


# 4. Agent Initialization & Execution
checkpointer = InMemorySaver()

agent = create_agent(
    model=llm,
    tools=[get_weather, locate_user],
    system_prompt=(
        "You are a helpful weather assistant.\n"
        "1. You MUST call `locate_user` first if the user does not specify a city.\n"
        "2. If `locate_user` returns 'Unknown', you MUST ask the user which city they are in. DO NOT guess a location.\n"
        "3. Once you have a valid city name, you MUST call the `get_weather` tool. NEVER invent or guess weather statistics yourself."
    ),
    context_schema=Context,
    response_format=ResponseFormat,
    checkpointer=checkpointer
)

# Test Runs
total_input_tokens = 0
total_output_tokens = 0

test_cases = [
    # ('1', 'HJKL111', 'What is the weather like today?'),
    # ('1', 'ABC123', 'What is the weather like today?'),
    ('2', 'ABC124', 'What is the weather like today?'),
    ('2', 'ABC123', 'What is the weather like today?'),
    # ('3', 'XYZ456', 'How is the weather today?')
]

for thread_id, user_id, prompt in test_cases:
    config_thread = {'configurable': {'thread_id': thread_id}}
    response = agent.invoke(
        {'messages': [{'role': 'user', 'content': prompt}]},
        config=config_thread,
        context=Context(user_id=user_id)
    )
    
    for message in response['messages']:
        message.pretty_print()
        if hasattr(message, 'usage_metadata') and message.usage_metadata:
            total_input_tokens += message.usage_metadata.get('input_tokens', 0)
            total_output_tokens += message.usage_metadata.get('output_tokens', 0)
            
    print("#" * 35)

total_tokens = total_input_tokens + total_output_tokens
print(f"📊 Token Usage Breakdown:")
print(f"   Input Tokens:  {total_input_tokens}")
print(f"   Output Tokens: {total_output_tokens}")
print(f"   Total Tokens:  {total_tokens}")