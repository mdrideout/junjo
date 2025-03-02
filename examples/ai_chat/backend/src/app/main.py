from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.db.db_config import engine, init_db
from app.db.models.contact.routes import contact_router
from app.log.config import setup_logging
from app.workflows.routes import workflows_router

# Load the environment variables
load_dotenv()

# Set up logging
setup_logging()

# Dependency to manage the lifespan of the application
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    # Initialize the database
    await init_db()
    yield

    # Shutdown
    # Close the database connection
    await engine.dispose()


# Create the FastAPI app
app = FastAPI(lifespan=lifespan)

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
app.include_router(contact_router)  # Contact API Router
app.include_router(workflows_router)  # Workflow API Router
