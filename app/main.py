from fastapi import FastAPI

app = FastAPI(title="Office Jukebox")


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}
