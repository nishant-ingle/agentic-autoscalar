import os
import uuid
import subprocess
from typing import TypedDict, Annotated, Literal
from dotenv import load_dotenv

from langchain.chat_models import init_chat_model
from langchain_core.vectorstores import InMemoryVectorStore
from langchain_core.documents import Document
from langchain_openai import OpenAIEmbeddings
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph.message import add_messages
from langgraph.types import interrupt, Command

from pydantic import BaseModel, Field


load_dotenv()
llm = init_chat_model('openai:gpt-4.1-mini')
KNOWLEDGE = [
    "NeuralNine is a YouTube channel focused on programming, AI, and software engineering tutorials."
    "LangGraph is a library for building stateful, multi-agent applications on top of LangChain."
    "A StateGraph in LangGraph defines nodes and edges that operate on a shared typed state."
    "Checkpointers Like InMemorySaver let LangGraph persist conversation state across invocations using a thread_id."
    "RAG (Retrieval-Augmented Generation) combines a retriever over a knowledge base with an LLM to ground answers in source documents."
]

vec_store = InMemoryVectorStore(OpenAIEmbeddings(model='text-embedding-3-small'))
vec_store.add_documents([Document(page_content=text) for text in KNOWLEDGE])


class IntentClassifier(BaseModel):
    msg_intent: Literal['chat', 'knowledge', 'code'] = Field(..., description='Classify whether the user want sto just chat, ask for knowledge or change code in the project.')


class State(TypedDict):
    messages: Annotated[list, add_messages]
    msg_intent: str | None
    next_node: str | None


def classify_intent(state: State):
    str_llm = llm.with_structured_output(IntentClassifier)
    res = str_llm.invoke([
        {'role': 'system',
         'content': 'Determine / classify whether the user wants to chat("chat"), retrieve knowlege ("knowledge") or change code ("code").'},
         {'role': 'user',
          'content': state['messages'][-1].content}
    ])

    return {'msg_intent': res.msg_intent}


def prompt_llm_chat(state: State):
    messages = [
        {'role': 'system',
         'content': 'You are a talkative chatbot for fun. Be nice.'}
    ] + state['messages']
    res = llm.invoke(messages)
    return {'messages': [
            {'role': 'assistant',
             'content': res.content}]
            }

def prompt_llm_rag(state: State):
    query = state['messages'][-1].content
    documents = vec_store.similarity_search(query, k=3)
    context = '\n'.join(f'- {doc.page_content}' for doc in documents)

    messages = [
        {'role': 'system',
         'content': f'You are a RAG agent. Answer the user using only the context below. If the answer is not in it, say you don\'t know.\n\nContext: \n{context}'},
    ] + state['messages']
    res = llm.invoke(messages)
    return {'messages': [
            {'role': 'assistant',
             'content': res.content}]
            }

def prompt_llm_code(state: State):
    user_prompt = state['messages'][-1].content
    workspace = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'workspace')

    res = subprocess.run(
        ['agy', '-p', user_prompt, '--dangerously-skip-permissions'],
        cwd=workspace,
        capture_output=True,
        text=True
    )

    output = res.stdout.strip() or res.stderr.strip()

    return {
            'messages': [
                {'role': 'assistant', 'content': output}
            ]
    }

def prompt_llm_code_claude(state: State):
    user_prompt = state['messages'][-1].content
    workspace = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'workspace')

    res = subprocess.run(
        ['claude', '-p', user_prompt, '--permission-mode', 'acceptEdits'],
        cwd=workspace,
        capture_output=True,
        text=True
    )

    output = res.stdout.strip() or res.stderr.strip()

    return {
            'messages': [
                {'role': 'assistant', 'content': output}
            ]
    }

    # messages = [
    #     {'role': 'system',
    #      'content': 'No matter what the user says, always say "I am the CODING agent"'}    ] + state['messages']
    # res = llm.invoke(messages)
    # return {'messages': [
    #         {'role': 'assistant',
    #          'content': res.content}]
    #         }


def accept_coding(state: State):
    user_prompt = state['messages'][-1].content
    decision = interrupt(f'About to run Antigravity CLI with requeust:\n\n{user_prompt}\n\nApprove? (yes/no, or type a revised request)')
    text = str(decision).strip().lower()

    if text in ['y', 'yes', 'approve', 'ok']:
        return {'next_node': 'coding_agent'}

    if text in ['n', 'no', 'deny', 'cancel']:
        return {'messages': [{'role': 'assistant', 'content': 'Coding request was denied by the user.'}], 'next_node': 'denied'}

    return {'messages': [{'role': 'user', 'content': text}], 'next_node': 'accept_coding'}


graph_builder = StateGraph(State)
graph_builder.add_node('classifier', classify_intent)
graph_builder.add_node('chat_agent', prompt_llm_chat)
graph_builder.add_node('rag_agent', prompt_llm_rag)
graph_builder.add_node('coding_agent', prompt_llm_code)
graph_builder.add_node('accept_coding', accept_coding)

graph_builder.add_edge(START, 'classifier')
graph_builder.add_conditional_edges('classifier',
                                    lambda state: state['msg_intent'],
                                    {'chat': 'chat_agent',
                                     'knowledge': 'rag_agent',
                                     'code': 'accept_coding'})
graph_builder.add_conditional_edges('accept_coding', lambda state: 'end' if state.get('next_node') == 'denied' else state['next_node'],
                                    {'end': END, 'coding_agent': 'coding_agent', 'accept_coding': 'accept_coding'})

graph_builder.add_edge('chat_agent', END)
graph_builder.add_edge('rag_agent', END)
graph_builder.add_edge('coding_agent', END)

checkpointer = InMemorySaver()
graph = graph_builder.compile(checkpointer=checkpointer)
graph.get_graph().draw_mermaid_png(output_file_path='images/graph.png')

config = {'configurable': {'thread_id': uuid.uuid4()}}

while True:
    user_msg = input('Enter a message: ')
    result = graph.invoke({'messages': [{'role': 'user', 'content': user_msg}]}, config=config)

    while '__interrupt__' in result:
        prompt = result['__interrupt__'][0].value
        decision = input(f'{prompt}\n')
        result = graph.invoke(Command(resume=decision), config=config)

    print(result['messages'][-1].content)
