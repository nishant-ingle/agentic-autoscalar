import os
from openai import OpenAI
from dotenv import load_dotenv

# Force load the .env file
load_dotenv()

print("Loaded API Key preview:", os.getenv("OPENAI_API_KEY", "NOT FOUND")[:10] + "...")

# Initialize the official OpenAI client explicitly
client = OpenAI()

try:
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": "ping"}],
        max_tokens=5)
    print("Success! Response from OpenAI:", response.choices[0].message.content)
except Exception as e:
    print("\n--- CAUGHT EXCEPTION ---")
    print(type(e).__name__)
    print(e)
finally:
    pass