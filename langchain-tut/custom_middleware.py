from time import time

from langchain.agents import create_agent
from langchain.chat_models import init_chat_model
from langchain.agents.middleware import AgentMiddleware, AgentState
from langchain.messages import SystemMessage, HumanMessage, AIMessage
from dotenv import load_dotenv


load_dotenv()


class HooksDemo(AgentMiddleware):
    """"""
    def __init__(self):
        super().__init__()
        self.start_time = 0.0

    def before_agent(self, state: AgentState, runtime):
        self.start_time = time()
        print('before agent triggered')
        return super().before_agent(state, runtime)

    def before_model(self, state, runtime):
        print('before model')
        return super().before_model(state, runtime)

    def after_model(self, state, runtime):
        print('after model')
        return super().after_model(state, runtime)

    def after_agent(self, state, runtime):
        print('after agent:', time() - self.start_time)
        return super().after_agent(state, runtime)


agent = create_agent('gpt-4o-mini', middleware=[HooksDemo()])
response = agent.invoke({
    'messages': [
        SystemMessage('You are a helpful assistant.'),
        HumanMessage('What is PCA?')
    ]
})

print(response['messages'][-1].content)
