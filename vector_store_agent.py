from dotenv import load_dotenv

from langchain.agents import create_agent
from langchain_openai import OpenAIEmbeddings
from langchain_community.vectorstores import FAISS
from langchain_core.tools import create_retriever_tool


load_dotenv()
embeddings = OpenAIEmbeddings(model='text-embedding-3-large')

texts = [
    'I love apples.',
    'I enjoy oranges.',
    'I think pears taste very good.',
    'I hate bananas.',
    'I dislike raspberries.',
    'I despise mangoes.',
    'I love Linux.',
    'I hate Windows.',
]

vector_store = FAISS.from_texts(texts, embedding=embeddings)

# print(vector_store.similarity_search('What food does the person like?', k=3))
# print(vector_store.similarity_search('What food does the person hate?', k=3))

retriever = vector_store.as_retriever(search_kwargs={'k': 3})
retriever_tool = create_retriever_tool(retriever, name='kb_search', description='Search the small product / fruit knowledge base for information.')
agent = create_agent(
    model='gpt-4.1-mini',
    tools=[retriever_tool],
    system_prompt= (
        "You are a helpful assistant. For questions about Macs, apples, or laptops, "
        "first call the kb_search tool to retrieve context, then answer succintly."
        "Maybe you have to use it multiple times before answering."
    )
)

result = agent.invoke({
    "messages": [{"role": "user", "content": "What three fruits does the person like and what three fruits does the person dislike?"}]
})

# print(result)
print(result["messages"][-1].content)
