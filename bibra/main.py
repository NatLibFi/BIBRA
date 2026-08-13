import logging
import os

import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

from bibra import __version__
from bibra.api.v0.routes import router as v0_router
from bibra.config import ProjectRegistry

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


app = FastAPI(title="BIBRA API", version=__version__)

# Mount static files at /static path
app.mount("/static", StaticFiles(directory="bibra/static"), name="static")

# Mount node_modules for static files (e.g., Bootstrap) if directory exists
if os.path.isdir("node_modules"):
    app.mount(
        "/node_modules", StaticFiles(directory="node_modules"), name="node_modules"
    )


@app.get("/", response_class=HTMLResponse)
async def root():
    """Return the static index.html page."""
    return FileResponse("bibra/static/index.html")


app.include_router(v0_router, prefix="/v0")


@app.on_event("startup")
async def startup_event():
    """Load .env and initialize the project registry at startup.

    Calls registry.load() to fail fast if the config file is missing or
    malformed, rather than deferring the error to the first request.
    """
    load_dotenv()
    registry = ProjectRegistry(os.environ.get("BIBRA_CONFIG"))
    registry.load()
    app.state.project_registry = registry
    logger.info("Startup complete: loaded %d project(s)", len(registry.list_projects()))


def main():
    """Run the FastAPI server."""
    uvicorn.run(app, host="0.0.0.0", port=8000)


if __name__ == "__main__":
    main()
