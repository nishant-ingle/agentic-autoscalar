from langchain.agents import create_agent
from langgraph.checkpoint.memory import InMemorySaver

from llm_factory import get_llm
from schemas import Context, ResponseFormat
from tools import get_weather, locate_user

# 1. Initialize pre-configured LLM with auto-logging
llm = get_llm()

# 2. Setup Checkpointer & Agent
checkpointer = InMemorySaver()

agent = create_agent(
    model=llm,
    tools=[get_weather, locate_user],
    system_prompt=(
        "You are a helpful weather assistant.\n"
        "1. You MUST call `locate_user` first if the user does not specify a city.\n"
        "2. If `locate_user` returns 'Unknown', ask the user which city they are in. DO NOT guess a location.\n"
        "3. Once you have a valid city name, you MUST call the `get_weather` tool. NEVER invent or guess weather statistics yourself."
    ),
    context_schema=Context,
    response_format=ResponseFormat,
    checkpointer=checkpointer
)

# 3. Test Cases
test_cases = [
    # ('1', 'HJKL111', 'What is the weather like today?'),
    # ('1', 'ABC123', 'What is the weather like today?'),
    # ('2', 'ABC124', 'What is the weather like today?'),
    ('3', 'XYZ456', 'How is the weather today?')
]

if __name__ == "__main__":
    for thread_id, user_id, prompt in test_cases:
        print(f"\n--- Thread ID: {thread_id} | User ID: {user_id} ---")
        config_thread = {'configurable': {'thread_id': thread_id}}
        
        response = agent.invoke(
            {'messages': [{'role': 'user', 'content': prompt}]},
            config=config_thread,
            context=Context(user_id=user_id)
        )
        
        # for message in response['messages']:
        #     message.pretty_print()
            
        if response.get('structured_response'):
            print("\nStructured Output:", response['structured_response'])
            
        print("#" * 40)