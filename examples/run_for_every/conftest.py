import os

from load_dotenv import load_dotenv

# point at the .env in the repo root
dotenv_path = os.path.join(os.path.dirname(__file__), ".env")
load_dotenv(dotenv_path)
