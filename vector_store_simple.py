from dotenv import load_dotenv

from langchain_openai import OpenAIEmbeddings
from langchain_community.vectorstores import FAISS


load_dotenv()
embeddings = OpenAIEmbeddings(model='text-embedding-3-large')

texts = [
    'Apple make very good computers.',
    'I believe Apple is innovative!',
    'I love apples.',
    'I am a fan of Macbooks.',
    'I enjoy oranges.',
    'I like Lenovo Thinkpads.',
    'I think pear taste very good.'
]

vector_store = FAISS.from_texts(texts, embedding=embeddings)

# print(vector_store.similarity_search('Apples are my favorite food.', k=7))
print(vector_store.similarity_search('Linux is a great operating system.', k=7))