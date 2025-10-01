"""
Data processing module for consolidating financial statements.

Loads extracted JSON files, applies AI-generated schema normalization,
and outputs unified CSV files with consistent column names across years.
"""

import os
import json
import re
import pandas as pd
from schema_generator import get_all_unique_columns, generate_schema_with_ai
import config


def get_or_generate_schema_map(statements_dir: str, unified_dir: str) -> dict:
    """
    Load existing schema map or generate new one using AI.
    
    Checks for cached schema_map.json first to avoid redundant API calls.
    If not found, collects all unique column names and generates mapping.
    
    Args:
        statements_dir: Directory containing raw statement JSON files
        unified_dir: Output directory where schema_map.json is stored
        
    Returns:
        Dictionary mapping lowercase variations to canonical names
    """
    schema_map_path = os.path.join(unified_dir, "schema_map.json")

    if os.path.exists(schema_map_path):
        print("DEBUG: Loading existing schema map from file.")
        with open(schema_map_path, 'r') as f:
            return json.load(f)

    print("DEBUG: Schema map not found. Generating a new one with AI...")
    all_columns = get_all_unique_columns(statements_dir)
    if not all_columns:
        print("Error: No columns found to generate a schema. Aborting.")
        return {}

    schema_map = generate_schema_with_ai(config.CLIENT, config.MODEL_TO_USE, all_columns)

    # Normalize keys to avoid casing / whitespace mismatches
    schema_map = {k.lower().strip(): v for k, v in schema_map.items()}

    if schema_map:
        os.makedirs(unified_dir, exist_ok=True)
        with open(schema_map_path, 'w') as f:
            json.dump(schema_map, f, indent=4)
        print(f"DEBUG: New schema map saved to '{schema_map_path}'")

    return schema_map


def clean_column_name(col_name: str) -> str:
    """
    Convert string to clean snake_case format for DataFrame columns.
    
    Args:
        col_name: Raw column name (may contain spaces, capitals, symbols)
        
    Returns:
        Lowercase snake_case string with only alphanumeric and underscores
    """
    s = col_name.lower().strip()
    s = re.sub(r'[^a-z0-9_]+', '_', s)
    return s.strip('_')


def load_golden_records_from_subdirs(base_dir: str, ticker: str) -> tuple[dict, dict, dict]:
    """
    Load golden records by reading from statement subdirectories.
    
    Implements "golden record" principle: for each year, uses data from the
    most recently published report. This ensures restated figures are preferred
    over original publications.
    
    Args:
        base_dir: Base directory containing statement subdirectories
        ticker: Company ticker for constructing file_source attribution
        
    Returns:
        Tuple of three dictionaries (income, balance, cash_flow) where each
        maps year -> {financial_data: dict, file_source: str}
    """
    statement_map = {
        "income_statements": {},
        "balance_sheets": {},
        "cash_flow_statements": {},
    }

    for subdir, golden_dict in statement_map.items():
        statement_path = os.path.join(base_dir, subdir)
        if not os.path.isdir(statement_path):
            print(f"Warning: Subdirectory not found, skipping: {statement_path}")
            continue

        files = sorted(os.listdir(statement_path), reverse=True)
        print(f"Processing {len(files)} files in '{subdir}'...")

        for filename in files:
            match = re.search(r'(\d{4})', filename)
            if not match:
                print(f"Warning: Could not extract year from filename: {filename}")
                continue

            report_year_source = match.group(1)
            filepath = os.path.join(statement_path, filename)
            try:
                with open(filepath, 'r') as f:
                    data = json.load(f)
                    for year, statement_data in data.items():
                        if not isinstance(statement_data, dict):
                            print(f"Warning: Corrupt data in {filename} for year {year}. Skipping.")
                            continue
                        if year not in golden_dict:
                            golden_dict[year] = {
                                "financial_data": statement_data,
                                "file_source": f"{ticker}_{report_year_source}_annual_report.pdf",
                            }
            except (json.JSONDecodeError, AttributeError):
                print(f"Warning: Could not read or process corrupt file: {filename}")

    print("\nGolden record creation complete.")
    return statement_map["income_statements"], statement_map["balance_sheets"], statement_map["cash_flow_statements"]

def normalize_data(data_dict: dict, schema_map: dict) -> dict:
    """
    Apply schema map to unify line item names across years.
    
    Maps variations like "Revenues", "Net sales", "Turnover" to a single
    canonical name using the AI-generated schema. Unmapped items are kept
    with original names and reported to user.
    
    Args:
        data_dict: Dictionary mapping year -> {financial_data, file_source}
        schema_map: Dictionary mapping lowercase variations -> canonical names
        
    Returns:
        Normalized dictionary with consistent canonical names. Years with
        duplicate canonical name conflicts are excluded.
    """
    normalized_dict, unmapped_items = {}, set()

    for year, year_data in data_dict.items():
        normalized_year_data = {}
        skip_year = False
        
        for item_name, value in year_data['financial_data'].items():
            clean_item_name = item_name.lower().strip()
            canonical_name = schema_map.get(clean_item_name, item_name)

            if clean_item_name not in schema_map:
                unmapped_items.add(item_name)

            # Check for duplicate canonical names
            if canonical_name in normalized_year_data:
                print(f"ERROR: {year} - Duplicate canonical name '{canonical_name}'")
                print(f"  Both '{item_name}' and another item map to this name.")
                print(f"  This indicates either bad schema design or duplicate extraction.")
                print(f"  Skipping year {year}. Please review schema_map.json or re-extract this year.")
                skip_year = True
                break
            
            normalized_year_data[canonical_name] = value

        # Only add year if no conflicts occurred
        if not skip_year:
            normalized_dict[year] = {
                "financial_data": normalized_year_data,
                "file_source": year_data['file_source']
            }

    if unmapped_items:
        print(f"Info: The following items were not in the schema map and were added as new columns:")
        for item in sorted(unmapped_items):
            print(f" - {item}")

    return normalized_dict


def create_and_save_unified_files(statements_dir: str, unified_dir: str, ticker: str):
    """
    Orchestrate entire data processing workflow and save unified CSVs.
    
    Complete pipeline:
    1. Get or generate AI schema map
    2. Load golden records from all JSON files
    3. Normalize data using schema map
    4. Create DataFrames with clean column names
    5. Save three unified CSV files
    
    Args:
        statements_dir: Directory containing statement subdirectories with JSONs
        unified_dir: Output directory for CSV files and schema_map.json
        ticker: Company ticker for file naming
    """
    os.makedirs(unified_dir, exist_ok=True)

    # Get AI-generated schema map
    schema_map = get_or_generate_schema_map(statements_dir, unified_dir)
    if not schema_map:
        print("Error: Could not obtain schema map. Halting consolidation.")
        return

    income_data, balance_data, cash_flow_data = load_golden_records_from_subdirs(statements_dir, ticker)

    print("\n--- Normalizing Data ---")
    normalized_income = normalize_data(income_data, schema_map)
    normalized_balance = normalize_data(balance_data, schema_map)
    normalized_cash_flow = normalize_data(cash_flow_data, schema_map)

    for name, data in [
        ("income_statement", normalized_income),
        ("balance_sheet_statement", normalized_balance),
        ("cash_flow_statement", normalized_cash_flow),
    ]:
        if not data:
            print(f"\nNo data found for {name}. Skipping file creation.")
            continue

        # Create DataFrame
        df = pd.DataFrame.from_dict({year: d['financial_data'] for year, d in data.items()}, orient='index')
        df['file_source'] = pd.Series({year: d['file_source'] for year, d in data.items()})
        df.columns = [clean_column_name(col) for col in df.columns]
        df.reset_index(inplace=True)
        df.rename(columns={'index': 'year'}, inplace=True)

        # Reorder columns
        cols = ['year', 'file_source'] + [col for col in df.columns if col not in ['year', 'file_source']]
        df = df[cols].sort_values(by='year', ascending=False)

        # Save CSV
        output_path = os.path.join(unified_dir, f"unified_{name}.csv")
        df.to_csv(output_path, index=False)
        print(f"\n✅ Unified {name.replace('_', ' ').title()} saved to: {output_path}")