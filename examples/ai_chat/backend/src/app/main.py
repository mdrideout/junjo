from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from junjo.app import JunjoApp
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.google_genai import GoogleGenAiSdkInstrumentor

from app.db.db_config import engine, init_db
from app.db.models.chat.routes import chat_router
from app.db.models.chat_members.routes import chat_members_router
from app.db.models.contact.routes import contact_router
from app.db.models.message.routes import message_router
from app.db.queries.routes import queries_router
from app.log.config import setup_logging
from app.otel_config import init_otel
from app.workflows_basic.routes import workflows_router
from app.workflows_junjo.routes import workflows_junjo_router

# Load the environment variables
load_dotenv()

# Set up logging
setup_logging()

# Setup OpenTelemetry before anything else happens
init_otel()

# Dependency to manage the lifespan of the application
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    # Initialize Junjo
    JunjoApp(app_name="AI Chat Demo")

    # Initialize the database (OTEL instrumented in db_config.py)
    await init_db()
    yield

    # Shutdown
    # Close the database connection
    await engine.dispose()


# Create the FastAPI app
app = FastAPI(lifespan=lifespan)

# OTEL: Instrument FastAPI tracing
FastAPIInstrumentor.instrument_app(app)

# OTEL: Instrument Gemini AI tracing

GoogleGenAiSdkInstrumentor().instrument()

origins = [
    "http://localhost:5173",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routes
@app.get("/")
def read_root():
    return {"Hello": "World"}

# Add routers
app.include_router(chat_router)  # Chat API Router)
app.include_router(chat_members_router)  # Chat API Router
app.include_router(contact_router)  # Contact API Router
app.include_router(message_router)  # Message API Router
app.include_router(queries_router)  # Queries API Router
app.include_router(workflows_router)  # Workflow API Router
app.include_router(workflows_junjo_router)
