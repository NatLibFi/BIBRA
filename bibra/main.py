import uvicorn
from fastapi import FastAPI

from bibra.api.v0.routes import router as v0_router

app = FastAPI(title="BIBRA API", version="0.1.0")

app.include_router(v0_router, prefix="/v0")


def main():
    """Run the FastAPI server."""
    uvicorn.run(app, host="0.0.0.0", port=8000)


if __name__ == "__main__":
    main()
