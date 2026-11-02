from dotenv import load_dotenv

from langchain.chat_models import init_chat_model
from langgraph.graph import MessagesState, StateGraph, START, END


load_dotenv()
llm = init_chat_model('openai:gpt-4.1-mini')

def prompt_llm(state: MessagesState):
    response = llm.invoke(state['messages'])
    return {'messages': [response]}


graph_builder = StateGraph(MessagesState)
graph_builder.add_node(prompt_llm)
graph_builder.add_edge(START, 'prompt_llm')
graph_builder.add_edge('prompt_llm', END)

graph = graph_builder.compile()

while True:
    user_msg = input('Enter message:')
    print(graph.invoke({'messages': [{'role': 'user', 'content': user_msg}]}))

