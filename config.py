import os
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

# --- API and Model Configuration ---
API_KEY = os.getenv("OPENAI_API_KEY")
if not API_KEY:
    raise ValueError("OPENAI_API_KEY not found in environment variables.")

CLIENT = OpenAI(api_key=API_KEY)
MODEL_TO_USE = "gpt-4o"

# --- Project Configuration ---
COMPANIES = [
    {
        "name": "Lindt & Sprüngli",
        "ticker": "LISP",
        "investor_relations_url": "https://www.lindt-spruengli.com/investors/financial-reporting/publications"
    },
    {
        "name": "Novo Nordisk",
        "ticker": "NVO",
        "investor_relations_url": "https://www.novonordisk.com/sustainable-business/esg-portal/integrated-reporting.html"
    }
]

# --- Directory Configuration ---
OUTPUT_DIR = "output"

# --- Processing Parameters ---
MAX_PAGES_TO_PROCESS = 3
TOC_SEARCH_LIMIT = 5
YEAR_REGEX_PATTERN = r'\b(201[5-9]|202[0-4])\b'
MAX_RETRIES = 2
TOLERANCE = 2
PAGE_OFFSET_SEARCH_WINDOW = 10