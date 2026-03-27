import uvicorn
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from bibra import __version__
from bibra.api.v0.routes import router as v0_router

app = FastAPI(title="BIBRA API", version=__version__)

# Mount static files at /static path
app.mount("/static", StaticFiles(directory="bibra/static"), name="static")

# Mount node_modules for static files (e.g., Bootstrap)
app.mount("/node_modules", StaticFiles(directory="node_modules"), name="node_modules")


@app.get("/")
async def root():
    """Return the static index.html page."""
    with open("bibra/static/index.html") as f:
        html_content = f.read()
    return HTMLResponse(content=html_content, status_code=200)


app.include_router(v0_router, prefix="/v0")


def main():
    """Run the FastAPI server."""
    uvicorn.run(app, host="0.0.0.0", port=8000)


if __name__ == "__main__":
    main()
