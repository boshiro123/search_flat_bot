from playwright.sync_api import sync_playwright
from playwright.async_api import async_playwright


def fetch_rendered_html_sync(url: str, wait_selector: str | None = None, timeout_ms: int = 20000) -> str:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
            viewport={"width": 1366, "height": 768},
            locale="ru-RU",
        )
        page = context.new_page()
        page.goto(url, wait_until="networkidle", timeout=timeout_ms)
        if wait_selector:
            try:
                page.wait_for_selector(wait_selector, timeout=timeout_ms)
            except Exception:
                pass
        html = page.content()
        context.close()
        browser.close()
        return html


async def fetch_rendered_html(url: str, wait_selector: str | None = None, timeout_ms: int = 20000) -> str:
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
            viewport={"width": 1366, "height": 768},
            locale="ru-RU",
        )
        page = await context.new_page()
        await page.goto(url, wait_until="networkidle", timeout=timeout_ms)
        if wait_selector:
            try:
                await page.wait_for_selector(wait_selector, timeout=timeout_ms)
            except Exception:
                pass
        html = await page.content()
        await context.close()
        await browser.close()
        return html

