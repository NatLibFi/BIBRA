from fastapi import APIRouter

router = APIRouter()


@router.get("/")
async def root():
    """Return the API version information."""
    from bibra import __version__

    return {"version": __version__, "message": "Welcome to BIBRA API v0"}
