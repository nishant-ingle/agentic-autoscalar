import json
import requests
import time
import yaml

from dataclasses import dataclass
from dotenv import load_dotenv

from langchain.agents import create_agent
from langchain.chat_models import init_chat_model
from langchain.tools import tool, ToolRuntime
from langgraph.checkpoint.memory import InMemorySaver


# 1. Load system environments and project configuration
load_dotenv()

with open("./config.yaml", "r") as f:
    config = yaml.safe_load(f)

provider = config["model_setting"]["provider"]
provider_key = config["model_setting"]["provider"]

# 2. Resolve model name and provider for init_chat_model
if provider_key == "gemini":
    model_name = config["providers"]["gemini"]["model_name"]
    model_provider = "google_genai"
    print(f"☁️ Initialized Cloud Provider: Gemini ({model_name})")

elif provider_key == "ollama":
    selected_local = config["model_setting"]["local_model"]
    if selected_local in config["providers"]["ollama"]["models"]:
        model_name = config["providers"]["ollama"]["models"][selected_local]
    else:
        raise ValueError(f"Unknown local model option: '{selected_local}'")
    
    model_provider = "ollama"
    print(f"🤖 Initialized Local Provider: Ollama -> {selected_local.upper()} ({model_name})")

else:
    raise ValueError(f"Unknown provider '{provider_key}' set in config.yaml")


@dataclass
class Context:
    user_id: str


@dataclass
class ResponseFormat:
    summary: str
    temperature_celsius: float
    temperature_fahrenheit: float
    humidity: float


@tool('get_weather', description='Return weather information for a given city', return_direct=False)
def get_weather(city: str):
    response = requests.get(f'https://wttr.in/{city}?format=j1')
    return response.json()

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


checkpointer = InMemorySaver()
llm = init_chat_model(
    model=model_name,
    model_provider=model_provider,
    temperature=0.1 # Optional extra kwargs if needed
)

agent = create_agent(
    model=llm,
    tools=[get_weather, locate_user],
    system_prompt='You are a helpful weather assistant, who always cracks jokes and is humorous while remaining helpful.',
    context_schema=Context,
    response_format=ResponseFormat,
    checkpointer=checkpointer
)

config = {'configurable': {'thread_id': '1'}}
response = agent.invoke(
    {
        'messages': [
            {'role': 'user', 'content': 'What is the weather like today?'}
        ]
    },
    config=config,
    context=Context(user_id='dlfjdlkfsjd')
)

# print(json.dumps(response, indent=4))
print(response['structured_response'])
print(response['structured_response'].summary)
print(response['structured_response'].temperature_celsius)
print("#" * 35)

"""
# Works with gemini
# print(response['structured_response'].summary)
# print(response['structured_response'].temperature_celsius)
# print(response['messages'][-1])

response = agent.invoke(
    {
        'messages': [
            {'role': 'user', 'content': 'What is the weather like today?'}
        ]
    },
    config=config,
    context=Context(user_id='ABC123')
)

# print(json.dumps(response, indent=4))
print(response['structured_response'])
print("#" * 35)


config2 = {'configurable': {'thread_id': 2}}
response = agent.invoke(
    {
        'messages': [
            {'role': 'user', 'content': 'What is the weather like today?'}
        ]
    },
    config=config,
    context=Context(user_id='ABC123')
)

# print(json.dumps(response, indent=4))
print(response['structured_response'])
print("#" * 35)

# Works with gemini
"""