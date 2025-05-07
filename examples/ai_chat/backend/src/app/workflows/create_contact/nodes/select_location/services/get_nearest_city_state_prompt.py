def get_nearest_city_state_prompt(lat: float, long: float) -> str:
    """Prompt to retrieve the closest city and state to the lat and long."""

    # Create the prompt
    return f"""
Return a JSON object with the nearest city and state given the following latitude and longitude.

Your JSON object should be in the following format:
{{
    "city": "City Name",
    "state": "State Name"
}}

The latitude and longitude you need to use are: {lat}, {long}

Do not output markdown or any other formatting. Return only valid JSON.
""".strip()
