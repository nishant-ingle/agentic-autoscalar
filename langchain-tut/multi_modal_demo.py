import base64
from llm_factory import get_llm

# Helper function to encode local image to Base64
def encode_image(image_path: str) -> str:
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode("utf-8")

# 1. Initialize pre-configured LLM with auto-logging
llm = get_llm()

# 2. Encode local image file
base64_image = encode_image("./images/cat.png")

# 3. Construct message with OpenAI-compliant image payload
message = {
    'role': 'user',
    'content': [
        {'type': 'text', 'text': 'Describe the contents of this image.'},
        {
            'type': 'image_url',
            'image_url': {
                'url': f'data:image/png;base64,{base64_image}'
            }
        }
    ]
}

response = llm.invoke([message])
print(response.content)