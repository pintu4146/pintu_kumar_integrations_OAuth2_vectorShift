from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware


def setup_middleware(app: FastAPI) -> None:
    """
    Configures and adds all middleware to the application.

    Note: Middleware is processed in the reverse order of how it's added.
    The first middleware added is the outermost layer (last to process a request,
    first to process a response).
    """

    app.add_middleware(
        TrustedHostMiddleware, allowed_hosts=["localhost", "127.0.0.1"]
    )


    app.add_middleware(GZipMiddleware, minimum_size=1000)

    origins = [
        "http://localhost:3000",  # React app address for development
    ]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type", "Authorization"],
    )
