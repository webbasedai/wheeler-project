import asyncio
from playwright.async_api import async_playwright
import json
import csv

async def main():
    # Read the first 20 ISBNs from the CSV file
    isbns = []
    with open("Masterlists/MVP-AF.csv", 'r', encoding='utf-8') as file:
        reader = csv.DictReader(file)
        for i, row in enumerate(reader):
            if i >= 20:  # Only take first 20
                break
            isbns.append(row['ISBN'])
    
    print(f"Processing first 20 ISBNs from MVP-AF.csv...", flush=True)
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        results_by_isbn = {}
        
        # Initialize output file
        output_filename = "edelweiss_results.json"
        with open(output_filename, 'w', encoding='utf-8') as f:
            f.write('{\n  "summary": {\n    "total_isbns_processed": 0,\n    "isbns_with_data": 0,\n    "isbns_without_data": 0,\n    "total_books_found": 0\n  },\n  "results_by_isbn": {\n')
        
        for i, isbn in enumerate(isbns, 1):
            print(f"Processing ISBN {i}/20: {isbn}...", flush=True)
            
            # Create a new browser context for each ISBN to ensure complete isolation
            context = await browser.new_context()
            page = await context.new_page()
            
            print("Opening dashboard...", flush=True)
            await page.goto("https://www.edelweiss.plus/#dashboard", wait_until="networkidle")
            
            # Clear the search field and type the ISBN
            await page.fill('input[name="keywords"]', '')
            await page.wait_for_timeout(1000)
            
            # Debug: Check if field is actually cleared
            cleared_value = await page.input_value('input[name="keywords"]')
            print(f"After clearing, search field contains: '{cleared_value}'", flush=True)
            
            await page.fill('input[name="keywords"]', str(isbn))
            await page.wait_for_timeout(500)
            
            # Debug: Check what's in the search field after typing
            typed_value = await page.input_value('input[name="keywords"]')
            print(f"After typing, search field contains: '{typed_value}'", flush=True)
            
            await page.keyboard.press("Enter")
            
            # Wait for the page to load after search
            await page.wait_for_load_state("networkidle")
            
            # Debug: Check what's in the search field after search
            search_value = await page.input_value('input[name="keywords"]')
            print(f"After search, search field contains: '{search_value}'", flush=True)

            # Wait for results container
            try:
                await page.wait_for_selector('div.productRowBody___XM7bE', timeout=15000)
                print(f"Extracting data for ISBN {isbn}...", flush=True)
                has_data = True
            except Exception as e:
                print(f"No results found for ISBN {isbn}: {e}", flush=True)
                # Write no-data result to file immediately
                result_data = {
                    "status": "no_data_found",
                    "message": f"No results found on Edelweiss for ISBN {isbn}",
                    "books": []
                }
                with open(output_filename, 'a', encoding='utf-8') as f:
                    f.write(f'    "{isbn}": {json.dumps(result_data, ensure_ascii=False)},\n')
                await context.close()
                continue

            books_data = []

            # Loop through each book
            book_elements = await page.query_selector_all('div.productRowBody___XM7bE')
            print(f"Found {len(book_elements)} book elements for ISBN {isbn}", flush=True)
            
            for book_idx, book in enumerate(book_elements):
                title_elem = await book.query_selector('p[class*="titleName"]')
                subtitle_elem = await book.query_selector('span[class*="subTitleName"]')
                author_elem = await book.query_selector('div[class*="contributors"]')
                cover_elem = await book.query_selector('img[alt^="Cover for"]')
                
                # Debug: Print the title being extracted
                title_text = await title_elem.text_content() if title_elem else None
                print(f"Book {book_idx + 1} title: '{title_text}'", flush=True)

                # ISBN
                isbn_elem = await book.evaluate("""b => {
                    const spans = Array.from(b.querySelectorAll('div.dotDot span'));
                    const found = spans.find(s => /\\d{10,13}/.test(s.innerText));
                    return found ? found.innerText : null;
                }""")

                # Pub Info
                pub_info = await book.evaluate("""b => {
                    const divs = Array.from(b.querySelectorAll('div.dotDot'));
                    const found = divs.find(d => d.innerText.includes('Pub Date'));
                    return found ? found.innerText : null;
                }""")

                # Format / Price
                format_price = await book.evaluate("""b => {
                    const divs = Array.from(b.querySelectorAll('div.dotDot'));
                    const found = divs.find(d => /\\$/.test(d.innerText) || /Trade/.test(d.innerText));
                    return found ? found.innerText : null;
                }""")

                # Discount Code
                discount_code = await book.evaluate("""b => {
                    const divs = Array.from(b.querySelectorAll('div'));
                    const found = divs.find(d => d.innerText.includes('Discount Code'));
                    return found ? found.innerText : null;
                }""")

                # Related Products
                related_products = await book.evaluate("""b => b.querySelector('.related-products-container button')?.innerText || null""")

                #Pages
                pages = await book.evaluate("""b => {
                    return Array.from(b.querySelectorAll('.biblioTwo___bgyhS div'))
                        .map(d => d.innerText)
                        .find(t => /\\d+\\s+pages/.test(t)) || null;
                }""")

                # Dimensions / Weight
                dimensions = await book.evaluate("""b => {
                    const divs = Array.from(b.querySelectorAll('.biblioTwoItemContainer___QeMy0 div'));
                    return divs[0] ? divs[0].innerText : null;
                }""")

                # Status
                status = await book.evaluate("""b => {
                    const divs = Array.from(b.querySelectorAll('div.dotDot'));
                    const found = divs.find(d => d.innerText.includes('Status:'));
                    return found || null;
                }""")

                # Sales Rights
                sales_rights = await book.evaluate("""b => {
                    const buttons = Array.from(b.querySelectorAll('.biblioTwo___bgyhS button'));
                    const found = buttons.find(btn => btn.innerText.includes('View'));
                    return found ? found.innerText : null;
                }""")

                # Honors / Awards (alt text only)
                honors = await book.evaluate("""
                    b => Array.from(b.querySelectorAll('.dotDot.flex img'))
                               .map(img => img.alt)
                """)

                # Community stats
                community = await book.evaluate("""b => Array.from(b.querySelectorAll('.communityItemsRow___utLCU button')).map(btn => btn.innerText)""")

                # BISAC categories: click button if exists and extract all
                bisac_button = await book.query_selector('button:has-text("BISAC")')
                bisac_categories = None
                if bisac_button:
                    try:
                        if await bisac_button.is_enabled():
                            await bisac_button.click()
                            popover = await page.wait_for_selector('div.MuiPopover-paper', timeout=3000)
                            bisac_categories = await popover.evaluate("""
                                pop => Array.from(pop.querySelectorAll('li'))
                                        .slice(1)  // skip first <li> which is just "BISAC"
                                        .map(li => li.innerText.trim())
                            """)
                    except Exception as e:
                        pass  # BISAC extraction failed, continue without it

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

            # Store results for this ISBN
            result_data = {
                "status": "data_found",
                "message": f"Found {len(books_data)} book(s) for ISBN {isbn}",
                "books": books_data
            }
            results_by_isbn[isbn] = result_data
            
            # Write result to file immediately
            with open(output_filename, 'a', encoding='utf-8') as f:
                f.write(f'    "{isbn}": {json.dumps(result_data, ensure_ascii=False, indent=4)},\n')
            
            # Close the context to ensure complete cleanup
            await context.close()

        # Calculate summary statistics
        total_isbns = len(isbns)
        isbns_with_data = sum(1 for result in results_by_isbn.values() if result["status"] == "data_found")
        isbns_without_data = total_isbns - isbns_with_data
        total_books = sum(len(result["books"]) for result in results_by_isbn.values())

        print(f"Completed processing {total_isbns} ISBNs:")
        print(f"- ISBNs with data: {isbns_with_data}")
        print(f"- ISBNs without data: {isbns_without_data}")
        print(f"- Total books found: {total_books}")
        
        # Finalize the JSON file by closing the results section and updating summary
        with open(output_filename, 'r+', encoding='utf-8') as f:
            content = f.read()
            # Remove the last comma if it exists
            if content.endswith(',\n'):
                content = content[:-2] + '\n'
            # Close the results section and add summary
            content += '  },\n  "summary": {\n'
            content += f'    "total_isbns_processed": {total_isbns},\n'
            content += f'    "isbns_with_data": {isbns_with_data},\n'
            content += f'    "isbns_without_data": {isbns_without_data},\n'
            content += f'    "total_books_found": {total_books}\n'
            content += '  }\n}'
            
            f.seek(0)
            f.write(content)
            f.truncate()
        
        print(f"Results saved to {output_filename}")
        await browser.close()

asyncio.run(main())
