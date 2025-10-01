# Financial Statement Extractor

Automated extraction and consolidation of financial statements from European company annual reports using AI-powered PDF parsing.

**Author:** Martin Leung  
**Assignment:** Fiscal.ai Data Developer Take Home

## Overview

This project extracts 10+ years of financial data (Income Statement, Balance Sheet, Cash Flow Statement) from company annual reports and consolidates them into clean, analysis-ready CSV files.

### Key Features

- **Automated PDF Discovery**: Scrapes investor relations pages to find and download annual reports
- **AI-Powered Extraction**: Uses GPT-4o Vision to locate and extract financial tables from PDFs
- **Smart Schema Normalization**: AI-generated schema maps variations like "Revenues", "Net sales" → single canonical name
- **Golden Record Logic**: Prioritizes restated figures from recent reports over original publications
- **Self-Correction Loop**: Validates extracted data and automatically re-processes failures
- **Multi-Company Support**: Process multiple companies in a single run

## Setup

### Prerequisites

- Python 3.10+
- OpenAI API key
- Chrome/Chromium browser (for Selenium fallback)

### Installation

1. Clone the repository:
```bash
git clone https://github.com/Mart1n1DE/fiscal_challenge.git
cd financial-statement-extractor
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Create `.env` file in project root:
```bash
OPENAI_API_KEY=sk-......
```

### Configuration

Edit `config.py` to customize:

```python
# Companies to process
COMPANIES = [
    {
        "name": "Lindt & Sprüngli",
        "ticker": "LISP",
        "investor_relations_url": "https://www.lindt-spruengli.com/investors/financial-reporting/publications"
    },
    {
        "name": "Novo Nordisk",
        "ticker": "NVO",
        "investor_relations_url": "https://www.novonordisk.com/sustainable-business/esg-portal/integrated-reporting.html"
    }
]

# Years to extract (regex pattern)
YEAR_REGEX_PATTERN = r'\b(201[5-9]|202[0-4])\b'  # 2015-2024

# Processing parameters
MAX_RETRIES = 2  # Re-extraction attempts for failed validations
TOLERANCE = 2    # Balance sheet equation tolerance (in data units)
```

## Usage

Run the entire pipeline:

```bash
python main.py
```

The script will:
1. Create directory structure for each company
2. Scrape and download annual report PDFs
3. Extract financial statements using AI
4. Validate data quality
5. Generate unified CSV files

### Output Structure

```
output/
└── {TICKER}/
    ├── annual_reports/
    │   ├── {TICKER}_2024_annual_report.pdf
    │   └── {TICKER}_2023_annual_report.pdf
    ├── financial_statements/
    │   ├── income_statements/
    │   │   └── {TICKER}_2024_income_statements.json
    │   ├── balance_sheets/
    │   └── cash_flow_statements/
    └── unified_statements/
        ├── schema_map.json
        ├── unified_income_statement.csv
        ├── unified_balance_sheet_statement.csv
        └── unified_cash_flow_statement.csv
```

### Final Output Files

Each unified CSV contains:
- `year`: Fiscal year
- `file_source`: Source PDF filename for data lineage
- Normalized financial line items in `snake_case`

Example (`unified_income_statement.csv`):
```csv
year,file_source,net_sales,cost_of_goods_sold,gross_profit,net_income,...
2024,NVO_2024_annual_report.pdf,290403,-44522,245881,45678,...
2023,NVO_2024_annual_report.pdf,232261,-35765,196496,38901,...
```

## Approach & Design Decisions

### 1. Web Scraping Strategy

**Challenge**: Investor relations pages vary widely (static HTML vs JavaScript-rendered).

**Solution**: Two-tier approach:
- **Tier 1**: Fast BeautifulSoup scraping for static content
- **Tier 2**: Selenium fallback for JavaScript-heavy sites (e.g., Lindt's accordion menus)

Auto-detects which approach to use based on results.

### 2. PDF Page Identification

**Challenge**: Financial statements can be anywhere in 100+ page PDFs.

**Solution**: AI-powered two-stage search:
1. Keyword scan finds ~30-50 candidate pages mentioning "income statement", etc.
2. GPT-4o analyzes page snippets to identify actual consolidated statements vs. ToC/summaries

This avoids brittle regex patterns and adapts to different report structures.

### 3. Data Extraction

**Challenge**: Financial tables have complex layouts, merged cells, and varying formats.

**Solution**: Vision model extraction:
- Convert PDF pages to 100 DPI JPEG images
- Send 3-page windows (target ± 1) to GPT-4o Vision
- Structured prompt ensures consistent JSON output format

**Why Vision over text extraction?**
- Preserves table structure (PyMuPDF text extraction loses row/column alignment)
- Handles merged cells, subtotals, and footnotes naturally
- Works across different report designs

### 4. Schema Normalization

**Challenge**: Line items vary across years ("Revenues" vs "Net sales" vs "Turnover").

**Solution**: AI-generated schema map:
1. Collect all unique column names from extracted JSONs
2. Send to GPT-4 with IFRS/GAAP terminology rules
3. Generate mapping: `{"revenues": "Net Sales", "net sales": "Net Sales", ...}`
4. Cache in `schema_map.json` for consistency

### 5. Golden Record Selection

**Challenge**: 2024 report contains restated 2023/2022 figures (more accurate than original reports).

**Solution**: "Most recent source wins":
- Process files in reverse chronological order
- Only add year data if not already present
- Result: Restated figures from 2024 report are used for 2023

**Example**:
```
2022 report has: 2022 data, 2021 data
2023 report has: 2023 data, 2022 data (restated), 2021 data (restated)
2024 report has: 2024 data, 2023 data (restated), 2022 data (restated)

Golden record uses:
- 2024 data from 2024 report
- 2023 data from 2024 report (restated)
- 2022 data from 2024 report (restated)
```

### 6. Self-Correction Loop

**Challenge**: AI extraction isn't 100% accurate.

**Solution**: Validation + automatic retry:
1. Run basic validation checks (e.g., Balance Sheet: Assets = Liabilities + Equity)
2. If validation fails, mark JSON files with `.FAILED` suffix
3. Re-extract only failed years (up to `MAX_RETRIES` times)
4. Continue until all validations pass or max retries reached

**Validations implemented**:
- Income Statement: Positive sales, net income exists
- Balance Sheet: Assets = Liabilities + Equity (within tolerance)
- Cash Flow: Ending cash balance exists and positive

### 7. Error Handling

**Duplicate canonical names**: If schema normalization creates conflicts (two source columns → same canonical name), the year is skipped with error message rather than silently overwriting data.

## Project Structure

```
.
├── main.py                 # Orchestration script
├── config.py               # Configuration settings
├── web_scraper.py          # PDF discovery and download
├── pdf_extractor.py        # AI-powered statement extraction
├── schema_generator.py     # AI schema normalization
├── data_processor.py       # Data consolidation and CSV generation
├── data_validator.py       # Quality checks and self-correction
├── requirements.txt        # Python dependencies
└── .env                    # API keys (not committed)
```

## Limitations & Future Improvements

### Current Limitations

1. **Language**: Only works with English-language reports (could add multi-language support)
2. **Statement Detection**: Assumes "Consolidated" statements (some companies only publish parent statements)
3. **Validation**: Basic checks only (could add more sophisticated validation)
4. **Rate Limits**: No rate limiting on OpenAI API calls

### Potential Enhancements

1. **OCR Support**: Handle scanned PDFs (currently requires native text)
2. **Segment Reporting**: Extract segment/geographic breakdowns
3. **Notes Extraction**: Parse footnotes and accounting policies
4. **Comparative Analysis**: Auto-generate year-over-year variance reports
5. **Web Interface**: Build dashboard for browsing extracted data

## Dependencies

```
openai              # GPT-4o API
python-dotenv       # Environment variable management
requests            # HTTP requests for downloads
beautifulsoup4      # HTML parsing for scraping
PyMuPDF             # PDF manipulation
pandas              # Data processing
selenium            # JavaScript-rendered page handling
```

## Testing

The project was tested on:
- **Lindt & Sprüngli** (LISP): Swiss chocolate manufacturer with JavaScript-heavy IR site
- **Novo Nordisk** (NVO): Danish pharmaceutical with standard HTML IR site

Both successfully extracted 10 years of data with high accuracy.

## License

MIT

## Contact

Martin Leung - martin.h.leung@hotmail.com
```

This README:
1. ✅ Explains how to set up `.env`
2. ✅ Clear usage instructions
3. ✅ Detailed approach/design decisions section
4. ✅ Professional structure suitable for a take-home submission
5. ✅ Includes technical rationale for key decisions
6. ✅ Acknowledges limitations (shows thoughtfulness)