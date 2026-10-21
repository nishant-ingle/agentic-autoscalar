import requests
from langchain.tools import tool, ToolRuntime
from schemas import Context


@tool('get_weather', description='Return weather information for a given city', return_direct=False)
def get_weather(city: str) -> dict:
    """Fetch current weather metrics from wttr.in and return a pruned dictionary."""
    response = requests.get(f'https://wttr.in/{city}?format=j1').json()
    current = response['current_condition'][0]
    return {
        "city": city,
        "temperature_celsius": float(current['temp_C']),
        "temperature_fahrenheit": float(current['temp_F']),
        "humidity": float(current['humidity']),
        "description": current['weatherDesc'][0]['value']
    }


@tool('locate_user', description="Look up a user's city based on runtime context")
def locate_user(runtime: ToolRuntime[Context]) -> str:
    """Map known user IDs to cities."""
    match runtime.context.user_id:
        case 'ABC123':
            return 'Vienna'
        case 'XYZ456':
            return 'London'
        case 'HJKL111':
            return 'Paris'
        case _:
            return 'Unknown'
