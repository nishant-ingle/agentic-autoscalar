import os
import yaml
from dotenv import load_dotenv

# 1. Load system environments and project configuration
load_dotenv()

with open("config.yaml", "r") as f:
    config = yaml.safe_load(f)

provider = config["model_setting"]["provider"]

# 2. Decoupled Model Factory Initialization
if provider == "gemini":
    from langchain_google_genai import ChatGoogleGenerativeAI
    
    model_name = config["providers"]["gemini"]["model_name"]
    llm = ChatGoogleGenerativeAI(model=model_name, thinking_level="low")
    print(f"☁️ Initialized Cloud Provider: Gemini ({model_name})")

elif provider == "ollama":
    from langchain_ollama import ChatOllama

    # 1. Read which specific local model you want to run
    selected_local = config["model_setting"]["local_model"]

    # 2. Extract the exact Ollama tag from your config dictionary
    if selected_local in config["providers"]["ollama"]["models"]:
        model_name = config["providers"]["ollama"]["models"][selected_local]
    else:
        raise ValueError(f"Unknown local model option: '{selected_local}'")

    # 3. Instantiate the model
    llm = ChatOllama(model=model_name)
    print(f"🤖 Initialized Local Provider: Ollama -> {selected_local.upper()} ({model_name})")

else:
    raise ValueError(f"Unknown provider '{provider}' set in config.yaml")

# 3. Core Logic (Completely independent of your model choice)
try:
    response = llm.invoke("What is the primary purpose of an AI Agent router?")
    print("\n--- Model Response ---")
    print(response.content)
except Exception as e:
    print(f"\n❌ Execution failed using provider '{provider}':")
    print(e)

