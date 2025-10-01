import os
import json
import config

def get_all_unique_columns(statements_dir: str) -> list:
    """
    Scans all extracted JSON files to collect a list of every unique
    financial line item name that has been extracted.

    Args:
        statements_dir (str): The path to the 'financial_statements' directory.

    Returns:
        list: A sorted list of unique column names found across all files.
    """
    unique_columns = set()
    subdirs = ["income_statements", "balance_sheets", "cash_flow_statements"]

    for subdir in subdirs:
        subdir_path = os.path.join(statements_dir, subdir)
        if not os.path.isdir(subdir_path):
            continue

        for filename in os.listdir(subdir_path):
            if filename.endswith('.json'):
                filepath = os.path.join(subdir_path, filename)
                try:
                    with open(filepath, 'r') as f:
                        data = json.load(f)
                        for year_data in data.values():
                            if isinstance(year_data, dict):
                                unique_columns.update(year_data.keys())
                except (json.JSONDecodeError, AttributeError):
                    print(f"Warning: Could not process file: {filename}")

    return sorted(list(unique_columns))

def generate_schema_with_ai(client, model: str, column_list: list) -> dict:
    """
    Uses an AI model to create a schema map from a list of column names.
    Applies intelligent normalization using standard financial statement terminology.

    Args:
        client: An initialized OpenAI client.
        model (str): The AI model to use.
        column_list (list): A list of all unique column names.

    Returns:
        dict: A dictionary mapping each variation of a column name to its
              canonical name (e.g., {"revenues": "Net Sales", "net sales": "Net Sales"}).
    """
    print("DEBUG: Sending unique column list to AI for schema generation...")

    prompt = f"""
    You are an expert financial analyst. Normalize financial statement line items extracted from annual reports using STANDARD IFRS/GAAP terminology.

    **CRITICAL: Use these EXACT canonical forms (standard financial terminology):**
    
    **TEMPORAL REFERENCES:**
    - "at the end of the year" is CANONICAL (not December 31)
    - "at the beginning of the year" is CANONICAL (not January 1)
    - "for the year" is CANONICAL for period items
    - Map "at December 31" → "at the end of the year"
    - Map "as at December 31" → "at the end of the year"
    - Map "at January 1" → "at the beginning of the year"
    - Map "as at January 1" → "at the beginning of the year"

    **INCOME STATEMENT - Standard Line Items:**
    - "Net Sales" or "Revenue" (not Revenues)
    - "Cost of Goods Sold"
    - "Gross Profit"
    - "Operating Profit" (or "Operating Income")
    - "Net Profit for the Year" (standard IFRS terminology)
    - "Earnings Per Share"
    - "Research and Development Costs"
    - "Sales and Distribution Costs"
    - "Administrative Costs"
    - "Financial Income"
    - "Financial Expenses"
    - "Income Taxes"
    - "Profit Before Income Taxes"

    **BALANCE SHEET - Standard Line Items:**
    - "Property, Plant and Equipment"
    - "Intangible Assets"
    - "Total Non-Current Assets"
    - "Total Current Assets"
    - "Total Assets"
    - "Share Capital"
    - "Retained Earnings"
    - "Total Equity"
    - "Total Non-Current Liabilities"
    - "Total Current Liabilities"
    - "Total Liabilities"
    - "Total Equity and Liabilities"
    - "Cash and Cash Equivalents at the End of the Year"
    - "Trade Receivables"
    - "Trade Payables"
    - "Inventories"
    - "Borrowings"
    - "Deferred Tax Assets"
    - "Deferred Tax Liabilities"

    **CASH FLOW STATEMENT - Standard Line Items:**
    - "Net Cash Flow from Operating Activities" (singular "Flow")
    - "Net Cash Flow from Investing Activities"
    - "Net Cash Flow from Financing Activities"
    - "Cash and Cash Equivalents at the Beginning of the Year"
    - "Cash and Cash Equivalents at the End of the Year"
    - "Exchange Gains/(Losses) on Cash and Cash Equivalents"
    - "Net Change in Cash and Cash Equivalents"
    - "Depreciation, Amortisation and Impairment Losses"
    - "Change in Working Capital"
    - "Interest Paid"
    - "Interest Received"
    - "Income Taxes Paid"
    - "Purchase of Property, Plant and Equipment"
    - "Purchase of Intangible Assets"
    - "Proceeds from Sale of Property, Plant and Equipment"
    - "Dividends Paid"
    - "Purchase of Treasury Shares"
    - "Proceeds from Borrowings"
    - "Repayment of Borrowings"

    **OTHER NORMALIZATION RULES:**
    - Remove redundant parenthetical clarifications: "Operating cash flow (OCF)" → "Operating Cash Flow"
    - Standardize symbols: "(+)" → "Increase", "(-)" → "Decrease"
    - Use British spelling: "Amortisation" not "Amortization"
    - Prefer singular: "Cash Flow" not "Cash Flows" (unless grammatically incorrect)
    - Use title case for all canonical names
    - Group all variations under ONE canonical name

    Return JSON where:
    - Each KEY = canonical name (standard terminology, title case)
    - Each VALUE = list of ALL variations

    Example:
    {{
      "Cash and Cash Equivalents at the End of the Year": [
        "Cash and cash equivalents at the end of the year",
        "Cash and cash equivalents at December 31",
        "Cash and cash equivalents as at December 31",
        "Cash at bank",
        "Cash at bank and on hand"
      ],
      "Net Profit for the Year": [
        "Net profit",
        "Net profit for the year",
        "Net income"
      ],
      "Net Cash Flow from Operating Activities": [
        "Net cash flows from operating activities",
        "Net cash generated from operating activities",
        "Cash flow from operating activities (operating cash flow)",
        "Operating cash flow"
      ]
    }}

    Line items to normalize:
    ---
    {json.dumps(column_list, indent=2)}
    ---
    """
    
    try:
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
            temperature=0,
            max_tokens=4096
        )
        content = response.choices[0].message.content
        if not content:
            print("Error: AI schema generation returned an empty response.")
            return {}

        # The AI returns {canonical: [variations]}. Reverse it to {variation: canonical}
        ai_schema = json.loads(content)
        reverse_map = {
            variation.lower().strip(): canonical
            for canonical, variations in ai_schema.items()
            for variation in variations
        }
        print("DEBUG: AI schema generation successful.")
        print(f"DEBUG: Mapped {len(reverse_map)} variations to {len(ai_schema)} canonical names")
        return reverse_map

    except Exception as e:
        print(f"An error occurred during AI schema generation: {e}")
        return {}