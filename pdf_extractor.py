"""
PDF extraction module for financial statements.

Uses AI to locate and extract financial statement tables from annual report PDFs.
"""

import fitz
import base64
import json
import time
import os
import re
from openai import OpenAI
import config


def find_statement_pages_with_ai(doc: fitz.Document) -> dict:
    """
    Identify pages containing the three main consolidated financial statements.
    
    Scans PDF for keyword candidates, then uses AI to distinguish actual
    statements from table of contents or summaries.
    
    Args:
        doc: Opened PyMuPDF document object
    
    Returns:
        Dictionary mapping statement types to 0-indexed page numbers:
        {'income': int|None, 'balance': int|None, 'cash_flow': int|None}
    """
    # Find all candidate pages that mention financial statements
    candidates = []
    keywords = ['income statement', 'balance sheet', 'cash flow', 'financial position', 'statement of operations']
    
    for page_num in range(doc.page_count):
        page = doc.load_page(page_num)
        text = page.get_text()
        text_lower = text.lower()
        
        if any(keyword in text_lower for keyword in keywords):
            candidates.append({
                'page': page_num + 1,  # 1-indexed for human readability
                'snippet': text[:1500]
            })
    
    print(f"DEBUG: Found {len(candidates)} candidate pages mentioning financial statements")
    
    if not candidates:
        return {'income': None, 'balance': None, 'cash_flow': None}
    
    # Ask AI to identify the 3 actual statement pages from all candidates
    prompt = f"""
    Below are excerpts from {len(candidates)} pages of an annual report. Each mentions financial statement keywords.
    
    Your task: Identify which 3 specific pages contain the actual CONSOLIDATED financial statements with full data tables.
    
    Requirements:
    - Look for "Consolidated Income Statement" (or "Statement of Operations")
    - Look for "Consolidated Balance Sheet" (or "Statement of Financial Position")
    - Look for "Consolidated Cash Flow Statement" (or "Statement of Cash Flows")
    - Ignore Table of Contents pages, summaries, or references to statements
    - Choose pages with actual multi-year data tables, not just mentions
    
    Return a JSON object with exactly 3 keys:
    {{
      "income_statement": <page_number>,
      "balance_sheet": <page_number>,
      "cash_flow_statement": <page_number>
    }}
    
    If you cannot find a statement, use null for that key.
    
    Pages to analyze:
    """
    
    for candidate in candidates[:30]:
        prompt += f"\n\n--- Page {candidate['page']} ---\n{candidate['snippet']}"
    
    try:
        response = config.CLIENT.chat.completions.create(
            model=config.MODEL_TO_USE,
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
            temperature=0,
            max_tokens=150
        )
        
        result = json.loads(response.choices[0].message.content)
        
        # Convert to 0-indexed page numbers
        found_pages = {
            'income': (result.get('income_statement') - 1) if result.get('income_statement') else None,
            'balance': (result.get('balance_sheet') - 1) if result.get('balance_sheet') else None,
            'cash_flow': (result.get('cash_flow_statement') - 1) if result.get('cash_flow_statement') else None
        }
        
        # Debug output
        income_page = found_pages['income'] + 1 if found_pages['income'] is not None else "Not found"
        balance_page = found_pages['balance'] + 1 if found_pages['balance'] is not None else "Not found"
        cash_page = found_pages['cash_flow'] + 1 if found_pages['cash_flow'] is not None else "Not found"
        
        print(f"DEBUG: AI identified - Income: page {income_page}, Balance: page {balance_page}, Cash Flow: page {cash_page}")
        
        return found_pages
        
    except Exception as e:
        print(f"Error in AI page identification: {e}")
        return {'income': None, 'balance': None, 'cash_flow': None}


def extract_single_statement(client: OpenAI, model: str, images: list, statement_name: str) -> dict or None:
    """
    Extract financial data from statement using GPT-4o Vision.
    
    Converts PDF pages to images and sends to vision model for table extraction.
    
    Args:
        client: Initialized OpenAI client
        model: Model name (e.g., "gpt-4o")
        images: List of base64-encoded JPEG strings (typically 3 pages)
        statement_name: Human-readable name (e.g., "Income Statement")
    
    Returns:
        Extracted data as {"2024": {"Line item": value, ...}, "2023": {...}}
        or None if extraction fails
    """
    print(f"DEBUG: Sending request to AI for: {statement_name}...")
    
    prompt = f"""
    Your task is to be a precise data extraction tool. Follow these steps to extract the **{statement_name}** from the provided images of an annual report.

    **Step 1: Locate the Correct Table**
    - Scan all provided images to find the main table for the **{statement_name}**.
    - Note that this statement might have alternative titles, such as "Statement of Operations", "Statement of Financial Position", or "Statements of Cash Flows". Find the best match.

    **Step 2: Identify Columns and Rows**
    - The columns of the table are the years (e.g., "2024", "2023").
    - The rows of the table are the financial line items (e.g., "Net sales", "Total assets").

    **Step 3: Extract Data**
    - For every line item in the table, extract the numerical value for each year.

    **Step 4: Format the Output**
    - Assemble the extracted data into a single, valid JSON object.
    - The top-level keys of the JSON must be the years as strings.
    - The values for each year must be an object containing the line items and their corresponding numerical values.

    **Formatting Rules:**
    - **Numbers Only:** All values must be numbers (integers or floats). Do not include currency symbols, commas, or letters.
    - **Negative Numbers:** Use a minus sign for negative numbers (e.g., -44522), not parentheses.
    - **Exact Names:** Use the exact line item names as they appear in the image.

    Example format for '{statement_name}':
    {{
      "2024": {{ "Net sales": 290403, "Cost of goods sold": -44522, ... }},
      "2023": {{ "Net sales": 232261, "Cost of goods sold": -35765, ... }}
    }}
    """
    
    messages = [{"role": "user", "content": [{"type": "text", "text": prompt}] + [{"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{img}"}} for img in images]}]
    
    try:
        response = client.chat.completions.create(
            model=model,
            messages=messages,
            response_format={"type": "json_object"},
            temperature=0,
            max_tokens=4096
        )
        choice = response.choices[0]
        if choice.message.content:
            return json.loads(choice.message.content)
        else:
            print(f"Error: OpenAI API returned an empty response for {statement_name}. Finish Reason: '{choice.finish_reason}'.")
            return None
    except Exception as e:
        print(f"An error occurred during the OpenAI API call for {statement_name}: {e}")
        return None


def process_report(report_filepath: str, statements_dir: str, ticker: str):
    """
    Extract all three financial statements from a single annual report PDF.
    
    Pipeline: Identify statement pages with AI → Extract 3-page windows as images
    → Send to GPT-4o Vision → Save structured JSON files
    
    Args:
        report_filepath: Full path to annual report PDF
        statements_dir: Base directory for saving extracted statements
        ticker: Company ticker for naming output files
    """
    year = re.search(r'(\d{4})', report_filepath).group(1)
    print(f"\n--- Processing report for year: {year} ---")

    statements_to_extract = {
        "Income Statement": ("income_statements", "income"),
        "Balance Sheet": ("balance_sheets", "balance"),
        "Cash Flow Statement": ("cash_flow_statements", "cash_flow"),
    }
    
    # Check if all JSON files for this year already exist
    all_json_exist = True
    for subdir, _ in statements_to_extract.values():
        json_path = os.path.join(statements_dir, subdir, f"{ticker}_{year}_{subdir}.json")
        if not os.path.exists(json_path):
            all_json_exist = False
            break
    if all_json_exist:
        print(f"DEBUG: All statements for {year} already exist. Skipping.")
        return

    try:
        doc = fitz.open(report_filepath)
        
        # Use AI to find the 3 statement pages
        found_pages = find_statement_pages_with_ai(doc)
        
        # Check if we found all statements
        if None in found_pages.values():
            missing = [k for k, v in found_pages.items() if v is None]
            print(f"Warning: Could not find statements: {missing}. Skipping {year}.")
            doc.close()
            return
        
        # Process each statement with pages before and after the identified page
        for statement_name, (subdir, stmt_key) in statements_to_extract.items():
            output_path = os.path.join(statements_dir, subdir, f"{ticker}_{year}_{subdir}.json")
            
            if os.path.exists(output_path):
                print(f"DEBUG: {statement_name} for {year} already exists. Skipping.")
                continue
            
            # Send page before, identified page, and page after (3 pages total)
            identified_page = found_pages[stmt_key]
            start_page = max(0, identified_page - 1)
            end_page = min(identified_page + 2, doc.page_count)
            
            images = []
            for page_num in range(start_page, end_page):
                pix = doc.load_page(page_num).get_pixmap(dpi=100)
                images.append(base64.b64encode(pix.tobytes("jpeg")).decode('utf-8'))
            
            print(f"DEBUG: Extracting {statement_name} from pages {start_page + 1} to {end_page}")
            
            # Extract this specific statement with retry logic
            statement_data = None
            for attempt in range(config.MAX_RETRIES):
                data = extract_single_statement(config.CLIENT, config.MODEL_TO_USE, images, statement_name)
                if data:
                    statement_data = data
                    break
                else:
                    print(f"Warning: Failed to extract {statement_name} on attempt {attempt + 1}. Retrying...")
                    time.sleep(3)
            
            if statement_data:
                with open(output_path, 'w') as f:
                    json.dump(statement_data, f, indent=4)
                print(f"✅ Successfully saved {statement_name} to '{output_path}'")
            else:
                print(f"❌ Failed to extract {statement_name} for {year} after {config.MAX_RETRIES} attempts.")
        
        doc.close()
            
    except Exception as e:
        print(f"Error processing report {year}: {e}")