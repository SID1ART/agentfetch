import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .routes import router

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("agentfetch.api")

app = FastAPI(title="agentfetch API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)


@app.on_event("startup")
async def startup():
    try:
        from playwright.async_api import async_playwright

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            await browser.close()
        logger.info("Playwright browser warmed up")
    except Exception as e:
        logger.warning("Could not warm up Playwright: %s", e)


def cli():
    import uvicorn

    uvicorn.run("agentfetch.api.app:app", host="0.0.0.0", port=8080)
