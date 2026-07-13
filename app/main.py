from fastapi import FastAPI

app = FastAPI(
    title="TaskFlow API",
    description="API para gerenciamento de solicitações e demandas.",
    version="0.1.0",
)


@app.get("/")
def root() -> dict[str, str]:
    return {
        "message": "TaskFlow API está funcionando."
    }


@app.get("/health")
def health_check() -> dict[str, str]:
    return {
        "status": "healthy"
    }