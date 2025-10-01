"""
Financial statement validation module.

Validates extracted financial data against basic accounting principles and
marks failed extractions for re-processing in the self-correction loop.
"""

import pandas as pd
import os
import config
import re


def get_value(row: pd.Series, primary_col: str, fallback_cols: list = []) -> float:
    """
    Safely extract a numerical value from a DataFrame row with fallback columns.
    
    Args:
        row: A DataFrame row containing financial data
        primary_col: Primary column name to check
        fallback_cols: Alternative column names if primary is missing/invalid
        
    Returns:
        First valid numerical value found, or 0.0 if all options fail
    """
    if primary_col in row and pd.notna(row[primary_col]) and row[primary_col] != 0:
        return row[primary_col]
    for col in fallback_cols:
        if col in row and pd.notna(row[col]) and row[col] != 0:
            return row[col]
    return 0.0


def validate_income_statement(df: pd.DataFrame, tolerance: int) -> set:
    """
    Validate income statement requires positive sales and existing net income.
    
    Args:
        df: Unified income statement DataFrame
        tolerance: Not used (kept for consistent interface)
        
    Returns:
        Set of source PDF filenames that failed validation
    """
    print("\n--- Validating Unified Income Statement ---")
    failed_files = set()
    
    for _, row in df.iterrows():
        year = row['year']
        print(f"\nChecking year: {year}")
        
        # Check multiple variations for sales
        sales = get_value(row, 'sales', ['net_sales', 'revenue', 'revenues'])
        if pd.isna(sales) or sales <= 0:
            print(f"  ❌ FAIL: {year} - Missing or invalid sales")
            failed_files.add(row['file_source'])
            continue
        
        # Check multiple variations for net income
        net_income = get_value(row, 'net_income', ['net_profit', 'net_profit_for_the_year'])
        if pd.isna(net_income):
            print(f"  ❌ FAIL: {year} - Missing net income")
            failed_files.add(row['file_source'])
            continue
        
        print(f"  ✅ PASS: {year} - Has sales ({sales:,.0f}) and net income ({net_income:,.0f})")
    
    if not failed_files:
        print("  ✅ All years passed validation.")
    return failed_files


def validate_balance_sheet(df: pd.DataFrame, tolerance: int) -> set:
    """
    Validate balance sheet using fundamental equation: Assets = Liabilities + Equity.
    
    Args:
        df: Unified balance sheet DataFrame
        tolerance: Maximum allowed difference for accounting equation
        
    Returns:
        Set of source PDF filenames that failed validation
    """
    print("\n--- Validating Unified Balance Sheet ---")
    failed_files = set()
    
    for _, row in df.iterrows():
        year = row['year']
        print(f"\nChecking year: {year}")
        
        total_assets = get_value(row, 'total_assets', ['total_asset'])
        if pd.isna(total_assets) or total_assets <= 0:
            print(f"  ❌ FAIL: {year} - Missing or invalid total assets")
            failed_files.add(row['file_source'])
            continue
        
        total_liabilities = get_value(row, 'total_liabilities')
        total_equity = get_value(row, 'total_equity')
        
        if not pd.isna(total_liabilities) and not pd.isna(total_equity):
            calc_assets = total_liabilities + total_equity
            if abs(total_assets - calc_assets) > tolerance:
                print(f"  ❌ FAIL: {year} - Assets ≠ Liabilities + Equity (diff: {abs(total_assets - calc_assets):,.1f})")
                failed_files.add(row['file_source'])
            else:
                print(f"  ✅ PASS: {year} - Balance sheet balances (Assets: {total_assets:,.0f})")
        else:
            print(f"  ⚪ SKIP: {year} - Missing liabilities or equity, cannot validate equation")
    
    if not failed_files:
        print("  ✅ All years passed validation.")
    return failed_files


def validate_cash_flow_statement(df: pd.DataFrame, tolerance: int) -> set:
    """
    Validate cash flow statement has positive ending cash balance.
    
    Args:
        df: Unified cash flow statement DataFrame
        tolerance: Not used (kept for consistent interface)
        
    Returns:
        Set of source PDF filenames that failed validation
    """
    print("\n--- Validating Unified Cash Flow Statement ---")
    failed_files = set()
    
    for _, row in df.iterrows():
        year = row['year']
        print(f"\nChecking year: {year}")
        
        # Try all reasonable variations for ending cash
        ending_cash = get_value(row, 'cash_and_cash_equivalents_at_the_end_of_the_year', [
            'cash_and_cash_equivalents_at_december_31',
            'cash_and_cash_equivalents_as_at_december_31',
            'cash_and_cash_equivalents'
        ])
        
        if pd.isna(ending_cash) or ending_cash <= 0:
            print(f"  ❌ FAIL: {year} - Missing or invalid ending cash")
            failed_files.add(row['file_source'])
        else:
            print(f"  ✅ PASS: {year} - Has ending cash balance ({ending_cash:,.0f})")
    
    if not failed_files:
        print("  ✅ All years passed validation.")
    return failed_files


def run_validation_phase(unified_dir: str) -> set:
    """
    Run all validation checks on unified CSVs and aggregate failures.
    
    Args:
        unified_dir: Directory containing unified statement CSV files
        
    Returns:
        Set of all source PDF filenames that contain failing data
    """
    print(f"\n{'='*20} RUNNING VALIDATION {'='*20}")
    all_failed_files = set()

    try:
        path = os.path.join(unified_dir, "unified_income_statement.csv")
        df = pd.read_csv(path)
        all_failed_files.update(validate_income_statement(df, config.TOLERANCE))
    except (FileNotFoundError, KeyError) as e:
        print(f"Warning: Could not validate income statement. Reason: {e}")

    try:
        path = os.path.join(unified_dir, "unified_balance_sheet_statement.csv")
        df = pd.read_csv(path)
        all_failed_files.update(validate_balance_sheet(df, config.TOLERANCE))
    except (FileNotFoundError, KeyError) as e:
        print(f"Warning: Could not validate balance sheet. Reason: {e}")
        
    try:
        path = os.path.join(unified_dir, "unified_cash_flow_statement.csv")
        df = pd.read_csv(path)
        all_failed_files.update(validate_cash_flow_statement(df, config.TOLERANCE))
    except (FileNotFoundError, KeyError) as e:
        print(f"Warning: Could not validate cash flow statement. Reason: {e}")

    return all_failed_files


def mark_failed_json_files(failed_source_pdfs: set, statements_dir: str, ticker: str):
    """
    Mark JSON files for re-processing by renaming with .FAILED suffix.
    
    Preserves original data for review while triggering re-extraction.
    
    Args:
        failed_source_pdfs: Source PDF filenames from failed validations
        statements_dir: Base directory containing statement subdirectories
        ticker: Company ticker for constructing JSON filenames
    """
    statements_subdirs = ["income_statements", "balance_sheets", "cash_flow_statements"]
    marked_count = 0
    
    for pdf_source_filename in failed_source_pdfs:
        year_match = re.search(r'(\d{4})', pdf_source_filename)
        if not year_match:
            print(f"Warning: Could not determine year from filename: {pdf_source_filename}")
            continue
        year = year_match.group(1)
        
        for subdir in statements_subdirs:
            json_filename = f"{ticker}_{year}_{subdir}.json"
            json_path = os.path.join(statements_dir, subdir, json_filename)
            failed_path = json_path + ".FAILED"
            
            if os.path.exists(json_path):
                if os.path.exists(failed_path):
                    os.remove(failed_path)
                
                print(f"DEBUG: Marking for re-extraction: {os.path.join(subdir, json_filename)}")
                os.rename(json_path, failed_path)
                marked_count += 1
    
    print(f"\n📋 Marked {marked_count} JSON files with .FAILED suffix for re-processing")


def cleanup_failed_markers(statements_dir: str, ticker: str):
    """
    Remove all .FAILED marker files after successful validation.
    
    Args:
        statements_dir: Base directory containing statement subdirectories
        ticker: Company ticker (unused, kept for consistency)
    """
    statements_subdirs = ["income_statements", "balance_sheets", "cash_flow_statements"]
    removed_count = 0
    
    for subdir in statements_subdirs:
        subdir_path = os.path.join(statements_dir, subdir)
        if not os.path.isdir(subdir_path):
            continue
            
        for filename in os.listdir(subdir_path):
            if filename.endswith('.FAILED'):
                failed_path = os.path.join(subdir_path, filename)
                print(f"DEBUG: Removing old failed marker: {os.path.join(subdir, filename)}")
                os.remove(failed_path)
                removed_count += 1
    
    if removed_count > 0:
        print(f"\n🧹 Cleaned up {removed_count} old .FAILED marker files")