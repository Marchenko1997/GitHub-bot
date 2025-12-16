from fastapi import FastAPI
from .routes.github import router
from .logger import log_info

app = FastAPI()

app.include_router(router)


@app.get("/")
def root():
    return {"status": "ok"}


@app.get("/health")
def health():
    return {"status": "ok"}


if __name__ == "__main__":
    log_info("Starting FastAPI GitHub webhook server...")
    import uvicorn

    uvicorn.run("app.main:app", host="0.0.0.0", port=8000)
