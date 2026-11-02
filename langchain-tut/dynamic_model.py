from dataclasses import dataclass
from dotenv import load_dotenv

from langchain.agents import create_agent
from langchain.chat_models import init_chat_model
from langchain.agents.middleware import ModelRequest, ModelResponse, wrap_model_call
from langchain.messages import SystemMessage, HumanMessage


load_dotenv()

basic_model = init_chat_model(model='gpt-4o-mini')
advanced_model = init_chat_model(model='gpt-4.1-mini')

@wrap_model_call
def dynamic_model_selection(request: ModelRequest, handler) -> ModelResponse:
    message_count = len(request.state['messages'])

    if message_count > 3:
        model = advanced_model
    else:
        model = basic_model

    request.model = model

    return handler(request)


agent = create_agent(model=basic_model, middleware=[dynamic_model_selection])

response = agent.invoke({
    'messages': [
        SystemMessage('You are a helpful assistant.'),
        HumanMessage('What is 1 + 1?'),
        # HumanMessage('What is 1 + 2?'),
        # HumanMessage('What is 1 + 3?'),
        # HumanMessage('What is 1 + 4?'),
    ]
})

print(response['messages'][-1].content)
print(response['messages'][-1].response_metadata['model_name'])
