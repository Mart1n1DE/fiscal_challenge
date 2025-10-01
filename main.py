"""
Main execution script for automated financial statement extraction.

Orchestrates a four-phase pipeline for each company:
1. Setup: Create directory structure
2. Acquisition: Scrape and download annual report PDFs
3. Extraction: Use AI to extract financial statements from PDFs
4. Validation: Check data quality and trigger re-extraction if needed

The validation phase implements a self-correction loop that automatically
re-processes failed extractions up to MAX_RETRIES times.
"""

import os
import re
import time
import config

from web_scraper import find_annual_report_links, download_pdf
from pdf_extractor import process_report
from data_processor import create_and_save_unified_files
from data_validator import run_validation_phase, mark_failed_json_files, cleanup_failed_markers


if __name__ == "__main__":
    """
    Main entry point that processes all companies defined in config.COMPANIES.
    
    For each company:
    - Creates directory structure for reports, statements, and unified output
    - Scrapes investor relations page for annual report PDFs
    - Downloads PDFs for years matching YEAR_REGEX_PATTERN
    - Extracts three financial statements using AI vision model
    - Validates extracted data and triggers re-extraction for failures
    - Outputs unified CSV files with normalized column names
    """
    
    for company in config.COMPANIES:
        ticker = company["ticker"]
        print(f"\n{'='*30}\nPROCESSING COMPANY: {company['name']} ({ticker})\n{'='*30}")

        # Dynamically define paths for the current company
        reports_dir = os.path.join(config.OUTPUT_DIR, ticker, "annual_reports")
        statements_dir = os.path.join(config.OUTPUT_DIR, ticker, "financial_statements")
        unified_dir = os.path.join(config.OUTPUT_DIR, ticker, "unified_statements")

        # 1. SETUP: Ensure all necessary directories exist for this company
        os.makedirs(reports_dir, exist_ok=True)
        for subdir in ["income_statements", "balance_sheets", "cash_flow_statements"]:
            os.makedirs(os.path.join(statements_dir, subdir), exist_ok=True)

        # 2. ACQUISITION: Find and download all required PDF reports
        print(f"\n{'='*20} PHASE 1: ACQUIRING PDF REPORTS {'='*20}")
        
        annual_reports = find_annual_report_links(
            company["investor_relations_url"],
            config.YEAR_REGEX_PATTERN
        )
        
        if not annual_reports:
            print("No annual reports found. Exiting.")
            continue
        else:
            for year, pdf_url in annual_reports.items():
                report_filepath = os.path.join(reports_dir, f"{ticker}_{year}_annual_report.pdf")
                download_pdf(pdf_url, report_filepath)
        
        # 3. EXTRACTION (Initial Run)
        print(f"\n{'='*20} PHASE 2: INITIAL DATA EXTRACTION {'='*20}")
        for year in sorted(annual_reports.keys()):
            report_filepath = os.path.join(reports_dir, f"{ticker}_{year}_annual_report.pdf")
            if os.path.exists(report_filepath):
                process_report(report_filepath, statements_dir, ticker)
        
        # 4. VALIDATION & CORRECTION LOOP
        for attempt in range(1, config.MAX_RETRIES + 1):
            print(f"\n{'='*30}\nMAIN WORKFLOW: Attempt {attempt}/{config.MAX_RETRIES}\n{'='*30}")
            
            create_and_save_unified_files(statements_dir, unified_dir, ticker)
            failed_files = run_validation_phase(unified_dir)
            
            if not failed_files:
                print(f"\n✅ All validations passed for {ticker}!")
                cleanup_failed_markers(statements_dir, ticker)
                break
            
            print(f"\n⚠️ Validation failed for data from: {', '.join(failed_files)}")
            
            if attempt == config.MAX_RETRIES:
                print(f"\n❌ Reached max retries for {ticker}. Please review failed files manually.")
                print(f"💡 Tip: Check the files marked with .FAILED suffix in {statements_dir}")
                schema_map_path = os.path.join(unified_dir, "schema_map.json")
                if os.path.exists(schema_map_path):
                    print(f"💡 Removing cached schema map at {schema_map_path} (might be corrupted)")
                    os.remove(schema_map_path)
                break
            
            print("Triggering self-correction: Marking failed JSONs for re-extraction...")
            mark_failed_json_files(failed_files, statements_dir, ticker)

            # Re-run extraction only for the failed files
            for pdf_filename in failed_files:
                report_filepath = os.path.join(reports_dir, pdf_filename)
                process_report(report_filepath, statements_dir, ticker)

    print("\nAll companies processed.")