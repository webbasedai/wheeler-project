import asyncio
import logging
from typing import List, Dict, Any
from pydantic import BaseModel
from playwright.async_api import async_playwright

logger = logging.getLogger(__name__)

class AuthorSearchRequest(BaseModel):
    author_name: str
    search_type: str = "author"

class AuthorSearchResponse(BaseModel):
    success: bool
    message: str
    books: List[Dict[str, Any]]
    total_books: int

async def search_fantastic_fiction(author_name: str, search_type: str = "author") -> AuthorSearchResponse:
    """
    Search for an author on Fantastic Fiction website
    
    Args:
        author_name (str): Name of the author to search for
        search_type (str): Type of search - "author", "book", or "series"
    
    Returns:
        AuthorSearchResponse: JSON response with found books
    """
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()
            
            # Navigate to Fantastic Fiction search page
            search_url = f"https://www.fantasticfiction.com/search/?q={author_name.replace(' ', '+')}"
            await page.goto(search_url, wait_until="domcontentloaded", timeout=30000)
            
            # Wait for search results to load
            await page.wait_for_timeout(2000)
            
            # Look for search results
            books = []
            
            # Try to find book results in various possible selectors
            book_selectors = [
                '.search-result',
                '.book-result',
                '.result',
                'div[class*="book"]',
                'div[class*="result"]'
            ]
            
            book_elements = []
            for selector in book_selectors:
                try:
                    elements = await page.query_selector_all(selector)
                    if elements:
                        book_elements = elements
                        logger.info(f"Found {len(elements)} book elements with selector: {selector}")
                        break
                except:
                    continue
            
            # If no specific book elements found, try to find any links that might be books
            if not book_elements:
                try:
                    # Look for links that might contain book information
                    links = await page.query_selector_all('a[href*="/book/"], a[href*="/author/"]')
                    book_elements = links
                    logger.info(f"Found {len(links)} potential book links")
                except:
                    pass
            
            # Extract book information
            for i, element in enumerate(book_elements[:10]):  # Limit to first 10 results
                try:
                    # Try to extract title
                    title = None
                    title_selectors = ['h3', 'h4', '.title', '.book-title', 'a']
                    for selector in title_selectors:
                        try:
                            title_elem = await element.query_selector(selector)
                            if title_elem:
                                title = await title_elem.text_content()
                                if title and title.strip():
                                    break
                        except:
                            continue
                    
                    # Try to extract author
                    author = None
                    author_selectors = ['.author', '.book-author', 'span[class*="author"]']
                    for selector in author_selectors:
                        try:
                            author_elem = await element.query_selector(selector)
                            if author_elem:
                                author = await author_elem.text_content()
                                if author and author.strip():
                                    break
                        except:
                            continue
                    
                    # Try to extract link
                    link = None
                    try:
                        link_elem = await element.query_selector('a')
                        if link_elem:
                            link = await link_elem.get_attribute('href')
                            if link and not link.startswith('http'):
                                link = f"https://www.fantasticfiction.com{link}"
                    except:
                        pass
                    
                    # Only add if we have at least a title
                    if title and title.strip():
                        book_data = {
                            "title": title.strip(),
                            "author": author.strip() if author else author_name,
                            "url": link,
                            "search_type": search_type
                        }
                        books.append(book_data)
                        logger.info(f"Found book {i+1}: {book_data['title']} by {book_data['author']}")
                
                except Exception as e:
                    logger.warning(f"Error extracting book {i+1}: {str(e)}")
                    continue
            
            await browser.close()
            
            return AuthorSearchResponse(
                success=True,
                message=f"Found {len(books)} books for author '{author_name}'",
                books=books,
                total_books=len(books)
            )
            
    except Exception as e:
        logger.error(f"Error searching Fantastic Fiction: {str(e)}")
        return AuthorSearchResponse(
            success=False,
            message=f"Search failed: {str(e)}",
            books=[],
            total_books=0
        )
