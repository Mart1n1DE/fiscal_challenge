# web_scraper.py
import os
import re
import time
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import json
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options

def find_annual_report_links_with_selenium(base_url: str, year_pattern: str) -> dict:
    """
    Uses Selenium to click accordion elements and extract Annual Report links.
    
    Designed for sites like Lindt & Sprüngli where annual reports are hidden behind
    year-specific accordion/dropdown elements that must be clicked to reveal content.
    
    Args:
        base_url (str): The investor relations URL containing the accordions
        year_pattern (str): Regex pattern for years to find (e.g., r'\b(201[5-9]|202[0-4])\b')
    
    Returns:
        dict: A dictionary mapping years (strings) to their corresponding full PDF URLs
        
    Process:
        1. Opens browser and loads page
        2. Finds all accordion headers (h3.faq-heading elements)
        3. Clicks each year header to expand content
        4. Finds all "English" links within table rows
        5. Filters for rows where first column exactly matches "annual report"
        6. Maps each link to its year based on accordion section
    """
    print(f"DEBUG: Using Selenium for {base_url}...")
    
    chrome_options = Options()
    chrome_options.add_argument('--no-sandbox')
    chrome_options.add_argument('--disable-dev-shm-usage')
    chrome_options.add_argument('--log-level=3')
    chrome_options.add_experimental_option('excludeSwitches', ['enable-logging'])
    
    driver = webdriver.Chrome(options=chrome_options)
    annual_reports = {}
    year_regex = re.compile(year_pattern)
    
    try:
        driver.get(base_url)
        print("DEBUG: Page loaded, waiting for content...")
        time.sleep(3)
        
        # Find and click all year accordion elements
        h3_elements = driver.find_elements(By.CSS_SELECTOR, "h3.faq-heading")
        print(f"DEBUG: Found {len(h3_elements)} accordion headers")
        
        # Extract years from pattern and click them
        years_found = set()
        for elem in h3_elements:
            try:
                elem_text = elem.text.strip()
                year_match = year_regex.search(elem_text)
                if year_match and elem_text == year_match.group(1):
                    year = year_match.group(1)
                    years_found.add(year)
                    driver.execute_script("arguments[0].scrollIntoView();", elem)
                    time.sleep(0.3)
                    elem.click()
                    time.sleep(0.5)
            except:
                continue
        
        print(f"DEBUG: Clicked {len(years_found)} year accordions")
        time.sleep(2)
        
        # Find all "English" links
        english_links = driver.find_elements(By.LINK_TEXT, "English")
        print(f"DEBUG: Found {len(english_links)} 'English' links")
        
        # Extract Annual Report links
        for link in english_links:
            try:
                href = link.get_attribute('href')
                
                # Get the row label from table structure
                try:
                    tr_element = link.find_element(By.XPATH, "./ancestor::tr[1]")
                    first_td = tr_element.find_element(By.XPATH, "./td[1]")
                    row_label = first_td.text.strip().lower()
                except:
                    continue
                
                # Only process "Annual Report" rows (exact match)
                if row_label == "annual report":
                    # Find the year from the accordion section
                    try:
                        section = link.find_element(By.XPATH, "./ancestor::div[contains(@class, 'faq-item') or contains(@class, 'accordion')]")
                        year_heading = section.find_element(By.CSS_SELECTOR, "h3.faq-heading")
                        year_text = year_heading.text.strip()
                        
                        year_match = year_regex.search(year_text)
                        if year_match and href:
                            year = year_match.group(1)
                            if year not in annual_reports:
                                annual_reports[year] = href
                                print(f"DEBUG: Found {year}: {href}")
                    except:
                        continue
            except:
                continue
        
    except Exception as e:
        print(f"ERROR during Selenium automation: {e}")
    finally:
        driver.quit()
    
    print(f"DEBUG: Found {len(annual_reports)} annual reports via Selenium")
    return annual_reports

def find_annual_report_links(base_url: str, year_pattern: str) -> dict:
    """
    Main function to find and extract annual report PDF URLs from investor relations pages.
    
    Uses a two-stage approach:
    1. First attempts fast, simple BeautifulSoup scraping for static HTML
    2. Falls back to Selenium browser automation for JavaScript-rendered content
    
    Args:
        base_url (str): The investor relations URL to scrape
        year_pattern (str): Regex pattern for years to find (e.g., r'\b(201[5-9]|202[0-4])\b')
    
    Returns:
        dict: A dictionary mapping years (strings) to their corresponding full PDF URLs
              Example: {"2024": "https://example.com/reports/2024.pdf", ...}
    
    Simple Scraping Criteria:
        - Looks for links ending in .pdf or containing /download/ or /amfile/
        - Must contain keywords: 'annual report', 'geschäftsbericht', or 'jahresbericht'
        - Excludes half-year/quarterly reports
        - Requires finding at least 10 reports to be considered successful
    
    Fallback Behavior:
        - If simple scraping finds <10 reports, switches to Selenium
        - If simple scraping fails with exception, switches to Selenium
    """
    print(f"DEBUG: Starting scrape of {base_url}...")
    
    # Try simple requests first
    try:
        response = requests.get(base_url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=10)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.content, 'html.parser')
        all_links = soup.find_all('a', href=True)
        
        # Try simple scraping
        report_links = {}
        year_regex = re.compile(year_pattern)
        
        for link in all_links:
            href = link['href']
            link_text = link.get_text().strip().lower()
            
            is_download = '.pdf' in href.lower() or '/download/' in href.lower() or '/amfile/' in href.lower()
            if not is_download:
                continue
            
            # STRICTER KEYWORDS - exclude half-year reports
            keywords = ['annual report', 'geschäftsbericht', 'jahresbericht']
            exclude_keywords = ['half', 'halbjahr', 'semi-annual', 'quarterly', 'q1', 'q2', 'q3', 'q4']
            
            has_keyword = any(term in link_text for term in keywords) or any(term in href.lower() for term in keywords)
            has_exclude = any(term in link_text for term in exclude_keywords) or any(term in href.lower() for term in exclude_keywords)
            
            if not has_keyword or has_exclude:
                continue
            
            year_match = year_regex.search(link_text) or year_regex.search(href)
            if year_match:
                year = year_match.group(1)
                if year not in report_links:
                    full_url = urljoin(base_url, href)
                    report_links[year] = full_url
                    print(f"DEBUG: Found {year}: {full_url}")
        
        # Only use simple scraping if we found a reasonable number of reports (10+)
        if len(report_links) >= 10:
            print(f"DEBUG: Simple scraping successful, found {len(report_links)} reports")
            return report_links
        
        # If simple scraping found <10 reports, try Selenium
        print(f"DEBUG: Simple scraping found only {len(report_links)} reports. Trying Selenium...")
        return find_annual_report_links_with_selenium(base_url, year_pattern)
        
    except Exception as e:
        print(f"Error with simple scraping: {e}")
        print("DEBUG: Falling back to Selenium...")
        return find_annual_report_links_with_selenium(base_url, year_pattern)

def download_pdf(url: str, save_path: str) -> bool:
    """
    Downloads a PDF from a URL to the specified local path.
    
    Args:
        url (str): The URL of the PDF to download
        save_path (str): The local file path where the PDF should be saved
    
    Returns:
        bool: True if download was successful or file already exists, False otherwise
    
    Behavior:
        - Skips download if file already exists at save_path
        - Uses streaming download for large files (8KB chunks)
        - Includes User-Agent header to avoid bot blocking
        - Prints status messages for tracking progress
    
    Example:
        >>> download_pdf(
        ...     "https://example.com/report.pdf",
        ...     "output/TICKER_2024_annual_report.pdf"
        ... )
        True
    """
    if os.path.exists(save_path):
        print(f"DEBUG: File '{os.path.basename(save_path)}' already exists. Skipping download.")
        return True
    
    print(f"DEBUG: Starting download from {url}...")
    try:
        response = requests.get(url, stream=True, headers={'User-Agent': 'Mozilla/5.0'})
        response.raise_for_status()
        with open(save_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        print(f"DEBUG: Successfully downloaded to {save_path}")
        return True
    except requests.RequestException as e:
        print(f"Error downloading PDF from '{url}'. Reason: {e}")
        return False