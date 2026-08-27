import contextlib
import logging
import os
from importlib.resources import files

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


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI):
    """Handle application startup and shutdown events.

    Loads .env and initializes the project registry at startup to fail fast
    if the config file is missing or malformed, rather than deferring the
    error to the first request.
    """
    load_dotenv()
    registry = ProjectRegistry(os.environ.get("BIBRA_CONFIG"))
    registry.load()
    app.state.project_registry = registry
    logger.info("Startup complete: loaded %d project(s)", len(registry.list_projects()))
    yield


app = FastAPI(title="BIBRA API", version=__version__, lifespan=lifespan)

# Mount static files at /static path
app.mount(
    "/static",
    StaticFiles(directory=str(files("bibra").joinpath("static"))),
    name="static",
)

# Mount node_modules for static files (e.g., Bootstrap) if it exists within package...
if files("bibra").joinpath("node_modules").is_dir():
    app.mount(
        "/node_modules",
        StaticFiles(directory=str(files("bibra").joinpath("node_modules"))),
        name="node_modules",
    )
elif os.path.isdir("node_modules"):  # ...or in the current directory
    app.mount(
        "/node_modules", StaticFiles(directory="node_modules"), name="node_modules"
    )


@app.get("/", response_class=HTMLResponse)
async def root():
    """Return the static index.html page."""
    return FileResponse(str(files("bibra").joinpath("static/index.html")))


app.include_router(v0_router, prefix="/v0")


def main():
    """Run the FastAPI server."""
    uvicorn.run(app, host="0.0.0.0", port=8000)


if __name__ == "__main__":
    main()
