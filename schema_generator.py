"""
Schema generation module for financial statement normalization.

Uses AI to create mappings from varied line item names to consistent
canonical names, with critical mappings pre-defined for validation.
"""

import os
import json
import config


def get_all_unique_columns(statements_dir: str) -> list:
    """
    Scan all extracted JSON files to collect unique financial line item names.

    Args:
        statements_dir: Path to the 'financial_statements' directory

    Returns:
        Sorted list of unique column names found across all files
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
    Create schema map using AI with critical mappings for validation.

    Args:
        client: Initialized OpenAI client
        model: Model name to use
        column_list: List of all unique column names

    Returns:
        Dictionary mapping lowercase variations to snake_case canonical names
    """
    print("DEBUG: Generating schema map...")
    
    # Critical mappings in snake_case to match validation expectations
    critical_mappings = {
        "sales": "sales",
        "revenue": "sales",
        "revenues": "sales",
        "net sales": "sales",
        "net income": "net_income",
        "net profit": "net_income", 
        "net profit for the year": "net_income",
        "total assets": "total_assets",
        "total asset": "total_assets",
        "total liabilities": "total_liabilities",
        "total equity": "total_equity",
        "cash and cash equivalents at december 31": "cash_and_cash_equivalents_at_the_end_of_the_year",
        "cash and cash equivalents as at december 31": "cash_and_cash_equivalents_at_the_end_of_the_year",
        "cash and cash equivalents at the end of the year": "cash_and_cash_equivalents_at_the_end_of_the_year",
        "cash and cash equivalents": "cash_and_cash_equivalents_at_the_end_of_the_year",
    }
    
    print(f"DEBUG: {len(critical_mappings)} critical mappings defined")
    print(f"DEBUG: Sending {min(len(column_list), 150)} items to AI")
    
    # Simplified prompt for AI normalization
    prompt = f"""
Normalize financial line items by grouping similar variations. Return snake_case canonical names.

If an item is clearly similar to one of these, map it there:
- sales (for revenue items)
- net_income (for profit items)
- total_assets, total_liabilities, total_equity (for balance sheet totals)
- cash_and_cash_equivalents_at_the_end_of_the_year (for ending cash only)

Otherwise create new snake_case canonical names. Don't force unrelated items together.

Return JSON: {{"canonical_name": ["Variation 1", "variation 2"]}}

Items to normalize:
{json.dumps(column_list[:150], indent=2)}
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
            print("Warning: AI returned empty response, using critical mappings only")
            return critical_mappings

        ai_schema = json.loads(content)
        
        # Build reverse map: variations -> canonical (lowercase)
        reverse_map = critical_mappings.copy()
        for canonical, variations in ai_schema.items():
            canonical_clean = canonical.lower().strip()
            for variation in variations:
                var_key = variation.lower().strip()
                # Don't override critical mappings
                if var_key not in critical_mappings:
                    reverse_map[var_key] = canonical_clean
        
        print(f"DEBUG: Mapped {len(reverse_map)} total variations")
        return reverse_map

    except Exception as e:
        print(f"Warning: AI schema generation failed: {e}")
        print("Using critical mappings only")
        return critical_mappings