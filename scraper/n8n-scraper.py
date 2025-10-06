import asyncio
import json
import logging
import re
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List, Dict, Any
from playwright.async_api import async_playwright
from fantastic_fiction_scraper import search_fantastic_fiction, AuthorSearchRequest, AuthorSearchResponse

# Set up logging
logger = logging.getLogger(__name__)

def clean_string(text):
    """Clean string by removing newlines and extra whitespace"""
    if text is None:
        return None
    return str(text).strip().replace('\n', ' ').replace('\r', ' ')

async def login_to_edelweiss(page, email="hello@webbased.ai", password="WNFrs9Zxys2bd3."):
    """
    Login to Edelweiss with provided credentials
    
    Args:
        page: Playwright page object
        email: Login email
        password: Login password
    
    Returns:
        bool: True if login successful, False otherwise
    """
    try:
        print(f"Attempting to login to Edelweiss with email: {email}")
        
        # Check current URL and page content
        current_url = page.url
        print(f"Current URL: {current_url}")
        
        # Wait for login section to be visible first
        print("Waiting for login section...")
        await page.wait_for_selector('section.login, .login-form, form#login-form', timeout=10000)
        print("Login section found!")
        
        # Then wait for the email input specifically
        print("Waiting for email input...")
        await page.wait_for_selector('input[name="email"]', timeout=5000)
        print("Email input found!")
        
        # Find email input field
        email_selectors = [
            'input[name="email"]',
            'input[type="text"][placeholder*="Email"]',
            'input[type="email"]',
            'input[placeholder*="email" i]',
            'input[id*="email" i]'
        ]
        
        email_input = None
        for selector in email_selectors:
            try:
                email_input = await page.query_selector(selector)
                if email_input:
                    print(f"Found email input with selector: {selector}")
                    break
            except:
                continue
        
        if not email_input:
            print("Email input field not found")
            return False
        
        # Fill email
        await email_input.fill(email)
        await page.wait_for_timeout(500)
        
        # Find password input field
        password_selectors = [
            'input[name="pword"]',
            'input[type="password"]',
            'input[name="password"]',
            'input[placeholder*="password" i]',
            'input[id*="password" i]'
        ]
        
        password_input = None
        for selector in password_selectors:
            try:
                password_input = await page.query_selector(selector)
                if password_input:
                    print(f"Found password input with selector: {selector}")
                    break
            except:
                continue
        
        if not password_input:
            print("Password input field not found")
            return False
        
        # Fill password
        await password_input.fill(password)
        await page.wait_for_timeout(500)
        
        # Find and click login button
        login_selectors = [
            'button[type="submit"]',
            'button:has-text("Sign In")',
            'input[type="submit"]',
            'button:has-text("Log in")',
            'button:has-text("Login")',
            'button:has-text("Sign in")'
        ]
        
        login_button = None
        for selector in login_selectors:
            try:
                login_button = await page.query_selector(selector)
                if login_button:
                    button_text = await login_button.text_content()
                    print(f"Found login button with selector: {selector}, text: '{button_text}'")
                    break
            except:
                continue
        
        if not login_button:
            print("Login button not found")
            return False
        
        # Click login button
        await login_button.click()
        print("Clicked login button")
        
        # Wait for login to complete - look for dashboard or search elements
        try:
            await page.wait_for_selector('input[name="keywords"], .dashboard, [class*="dashboard"]', timeout=15000)
            print("Login successful - dashboard loaded")
            return True
        except:
            # If we don't find dashboard elements, try navigating to dashboard
            print("Navigating to dashboard after login...")
            await page.goto("https://www.edelweiss.plus/#dashboard", wait_until="domcontentloaded", timeout=10000)
            await page.wait_for_timeout(2000)
            
            # Check if we can find search elements now
            try:
                await page.wait_for_selector('input[name="keywords"]', timeout=5000)
                print("Dashboard loaded successfully")
                return True
            except:
                print("Login may have failed - dashboard not accessible")
                return False
            
    except Exception as e:
        print(f"Login error: {str(e)}")
        return False

async def extract_summary_from_title_click(page, book_element):
    """
    Click on book title and extract summary from side panel
    
    Args:
        page: Playwright page object
        book_element: The book element containing the title
    
    Returns:
        str: Summary text or None if not found
    """
    try:
        # Find the clickable title element (could be span, p, or a)
        title_link = await book_element.query_selector('.titleContainer___zhygQ span.subTitleName___TmSIq, .titleContainer___zhygQ p.titleName___t0XBl, .titleContainer___zhygQ a, a[class*="title"], a[id*="title"]')
        
        if not title_link:
            print("Title link not found in book element")
            return None
        
        # Debug: Check what element we found
        tag_name = await title_link.evaluate("el => el.tagName")
        class_name = await title_link.get_attribute("class")
        print(f"Found clickable element: {tag_name} with class: {class_name}")
        
        print("Clicking on book title to open side panel...")
        
        # Try different click methods to avoid modal interference
        try:
            # Method 1: Force click
            await title_link.click(force=True)
        except:
            try:
                # Method 2: JavaScript click
                await title_link.evaluate("element => element.click()")
            except:
                try:
                    # Method 3: Dispatch click event
                    await title_link.evaluate("""
                        element => {
                            const event = new MouseEvent('click', {
                                view: window,
                                bubbles: true,
                                cancelable: true
                            });
                            element.dispatchEvent(event);
                        }
                    """)
                except:
                    print("All click methods failed")
                    return None
        
        # Wait for side panel to appear and load
        print("Waiting for side panel to load...")
        
        # Step 1: Wait for any side panel/modal to appear
        try:
            await page.wait_for_selector('[class*="Panel"], [class*="Modal"], [class*="Drawer"], [class*="Sidebar"]', timeout=8000)
            print("Side panel container detected")
        except:
            print("No side panel container found, trying alternative selectors...")
        
        # Step 2: Wait for animation to complete
        await page.wait_for_timeout(3000)
        
        # Step 3: Look for specific side panel indicators
        side_panel_found = False
        side_panel_selectors = [
            '.rightPanel___Cl_TH',
            '.mainContent___KncIm', 
            'div[role="tabpanel"]',
            '[class*="rightPanel"]',
            '[class*="mainContent"]',
            '[class*="sidePanel"]',
            '[class*="drawer"]',
            '[class*="modal"]'
        ]
        
        for selector in side_panel_selectors:
            try:
                element = await page.query_selector(selector)
                if element:
                    print(f"Found side panel with selector: {selector}")
                    side_panel_found = True
                    break
            except:
                continue
        
        if not side_panel_found:
            print("No side panel found with any selector")
        
        # Step 4: Try clicking the "Content" button if available
        try:
            content_button = await page.query_selector('button[aria-label="Content"]')
            if content_button:
                print("Found Content button, clicking it to expand summary...")
                await content_button.click()
                await page.wait_for_timeout(2000)  # Wait for content to expand
                print("Content button clicked")
            else:
                print("Content button not found")
        except Exception as e:
            print(f"Error clicking Content button: {str(e)}")
        
        # Step 5: Additional wait for content to load
        await page.wait_for_timeout(2000)
        
        # Look for summary content in side panel with comprehensive approach
        print("Searching for summary content...")
        
        # First, let's see what's actually on the page
        try:
            all_elements = await page.query_selector_all('*')
            print(f"Total elements on page: {len(all_elements)}")
        except:
            pass
        
        # Comprehensive summary selectors - targeting the correct structure
        summary_selectors = [
            # Most specific - exact path from the actual HTML structure
            'div[role="tabpanel"][id*="title-references-tabpanel"] div.MuiBox-root.css-old1by div p',
            'div[role="tabpanel"][id*="title-references-tabpanel"] div.MuiBox-root div p',
            'div[role="tabpanel"][id*="title-references-tabpanel"] div p',
            
            # Look for the specific tabpanel that's visible (not hidden)
            'div[role="tabpanel"]:not([hidden]) div.MuiBox-root.css-old1by div p',
            'div[role="tabpanel"]:not([hidden]) div.MuiBox-root div p',
            'div[role="tabpanel"]:not([hidden]) div p',
            
            # Look for any tabpanel content
            'div[role="tabpanel"]:not([hidden]) *',
            'div[role="tabpanel"] *',
            
            # Look for MuiBox content in main content area
            '.mainContent___KncIm div.MuiBox-root.css-old1by div p',
            '.mainContent___KncIm div.MuiBox-root div p',
            '.mainContent___KncIm div p',
            
            # Look for content in right panel
            '.rightPanel___Cl_TH .mainContent___KncIm *',
            '.mainContent___KncIm *',
            
            # Look for any paragraph with substantial text in the right areas
            '.rightPanel___Cl_TH p',
            '.mainContent___KncIm p',
            
            # Look for content that might be revealed by Content button
            'div[class*="content"] p',
            'div[class*="summary"] p',
            'div[class*="description"] p',
            'div[class*="expandable"] p',
            'div[class*="collapsible"] p',
            
            # General content selectors
            '[class*="content"] *',
            '[class*="description"] *',
            '[class*="summary"] *',
            
            # Look for any substantial text content
            'p',
            'div p'
        ]
        
        summary_text = None
        for i, selector in enumerate(summary_selectors):
            try:
                elements = await page.query_selector_all(selector)
                print(f"Selector {i+1} '{selector}': Found {len(elements)} elements")
                
                for j, element in enumerate(elements):
                    try:
                        # Check if element is visible (not hidden)
                        is_visible = await element.is_visible()
                        if not is_visible:
                            continue
                            
                        text = await element.text_content()
                        if text and len(text.strip()) > 100:  # Look for substantial content
                            print(f"  Element {j+1} (visible): {text[:100]}...")
                            
                            # Additional check: make sure it looks like a book summary
                            # (contains book-related keywords and is not just UI text)
                            ui_keywords = ['narrow your results', 'type here to find', 'click', 'button', 'tab', 'menu']
                            if not any(keyword in text.lower() for keyword in ui_keywords):
                                if not summary_text:  # Take the first substantial content found
                                    summary_text = text
                                    print(f"  ✓ Using this as summary content")
                    except:
                        continue
                        
                if summary_text:
                    print(f"Found summary with selector: {selector}")
                    break
            except Exception as e:
                print(f"  Error with selector {i+1}: {str(e)}")
                continue
        
        if summary_text:
            summary_text = clean_string(summary_text)
            print(f"Extracted summary: {summary_text[:100]}...")
            return summary_text
        else:
            print("No summary found with specific selectors, trying fallback search...")
            
            # Fallback: Search entire page for content that looks like a book summary
            try:
                all_elements = await page.query_selector_all('*')
                print(f"Fallback search through {len(all_elements)} elements...")
                
                for i, element in enumerate(all_elements):
                    try:
                        text = await element.text_content()
                        if text and len(text.strip()) > 200:  # Look for longer content
                            # Check if it looks like a book summary (contains common book summary words)
                            summary_indicators = ['novel', 'story', 'character', 'author', 'book', 'published', 'review', 'critic']
                            if any(indicator in text.lower() for indicator in summary_indicators):
                                print(f"Found potential summary in element {i}: {text[:100]}...")
                                summary_text = text
                                break
                    except:
                        continue
                        
                if summary_text:
                    summary_text = clean_string(summary_text)
                    print(f"Fallback summary found: {summary_text[:100]}...")
                    return summary_text
                    
            except Exception as e:
                print(f"Fallback search error: {str(e)}")
            
            print("No summary found anywhere on the page")
            return None
            
    except Exception as e:
        print(f"Error extracting summary: {str(e)}")
        return None

app = FastAPI(title="Multi-Scraper API", version="1.0.0")

class ISBNRequest(BaseModel):
    isbn: str

class ISBNsRequest(BaseModel):
    isbns: List[str]

# Hachette HNZ Scraper Models
class BookData(BaseModel):
    title: str
    author: str
    isbn: str
    price: str
    format: str
    publication_date: str
    cover_url: str
    summary: str = None  # Add summary field for Edelweiss data

class ScraperResponse(BaseModel):
    success: bool
    message: str
    books: List[BookData]
    total_books: int

async def scrape_isbns(isbns: List[str], login_required=True):
    results_by_isbn = {}
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        for isbn in isbns:
            context = await browser.new_context()
            page = await context.new_page()

            # Retry logic for page loading
            max_retries = 3
            retry_count = 0
            success = False
            
            while retry_count < max_retries and not success:
                try:
                    # Navigate to the main page first to get to login
                    await page.goto("https://www.edelweiss.plus/", wait_until="domcontentloaded", timeout=60000)
                    await page.wait_for_timeout(2000)  # Give page time to fully load
                    success = True
                except Exception as e:
                    retry_count += 1
                    if retry_count < max_retries:
                        await page.wait_for_timeout(2000 * retry_count)  # Exponential backoff
                        logger.warning(f"Retry {retry_count} for ISBN {isbn}: {str(e)}")
                    else:
                        logger.error(f"Failed to load page after {max_retries} retries for ISBN {isbn}: {str(e)}")
                        raise e

            # Login if required
            if login_required:
                login_success = await login_to_edelweiss(page)
                if not login_success:
                    results_by_isbn[isbn.strip()] = {
                        "status": "login_failed",
                        "message": f"Failed to login to Edelweiss for ISBN {isbn.strip()}",
                        "books": []
                    }
                    await context.close()
                    continue

            try:
                await page.fill('input[name="keywords"]', '')
                await page.wait_for_timeout(1000)
                await page.fill('input[name="keywords"]', str(isbn))
                await page.wait_for_timeout(500)
                await page.keyboard.press("Enter")
                await page.wait_for_load_state("networkidle")

                try:
                    await page.wait_for_selector('div.productRowBody___XM7bE', timeout=15000)
                except:
                    results_by_isbn[isbn.strip()] = {
                        "status": "no_data_found",
                        "message": f"No results found on Edelweiss for ISBN {isbn.strip()}",
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

                    # Extract summary by clicking on title (only if login was successful)
                    summary = None
                    if login_required:
                        summary = await extract_summary_from_title_click(page, book)

                    books_data.append({
                        "title": clean_string(await title_elem.text_content() if title_elem else None),
                        "subtitle": clean_string(await subtitle_elem.text_content() if subtitle_elem else None),
                        "author": clean_string(await author_elem.text_content() if author_elem else None),
                        "isbn": clean_string(isbn_elem),
                        "cover": clean_string(await cover_elem.get_attribute('src') if cover_elem else None),
                        "pubInfo": clean_string(pub_info),
                        "formatPrice": clean_string(format_price),
                        "discountCode": clean_string(discount_code),
                        "bisac": [clean_string(cat) for cat in bisac_categories] if bisac_categories else None,
                        "relatedProducts": clean_string(related_products),
                        "pages": clean_string(pages),
                        "dimensions": clean_string(dimensions),
                        "status": clean_string(status),
                        "salesRights": clean_string(sales_rights),
                        "honors": [clean_string(honor) for honor in honors] if honors else [],
                        "community": [clean_string(item) for item in community] if community else [],
                        "summary": summary
                    })

                results_by_isbn[isbn.strip()] = {
                    "status": "data_found",
                    "message": f"Found {len(books_data)} book(s) for ISBN {isbn.strip()}",
                    "books": books_data
                }

            except Exception as e:
                results_by_isbn[isbn.strip()] = {
                    "status": "error",
                    "message": str(e),
                    "books": []
                }

            await context.close()

        await browser.close()
    return results_by_isbn

# Hachette Scraper Functions
async def navigate_and_login_hachette(url="https://ati.hachette.co.nz/login", customer_number="46628", catalog_query="January 2026 HNZ"):
    """
    Navigate to Hachette login page, enter customer number, and login.
    
    Args:
        url (str): The login URL
        customer_number (str): The customer number to enter
        catalog_query (str): The catalog to search for (e.g., "January 2026 HNZ", "December 2025 HCB")
    
    Returns:
        List[Dict]: List of book data dictionaries
    """
    async with async_playwright() as p:
        # Launch browser (you can change 'chromium' to 'firefox' or 'webkit')
        browser = await p.chromium.launch(headless=True)  # Set to True for headless mode
        page = await browser.new_page()
        
        try:
            print(f"Navigating to: {url}")
            await page.goto(url)
            
            # Wait for the page to load
            await page.wait_for_load_state('networkidle')
            
            # Get the page title
            title = await page.title()
            print(f"\nPage Title: {title}")
            
            # Print initial page content
            content = await page.text_content('body')
            print(f"\nInitial Page Content:")
            print("=" * 50)
            print(content)
            print("=" * 50)
            
            # Look for customer number input field
            print(f"\nLooking for customer number input field...")
            
            # Try different possible selectors for the input field
            input_selectors = [
                'input[type="text"]',
                'input[name*="customer"]',
                'input[name*="number"]',
                'input[id*="customer"]',
                'input[id*="number"]',
                'input[placeholder*="customer"]',
                'input[placeholder*="number"]',
                'input'
            ]
            
            input_field = None
            for selector in input_selectors:
                try:
                    input_field = await page.query_selector(selector)
                    if input_field:
                        print(f"Found input field with selector: {selector}")
                        break
                except:
                    continue
            
            if input_field:
                print(f"Entering customer number: {customer_number}")
                await input_field.fill(customer_number)
                
                # Look for login/submit button
                print("Looking for login button...")
                button_selectors = [
                    'button[type="submit"]',
                    'input[type="submit"]',
                    'button:has-text("Log in")',
                    'button:has-text("Login")',
                    'button:has-text("Submit")',
                    'button'
                ]
                
                login_button = None
                for selector in button_selectors:
                    try:
                        login_button = await page.query_selector(selector)
                        if login_button:
                            button_text = await login_button.text_content()
                            print(f"Found button with selector: {selector}, text: '{button_text}'")
                            break
                    except:
                        continue
                
                if login_button:
                    print("Clicking login button...")
                    await login_button.click()
                    
                    # Wait for navigation or page change
                    await page.wait_for_load_state('networkidle')
                    
                    # Print updated page content
                    new_title = await page.title()
                    print(f"\nNew Page Title: {new_title}")
                    
                    new_content = await page.text_content('body')
                    print(f"\nUpdated Page Content:")
                    print("=" * 50)
                    print(new_content)
                    print("=" * 50)
                    
                    # Look for the specified catalog link
                    print(f"\nLooking for '{catalog_query}' link...")
                    
                    # Try different selectors to find the link
                    link_selectors = [
                        f'a:has-text("{catalog_query}")',
                        f'a:has-text("{catalog_query.split()[0]}. {catalog_query}")',  # e.g., "01. January 2026 HNZ"
                        f'a[href*="{catalog_query.split()[-1]}"]',  # e.g., "HNZ" or "HCB"
                        'a'
                    ]
                    
                    catalog_link = None
                    for selector in link_selectors:
                        try:
                            links = await page.query_selector_all(selector)
                            for link in links:
                                link_text = await link.text_content()
                                if link_text and catalog_query in link_text:
                                    catalog_link = link
                                    print(f"Found catalog link with text: '{link_text.strip()}'")
                                    break
                            if catalog_link:
                                break
                        except:
                            continue
                    
                    if catalog_link:
                        print(f"Clicking on {catalog_query} link...")
                        await catalog_link.click()
                        
                        # Wait for the page to fully load and navigate to catalog
                        await page.wait_for_load_state('networkidle')
                        await asyncio.sleep(3)  # Additional wait to ensure page is fully loaded
                        
                        # Extract catalog type from query (e.g., "HNZ", "HCB")
                        catalog_type = catalog_query.split()[-1]
                        
                        # Wait for the URL to change to catalog or check if we're on the right page
                        try:
                            await page.wait_for_function(f"() => window.location.href.includes('{catalog_type}') || document.title.includes('{catalog_type}')", timeout=10000)
                        except:
                            print(f"Waiting for {catalog_type} page to load...")
                            await asyncio.sleep(2)
                        
                        # Get the new page content
                        catalog_title = await page.title()
                        catalog_url = page.url
                        print(f"\n{catalog_type} Page Title: {catalog_title}")
                        print(f"{catalog_type} Page URL: {catalog_url}")
                        
                        # Only extract if we're actually on the catalog page
                        if catalog_type in catalog_title or catalog_type in catalog_url:
                            catalog_content = await page.text_content('body')
                            print(f"\n{catalog_type} Page Content (first 500 chars):")
                            print("=" * 50)
                            print(catalog_content[:500])
                            print("=" * 50)
                            
                            # Extract book catalog entries from HTML li elements
                            print(f"\nExtracting book catalog entries from {catalog_type} HTML...")
                            
                            # Find all li elements that contain book information
                            li_elements = await page.query_selector_all('li')
                            book_entries = []
                            seen_isbns = set()  # To avoid duplicates
                            
                            for li in li_elements:
                                # Check if this li contains a book entry (has an h3 title and ISBN)
                                title_element = await li.query_selector('h3')
                                if title_element:
                                    title = await title_element.text_content()
                                    title = title.strip() if title else ""
                                    
                                    # Get author
                                    author_element = await li.query_selector('p.author')
                                    author = await author_element.text_content()
                                    author = author.strip() if author else ""
                                    
                                    # Get details (ISBN, price, format, date)
                                    details_element = await li.query_selector('p.details')
                                    details = await details_element.text_content()
                                    details = details.strip() if details else ""
                                    
                                    # Get cover image URL
                                    img_element = await li.query_selector('img')
                                    cover_url = ""
                                    if img_element:
                                        cover_url = await img_element.get_attribute('src')
                                        if cover_url and not cover_url.startswith('http'):
                                            cover_url = 'https:' + cover_url
                                    
                                    # Parse details to extract ISBN, price, format, date
                                    isbn_match = re.search(r'978\d{10}|979\d{10}', details)
                                    price_match = re.search(r'\$\d+\.\d+', details)
                                    
                                    if title and isbn_match and price_match:
                                        isbn = isbn_match.group()
                                        
                                        # Skip if we've already seen this ISBN (avoid duplicates)
                                        if isbn in seen_isbns:
                                            continue
                                        seen_isbns.add(isbn)
                                        
                                        # Extract format and date
                                        format_match = re.search(r'(Paperback|Hardback)(?:\s*-\s*[A-Z]\s*Format)?', details)
                                        date_match = re.search(r'(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{4}', details)
                                        
                                        book_data = {
                                            "title": title,
                                            "author": author,
                                            "isbn": isbn,
                                            "price": price_match.group(),
                                            "format": format_match.group() if format_match else "",
                                            "publication_date": date_match.group() if date_match else "",
                                            "cover_url": cover_url,
                                            "details": details
                                        }
                                        
                                        book_entries.append(book_data)
                                        print(f"Found book: {title} by {author}")
                            
                            # Convert to JSON format (without details field)
                            # Remove details field from each book entry for JSON output
                            books_without_details = []
                            for book in book_entries:
                                book_copy = {k: v for k, v in book.items() if k != 'details'}
                                books_without_details.append(book_copy)
                            
                            if book_entries:
                                print(f"\nSuccessfully found {len(book_entries)} unique book(s)")
                                print(f"\nFirst few books:")
                                for i, book in enumerate(book_entries[:3]):
                                    print(f"{i+1}. {book['title']} by {book['author']} - {book['price']}")
                                
                                # Comment out CSV generation temporarily
                                # import csv
                                # csv_filename = "hachette_hnz_january_2026_all_books.csv"
                                # with open(csv_filename, 'w', newline='', encoding='utf-8') as csvfile:
                                #     fieldnames = ['title', 'author', 'isbn', 'price', 'format', 'publication_date', 'cover_url']
                                #     writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                                #     writer.writeheader()
                                #     for book in book_entries:
                                #         # Create a copy without the details field
                                #         book_copy = {k: v for k, v in book.items() if k != 'details'}
                                #         writer.writerow(book_copy)
                                
                                # Return the book data instead of saving to files
                                return books_without_details
                            else:
                                print("No book entries found!")
                                return []
                        else:
                            print(f"Not on {catalog_type} catalog page - skipping extraction")
                            return []
                    else:
                        print(f"{catalog_query} link not found!")
                        # Print all links for debugging
                        all_links = await page.query_selector_all('a')
                        print(f"Found {len(all_links)} total links:")
                        for i, link in enumerate(all_links[:20]):  # Show first 20 links
                            link_text = await link.text_content()
                            if link_text:
                                print(f"  Link {i+1}: '{link_text.strip()}'")
                        return []
                else:
                    print("Login button not found!")
                    return []
            else:
                print("Customer number input field not found!")
                # Print all input fields for debugging
                inputs = await page.query_selector_all('input')
                print(f"Found {len(inputs)} input fields:")
                for i, inp in enumerate(inputs):
                    input_type = await inp.get_attribute('type')
                    input_name = await inp.get_attribute('name')
                    input_id = await inp.get_attribute('id')
                    input_placeholder = await inp.get_attribute('placeholder')
                    print(f"  Input {i+1}: type='{input_type}', name='{input_name}', id='{input_id}', placeholder='{input_placeholder}'")
                return []
            
        except Exception as e:
            print(f"Error occurred: {e}")
            return []
        
        finally:
            # Close browser immediately for Docker
            await browser.close()

async def test_single_isbn(isbn: str, login_required: bool = True):
    """
    Test function to scrape a single ISBN with detailed output
    
    Args:
        isbn: ISBN to test
        login_required: Whether to login to Edelweiss
    
    Returns:
        dict: Detailed results for the ISBN
    """
    print(f"\n{'='*60}")
    print(f"TESTING SINGLE ISBN: {isbn}")
    print(f"LOGIN REQUIRED: {login_required}")
    print(f"{'='*60}")
    
    results = await scrape_isbns([isbn], login_required=login_required)
    
    if isbn in results:
        result = results[isbn]
        print(f"\nSTATUS: {result['status']}")
        print(f"MESSAGE: {result['message']}")
        
        if result['books']:
            print(f"\nFOUND {len(result['books'])} BOOK(S):")
            for i, book in enumerate(result['books'], 1):
                print(f"\n--- BOOK {i} ---")
                print(f"Title: {book.get('title', 'N/A')}")
                print(f"Subtitle: {book.get('subtitle', 'N/A')}")
                print(f"Author: {book.get('author', 'N/A')}")
                print(f"ISBN: {book.get('isbn', 'N/A')}")
                print(f"Cover: {book.get('cover', 'N/A')}")
                print(f"Publication Info: {book.get('pubInfo', 'N/A')}")
                print(f"Format/Price: {book.get('formatPrice', 'N/A')}")
                print(f"Discount Code: {book.get('discountCode', 'N/A')}")
                print(f"BISAC: {book.get('bisac', 'N/A')}")
                print(f"Pages: {book.get('pages', 'N/A')}")
                print(f"Dimensions: {book.get('dimensions', 'N/A')}")
                print(f"Status: {book.get('status', 'N/A')}")
                print(f"Sales Rights: {book.get('salesRights', 'N/A')}")
                print(f"Honors: {book.get('honors', 'N/A')}")
                print(f"Community: {book.get('community', 'N/A')}")
                print(f"Summary: {book.get('summary', 'N/A')}")
                if book.get('summary'):
                    print(f"Summary Length: {len(book['summary'])} characters")
        else:
            print("\nNO BOOKS FOUND")
    else:
        print(f"\nERROR: No results found for ISBN {isbn}")
    
    print(f"\n{'='*60}")
    return results

@app.post("/scrape")
async def scrape_single(request: ISBNRequest, login: bool = True):
    return await scrape_isbns([request.isbn], login_required=login)

@app.post("/scrape-multiple")
async def scrape_multiple(request: ISBNsRequest, login: bool = True):
    return await scrape_isbns(request.isbns, login_required=login)

# Hachette HNZ API Endpoints
@app.get("/", response_model=ScraperResponse)
async def root():
    """Root endpoint with basic info"""
    return ScraperResponse(
        success=True,
        message="Multi-Scraper API is running. Use /hachette/scrape?query=January%202026%20HNZ for Hachette (supports HNZ, HCB catalogs), /scrape for Edelweiss, or /fantastic-fiction/search?author_name=David%20Baldacci for Fantastic Fiction.",
        books=[],
        total_books=0
    )

@app.get("/hachette/scrape", response_model=ScraperResponse)
async def scrape_hachette_books(query: str = "January 2026 HNZ"):
    """
    Scrape books from Hachette catalog
    
    Args:
        query (str): The catalog query (e.g., "January 2026 HNZ", "December 2025 HCB", "February 2026 HNZ")
    
    Returns:
        ScraperResponse: JSON response with book data
    """
    try:
        # Validate query format (should contain month, year, and catalog type)
        query_parts = query.split()
        if len(query_parts) < 3:
            raise HTTPException(
                status_code=400, 
                detail="Query must be in format: 'Month Year CatalogType' (e.g., 'January 2026 HNZ', 'December 2025 HCB')"
            )
        
        # Extract catalog type for validation
        catalog_type = query_parts[-1]
        if catalog_type not in ['HNZ', 'HCB']:  # Add more catalog types as needed
            raise HTTPException(
                status_code=400, 
                detail="Catalog type must be one of: HNZ, HCB"
            )
        
        # Hardcoded Hachette login page and customer number
        url = "https://ati.hachette.co.nz/login"
        customer_number = "46628"
        
        # Run the scraper with the provided query
        books_data = await navigate_and_login_hachette(url, customer_number, query)
        
        # Convert to BookData objects
        books = [BookData(**book) for book in books_data]
        
        return ScraperResponse(
            success=True,
            message=f"Successfully scraped {len(books)} books from Hachette {catalog_type} catalog",
            books=books,
            total_books=len(books)
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Scraping failed: {str(e)}"
        )

# Fantastic Fiction API Endpoints
@app.post("/fantastic-fiction/search", response_model=AuthorSearchResponse)
async def search_fantastic_fiction_author(request: AuthorSearchRequest):
    """
    Search for an author on Fantastic Fiction website
    
    Args:
        request (AuthorSearchRequest): Request containing author name and search type
    
    Returns:
        AuthorSearchResponse: JSON response with found books
    """
    try:
        result = await search_fantastic_fiction(request.author_name, request.search_type)
        return result
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Fantastic Fiction search failed: {str(e)}"
        )

@app.get("/fantastic-fiction/search", response_model=AuthorSearchResponse)
async def search_fantastic_fiction_author_get(author_name: str, search_type: str = "author"):
    """
    Search for an author on Fantastic Fiction website (GET endpoint)
    
    Args:
        author_name (str): Name of the author to search for
        search_type (str): Type of search - "author", "book", or "series"
    
    Returns:
        AuthorSearchResponse: JSON response with found books
    """
    try:
        result = await search_fantastic_fiction(author_name, search_type)
        return result
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Fantastic Fiction search failed: {str(e)}"
        )

# Main function for testing
async def main():
    """Main function to run single ISBN test"""
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python main.py <ISBN> [login]")
        print("Example: python main.py 9781234567890")
        print("Example: python main.py 9781234567890 false  # Skip login")
        return
    
    isbn = sys.argv[1]
    login_required = True
    
    if len(sys.argv) > 2:
        login_required = sys.argv[2].lower() in ['true', '1', 'yes', 'y']
    
    await test_single_isbn(isbn, login_required)

if __name__ == "__main__":
    asyncio.run(main())
