from dataclasses import dataclass

from dotenv import load_dotenv

from langchain.agents import create_agent
from langchain.agents.middleware import ModelRequest, ModelResponse, dynamic_prompt


load_dotenv()

@dataclass
class Context:
    user_role: str

@dynamic_prompt
def user_role_prompt(request: ModelRequest) -> str:
    user_role = request.runtime.context.user_role
    base_prompt = 'You are a helpful and very concise assistant.'

    match user_role:
        case 'expert':
            return f'{base_prompt} Provide detail technical responses.'
        case 'beginner':
            return f'{base_prompt} Keep your explanations simple and basic.'
        case 'child':
            return f'{base_prompt} Explain everything as if you were literally talking to a five-year old.'
        case _:
            return base_prompt

agent = create_agent(
    model='gpt-4.1-mini',
    middleware=[user_role_prompt],
    context_schema=Context
)

response = agent.invoke({
    'messages': [{'role': 'user', 'content': 'Explain PCA.'}]
}, context=Context(user_role='beginner'))
print(response)
