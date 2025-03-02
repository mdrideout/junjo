from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.contact.routes import contact_router
from app.db.db_config import engine, init_db
from app.log.config import setup_logging

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

# Routes
@app.get("/")
def read_root():
    return {"Hello": "World"}

# Add routers
app.include_router(contact_router)
