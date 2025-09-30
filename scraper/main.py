import asyncio
from fastapi import FastAPI
from pydantic import BaseModel
from typing import List
from playwright.async_api import async_playwright

app = FastAPI(title="Edelweiss Scraper")

class ISBNRequest(BaseModel):
    isbn: str

class ISBNsRequest(BaseModel):
    isbns: List[str]

async def scrape_isbns(isbns: List[str]):
    results_by_isbn = {}
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        for isbn in isbns:
            context = await browser.new_context()
            page = await context.new_page()

            try:
                await page.goto("https://www.edelweiss.plus/#dashboard", wait_until="networkidle")
                await page.fill('input[name="keywords"]', '')
                await page.wait_for_timeout(1000)
                await page.fill('input[name="keywords"]', str(isbn))
                await page.wait_for_timeout(500)
                await page.keyboard.press("Enter")
                await page.wait_for_load_state("networkidle")

                try:
                    await page.wait_for_selector('div.productRowBody___XM7bE', timeout=15000)
                except:
                    results_by_isbn[isbn] = {
                        "status": "no_data_found",
                        "message": f"No results found on Edelweiss for ISBN {isbn}",
                        "books": []
                    }
                    await context.close()
                    continue

                books_data = []
                book_elements = await page.query_selector_all('div.productRowBody___XM7bE')

                for book in book_elements:
                    title_elem = await book.query_selector('p[class*="titleName"]')
                    subtitle_elem = await book.query_selector('span[class*="subTitleName"]')
                    author_elem = await book.query_selector('div[class*="contributors"]')
                    cover_elem = await book.query_selector('img[alt^="Cover for"]')

                    isbn_elem = await book.evaluate("""b => {
                        const spans = Array.from(b.querySelectorAll('div.dotDot span'));
                        const found = spans.find(s => /\\d{10,13}/.test(s.innerText));
                        return found ? found.innerText : null;
                    }""")

                    pub_info = await book.evaluate("""b => {
                        const divs = Array.from(b.querySelectorAll('div.dotDot'));
                        const found = divs.find(d => d.innerText.includes('Pub Date'));
                        return found ? found.innerText : null;
                    }""")

                    format_price = await book.evaluate("""b => {
                        const divs = Array.from(b.querySelectorAll('div.dotDot'));
                        const found = divs.find(d => /\\$/.test(d.innerText) || /Trade/.test(d.innerText));
                        return found ? found.innerText : null;
                    }""")

                    discount_code = await book.evaluate("""b => {
                        const divs = Array.from(b.querySelectorAll('div'));
                        const found = divs.find(d => d.innerText.includes('Discount Code'));
                        return found ? found.innerText : null;
                    }""")

                    related_products = await book.evaluate("""b => b.querySelector('.related-products-container button')?.innerText || null""")
                    pages = await book.evaluate("""b => Array.from(b.querySelectorAll('.biblioTwo___bgyhS div')).map(d => d.innerText).find(t => /\\d+\\s+pages/.test(t)) || null""")
                    dimensions = await book.evaluate("""b => {
                        const divs = Array.from(b.querySelectorAll('.biblioTwoItemContainer___QeMy0 div'));
                        return divs[0] ? divs[0].innerText : null;
                    }""")
                    status = await book.evaluate("""b => {
                        const divs = Array.from(b.querySelectorAll('div.dotDot'));
                        const found = divs.find(d => d.innerText.includes('Status:'));
                        return found || null;
                    }""")
                    sales_rights = await book.evaluate("""b => {
                        const buttons = Array.from(b.querySelectorAll('.biblioTwo___bgyhS button'));
                        const found = buttons.find(btn => btn.innerText.includes('View'));
                        return found ? found.innerText : null;
                    }""")
                    honors = await book.evaluate("""b => Array.from(b.querySelectorAll('.dotDot.flex img')).map(img => img.alt)""")
                    community = await book.evaluate("""b => Array.from(b.querySelectorAll('.communityItemsRow___utLCU button')).map(btn => btn.innerText)""")

                    bisac_button = await book.query_selector('button:has-text("BISAC")')
                    bisac_categories = None
                    if bisac_button:
                        try:
                            if await bisac_button.is_enabled():
                                await bisac_button.click()
                                popover = await page.wait_for_selector('div.MuiPopover-paper', timeout=3000)
                                bisac_categories = await popover.evaluate("""
                                    pop => Array.from(pop.querySelectorAll('li'))
                                            .slice(1)
                                            .map(li => li.innerText.trim())
                                """)
                        except:
                            pass

                    books_data.append({
                        "title": await title_elem.text_content() if title_elem else None,
                        "subtitle": await subtitle_elem.text_content() if subtitle_elem else None,
                        "author": await author_elem.text_content() if author_elem else None,
                        "isbn": isbn_elem,
                        "cover": await cover_elem.get_attribute('src') if cover_elem else None,
                        "pubInfo": pub_info,
                        "formatPrice": format_price,
                        "discountCode": discount_code,
                        "bisac": bisac_categories,
                        "relatedProducts": related_products,
                        "pages": pages,
                        "dimensions": dimensions,
                        "status": status,
                        "salesRights": sales_rights,
                        "honors": honors,
                        "community": community
                    })

                results_by_isbn[isbn] = {
                    "status": "data_found",
                    "message": f"Found {len(books_data)} book(s) for ISBN {isbn}",
                    "books": books_data
                }

            except Exception as e:
                results_by_isbn[isbn] = {
                    "status": "error",
                    "message": str(e),
                    "books": []
                }

            await context.close()

        await browser.close()
    return results_by_isbn

@app.post("/scrape")
async def scrape_single(request: ISBNRequest):
    return await scrape_isbns([request.isbn])

@app.post("/scrape-multiple")
async def scrape_multiple(request: ISBNsRequest):
    return await scrape_isbns(request.isbns)
