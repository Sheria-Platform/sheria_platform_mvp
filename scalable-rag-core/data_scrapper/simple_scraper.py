"""
Enhanced Kenya Law Scraper
- Searches multiple dictionary terms
- Stores clean metadata in PostgreSQL
- Downloads PDFs immediately after each search page
- Organizes PDFs in structured folders
- Handles duplicates and data normalization

Requirements:
pip install curl-cffi rich beautifulsoup4 psycopg2-binary
"""

import json
import os
import time
import re
from urllib.parse import urljoin
from datetime import datetime
from typing import Optional, Dict, List
import hashlib

from curl_cffi import requests
from bs4 import BeautifulSoup
from rich import print as rprint
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn
import psycopg2
from psycopg2.extras import execute_values

from english_words import get_english_words_set

# ==================== CONFIGURATION ====================
DB_CONFIG = {
    "host": "192.168.214.21",
    "database": "rag_db",
    "user": "ragadmin",
    "password": "changeme",
    "port": 5432
}

PDF_BASE_FOLDER = "kenya_law_data"
MAX_PAGES_PER_SEARCH = 10
DELAY_BETWEEN_PAGES = 2
DELAY_BETWEEN_PDFS = 5

# Search terms - you can load this from a file or define here
SEARCH_TERMS = get_english_words_set(['web2'], lower=True, alpha=True)

# ==================== DATABASE SETUP ====================
def init_database():
    """Create PostgreSQL tables for storing case metadata and PDFs"""
    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor()
    
    # Main cases table
    cur.execute("""
    CREATE TABLE IF NOT EXISTS cases (
        id SERIAL PRIMARY KEY,
        doc_id INTEGER UNIQUE NOT NULL,
        title TEXT NOT NULL,
        expression_frbr_uri TEXT UNIQUE NOT NULL,
        case_url TEXT NOT NULL,
        date DATE,
        year INTEGER,
        court TEXT,
        nature TEXT,
        registry TEXT,
        locality TEXT,
        outcome TEXT,
        language TEXT,
        matter_type TEXT,
        citation TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)
    
    # Judges table (many-to-many with cases)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS judges (
        id SERIAL PRIMARY KEY,
        name TEXT UNIQUE NOT NULL
    )
    """)
    
    cur.execute("""
    CREATE TABLE IF NOT EXISTS case_judges (
        case_id INTEGER REFERENCES cases(id) ON DELETE CASCADE,
        judge_id INTEGER REFERENCES judges(id) ON DELETE CASCADE,
        PRIMARY KEY (case_id, judge_id)
    )
    """)
    
    # Search terms tracking
    cur.execute("""
    CREATE TABLE IF NOT EXISTS search_terms (
        id SERIAL PRIMARY KEY,
        term TEXT UNIQUE NOT NULL,
        last_searched TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)
    
    cur.execute("""
    CREATE TABLE IF NOT EXISTS case_search_terms (
        case_id INTEGER REFERENCES cases(id) ON DELETE CASCADE,
        search_term_id INTEGER REFERENCES search_terms(id) ON DELETE CASCADE,
        PRIMARY KEY (case_id, search_term_id)
    )
    """)
    
    # PDFs table
    cur.execute("""
    CREATE TABLE IF NOT EXISTS case_pdfs (
        id SERIAL PRIMARY KEY,
        case_id INTEGER REFERENCES cases(id) ON DELETE CASCADE,
        pdf_url TEXT,
        pdf_path TEXT,
        pdf_hash TEXT,
        file_size BIGINT,
        downloaded_at TIMESTAMP,
        download_status TEXT DEFAULT 'pending',
        error_message TEXT
    )
    """)
    
    # Create indexes
    cur.execute("CREATE INDEX IF NOT EXISTS idx_cases_doc_id ON cases(doc_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_cases_year ON cases(year)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_cases_court ON cases(court)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_pdfs_status ON case_pdfs(download_status)")
    
    conn.commit()
    cur.close()
    conn.close()
    
    rprint("[bold green]✓ Database initialized successfully[/bold green]")

# ==================== DATA CLEANING ====================
def clean_text(text: Optional[str]) -> Optional[str]:
    """Clean and normalize text data"""
    if not text:
        return None
    text = re.sub(r'\s+', ' ', text)
    return text.strip()

def parse_date(date_str: Optional[str]) -> Optional[datetime]:
    """Parse date from various formats"""
    if not date_str:
        return None
    
    date_patterns = [
        r'(\d{4})-(\d{2})-(\d{2})',
        r'(\d{2})/(\d{2})/(\d{4})',
    ]
    
    for pattern in date_patterns:
        match = re.search(pattern, date_str)
        if match:
            try:
                if len(match.group(1)) == 4:  # YYYY-MM-DD
                    return datetime.strptime(date_str[:10], '%Y-%m-%d')
                else:  # DD/MM/YYYY
                    return datetime.strptime(date_str, '%d/%m/%Y')
            except ValueError:
                continue
    return None

def extract_year(date_str: Optional[str], expression_uri: Optional[str]) -> Optional[int]:
    """Extract year from date or expression URI"""
    if date_str:
        date = parse_date(date_str)
        if date:
            return date.year
    
    if expression_uri:
        year_match = re.search(r'/(\d{4})/', expression_uri)
        if year_match:
            return int(year_match.group(1))
    
    return None

def normalize_case_data(doc: Dict) -> Dict:
    """Clean and normalize case metadata"""
    return {
        'doc_id': doc.get('id'),
        'title': clean_text(doc.get('title')),
        'expression_frbr_uri': doc.get('expression_frbr_uri'),
        'date': parse_date(doc.get('date')),
        'year': extract_year(doc.get('date'), doc.get('expression_frbr_uri')),
        'court': clean_text(doc.get('court')),
        'nature': clean_text(doc.get('nature')),
        'registry': clean_text(doc.get('registry')),
        'locality': clean_text(doc.get('locality')),
        'outcome': clean_text(doc.get('outcome')),
        'language': clean_text(doc.get('language')),
        'matter_type': clean_text(doc.get('matter_type')),
        'citation': clean_text(doc.get('citation')),
        'judges': [clean_text(j) for j in doc.get('judges', []) if j],
    }

# ==================== SCRAPING FUNCTIONS ====================
def search_cases(session: requests.Session, search_term: str, page: int = 1) -> Dict:
    """Search for cases using a specific term"""
    url = "https://new.kenyalaw.org/search/api/documents/"
    params = {
        "search": search_term,
        "page": page,
        "ordering": "-score",
        "facet": [
            "nature", "court", "year", "registry", "locality", "outcome",
            "judges", "authors", "language", "labels", "attorneys", "matter_type"
        ]
    }
    response = session.get(url, params=params, timeout=30)
    response.raise_for_status()
    return response.json()

def extract_pdf_url(html: str, base_url: str) -> Optional[str]:
    """Extract PDF download URL from case page"""
    soup = BeautifulSoup(html, "html.parser")
    
    # Look for Download button or link
    pdf_link = soup.find("a", string=re.compile(r"Download|PDF", re.I))
    if pdf_link and pdf_link.get("href"):
        return urljoin(base_url, pdf_link["href"])
    
    download_btn = soup.find("button", attrs={"data-action": "download"})
    if download_btn and download_btn.get("data-url"):
        return urljoin(base_url, download_btn["data-url"])
    
    possible = soup.find("a", href=re.compile(r"\.pdf$", re.I))
    if possible:
        return urljoin(base_url, possible["href"])
    
    return None

def calculate_file_hash(filepath: str) -> str:
    """Calculate SHA256 hash of a file"""
    sha256_hash = hashlib.sha256()
    with open(filepath, "rb") as f:
        for byte_block in iter(lambda: f.read(4096), b""):
            sha256_hash.update(byte_block)
    return sha256_hash.hexdigest()

# ==================== DATABASE OPERATIONS ====================
def insert_search_term(conn, term: str) -> int:
    """Insert or get search term ID"""
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO search_terms (term, last_searched) 
        VALUES (%s, CURRENT_TIMESTAMP)
        ON CONFLICT (term) DO UPDATE SET last_searched = CURRENT_TIMESTAMP
        RETURNING id
    """, (term,))
    term_id = cur.fetchone()[0]
    conn.commit()
    cur.close()
    return term_id

def insert_case(conn, case_data: Dict, search_term_id: int) -> Optional[int]:
    """Insert case into database and return case_id"""
    cur = conn.cursor()
    
    try:
        case_url = f"https://new.kenyalaw.org{case_data['expression_frbr_uri']}"
        
        cur.execute("""
            INSERT INTO cases (
                doc_id, title, expression_frbr_uri, case_url, date, year,
                court, nature, registry, locality, outcome, language, matter_type, citation
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
            )
            ON CONFLICT (doc_id) DO UPDATE SET
                title = EXCLUDED.title,
                updated_at = CURRENT_TIMESTAMP
            RETURNING id
        """, (
            case_data['doc_id'], case_data['title'], case_data['expression_frbr_uri'],
            case_url, case_data['date'], case_data['year'], case_data['court'],
            case_data['nature'], case_data['registry'], case_data['locality'],
            case_data['outcome'], case_data['language'], case_data['matter_type'],
            case_data['citation']
        ))
        
        case_id = cur.fetchone()[0]
        
        # Link to search term
        cur.execute("""
            INSERT INTO case_search_terms (case_id, search_term_id)
            VALUES (%s, %s)
            ON CONFLICT DO NOTHING
        """, (case_id, search_term_id))
        
        # Insert judges
        for judge_name in case_data['judges']:
            if judge_name:
                cur.execute("""
                    INSERT INTO judges (name) VALUES (%s)
                    ON CONFLICT (name) DO NOTHING
                    RETURNING id
                """, (judge_name,))
                
                result = cur.fetchone()
                if result:
                    judge_id = result[0]
                else:
                    cur.execute("SELECT id FROM judges WHERE name = %s", (judge_name,))
                    judge_id = cur.fetchone()[0]
                
                cur.execute("""
                    INSERT INTO case_judges (case_id, judge_id)
                    VALUES (%s, %s)
                    ON CONFLICT DO NOTHING
                """, (case_id, judge_id))
        
        conn.commit()
        return case_id
        
    except Exception as e:
        conn.rollback()
        rprint(f"[red]Error inserting case: {e}[/red]")
        return None
    finally:
        cur.close()

def update_pdf_record(conn, case_id: int, pdf_data: Dict):
    """Update or insert PDF download record"""
    cur = conn.cursor()
    
    cur.execute("""
        INSERT INTO case_pdfs (
            case_id, pdf_url, pdf_path, pdf_hash, file_size, 
            downloaded_at, download_status, error_message
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (case_id) DO UPDATE SET
            pdf_url = EXCLUDED.pdf_url,
            pdf_path = EXCLUDED.pdf_path,
            pdf_hash = EXCLUDED.pdf_hash,
            file_size = EXCLUDED.file_size,
            downloaded_at = EXCLUDED.downloaded_at,
            download_status = EXCLUDED.download_status,
            error_message = EXCLUDED.error_message
    """, (
        case_id, pdf_data.get('pdf_url'), pdf_data.get('pdf_path'),
        pdf_data.get('pdf_hash'), pdf_data.get('file_size'),
        pdf_data.get('downloaded_at'), pdf_data['download_status'],
        pdf_data.get('error_message')
    ))
    
    conn.commit()
    cur.close()

def check_pdf_exists(conn, case_id: int) -> bool:
    """Check if PDF already downloaded for this case"""
    cur = conn.cursor()
    cur.execute("""
        SELECT download_status FROM case_pdfs 
        WHERE case_id = %s AND download_status = 'success'
    """, (case_id,))
    result = cur.fetchone()
    cur.close()
    return result is not None

# ==================== PDF DOWNLOAD FUNCTION ====================
def download_single_pdf(session: requests.Session, conn, case_id: int, 
                       doc_id: int, title: str, expression_uri: str, 
                       year: Optional[int]) -> bool:
    """Download PDF for a single case"""
    
    # Check if already downloaded
    if check_pdf_exists(conn, case_id):
        rprint(f"[cyan]  ✓ PDF already downloaded for case {doc_id}[/cyan]")
        return True
    
    # Prepare file paths
    title_clean = title[:80].replace("/", "_").replace("\\", "_")
    year_folder = str(year) if year else "unknown"
    pdf_folder = os.path.join(PDF_BASE_FOLDER, year_folder)
    os.makedirs(pdf_folder, exist_ok=True)
    
    pdf_filename = f"{doc_id}_{title_clean}.pdf"
    pdf_path = os.path.join(pdf_folder, pdf_filename)
    
    # Skip if file already exists on disk
    if os.path.exists(pdf_path):
        # Update database record
        pdf_hash = calculate_file_hash(pdf_path)
        file_size = os.path.getsize(pdf_path)
        update_pdf_record(conn, case_id, {
            'pdf_path': pdf_path,
            'pdf_hash': pdf_hash,
            'file_size': file_size,
            'downloaded_at': datetime.now(),
            'download_status': 'success'
        })
        rprint(f"[cyan]  ✓ PDF exists on disk: {pdf_filename}[/cyan]")
        return True
    
    case_url = f"https://new.kenyalaw.org{expression_uri}"
    
    try:
        # Fetch case page
        rprint(f"[yellow]  ⬇️  Downloading PDF: {title_clean[:50]}...[/yellow]")
        page_resp = session.get(case_url, timeout=30)
        page_resp.raise_for_status()
        
        # Extract PDF URL
        pdf_url = extract_pdf_url(page_resp.text, case_url)
        if not pdf_url:
            rprint(f"[red]  ✗ No PDF link found for case {doc_id}[/red]")
            update_pdf_record(conn, case_id, {
                'download_status': 'failed',
                'error_message': 'PDF link not found on page'
            })
            return False
        
        # Download PDF
        pdf_resp = session.get(pdf_url, timeout=60)
        pdf_resp.raise_for_status()
        
        # Save PDF
        with open(pdf_path, "wb") as f:
            f.write(pdf_resp.content)
        
        # Calculate hash and file size
        pdf_hash = calculate_file_hash(pdf_path)
        file_size = os.path.getsize(pdf_path)
        
        # Update database
        update_pdf_record(conn, case_id, {
            'pdf_url': pdf_url,
            'pdf_path': pdf_path,
            'pdf_hash': pdf_hash,
            'file_size': file_size,
            'downloaded_at': datetime.now(),
            'download_status': 'success'
        })
        
        rprint(f"[bold green]  ✓ Downloaded: {pdf_filename} ({file_size/1024:.1f} KB)[/bold green]")
        return True
        
    except Exception as e:
        rprint(f"[red]  ✗ Error downloading PDF for case {doc_id}: {e}[/red]")
        update_pdf_record(conn, case_id, {
            'download_status': 'failed',
            'error_message': str(e)[:500]
        })
        return False

# ==================== MAIN WORKFLOW ====================
def scrape_and_download(conn):
    """Scrape metadata and download PDFs page by page"""
    session = requests.Session(impersonate="chrome124")
    
    overall_stats = {
        'total_cases': 0,
        'new_cases': 0,
        'pdfs_downloaded': 0,
        'pdfs_failed': 0,
        'pdfs_skipped': 0
    }
    
    for search_term in SEARCH_TERMS:
        rprint(f"\n[bold cyan]{'='*60}[/bold cyan]")
        rprint(f"[bold cyan]Search Term: '{search_term}'[/bold cyan]")
        rprint(f"[bold cyan]{'='*60}[/bold cyan]")
        
        search_term_id = insert_search_term(conn, search_term)
        term_stats = {'cases': 0, 'pdfs': 0}
        
        for page in range(1, MAX_PAGES_PER_SEARCH + 1):
            try:
                rprint(f"\n[bold yellow]📄 Page {page}/{MAX_PAGES_PER_SEARCH}[/bold yellow]")
                
                # Fetch search results
                data = search_cases(session, search_term, page)
                results = data.get("results", [])
                
                if not results:
                    rprint(f"[yellow]  No more results for '{search_term}'[/yellow]")
                    break
                
                rprint(f"[green]  Found {len(results)} cases on this page[/green]")
                
                # Process each case on this page
                for idx, doc in enumerate(results, 1):
                    rprint(f"\n[bold blue]  Case {idx}/{len(results)}:[/bold blue]")
                    
                    # Normalize and insert case metadata
                    case_data = normalize_case_data(doc)
                    case_id = insert_case(conn, case_data, search_term_id)
                    
                    if not case_id:
                        rprint(f"[red]  ✗ Failed to insert case metadata[/red]")
                        continue
                    
                    overall_stats['total_cases'] += 1
                    term_stats['cases'] += 1
                    
                    rprint(f"[green]  ✓ Metadata saved: ID={case_data['doc_id']}, Title={case_data['title'][:50]}[/green]")
                    
                    # Download PDF immediately
                    success = download_single_pdf(
                        session, conn,
                        case_id=case_id,
                        doc_id=case_data['doc_id'],
                        title=case_data['title'],
                        expression_uri=case_data['expression_frbr_uri'],
                        year=case_data['year']
                    )
                    
                    if success:
                        if check_pdf_exists(conn, case_id):
                            overall_stats['pdfs_downloaded'] += 1
                            term_stats['pdfs'] += 1
                        else:
                            overall_stats['pdfs_skipped'] += 1
                    else:
                        overall_stats['pdfs_failed'] += 1
                    
                    # Small delay between PDFs
                    time.sleep(DELAY_BETWEEN_PDFS)
                
                rprint(f"\n[bold green]✓ Page {page} complete: {len(results)} cases processed[/bold green]")
                
                # Delay before next page
                time.sleep(DELAY_BETWEEN_PAGES)
                
            except Exception as e:
                rprint(f"[red]✗ Error on page {page}: {e}[/red]")
                continue
        
        rprint(f"\n[bold magenta]Search term '{search_term}' complete:[/bold magenta]")
        rprint(f"[magenta]  Cases: {term_stats['cases']}, PDFs: {term_stats['pdfs']}[/magenta]")
    
    # Final summary
    rprint(f"\n[bold blue]{'='*60}[/bold blue]")
    rprint(f"[bold blue]SCRAPING COMPLETE - SUMMARY[/bold blue]")
    rprint(f"[bold blue]{'='*60}[/bold blue]")
    rprint(f"[cyan]Total cases processed: {overall_stats['total_cases']}[/cyan]")
    rprint(f"[green]✓ PDFs downloaded: {overall_stats['pdfs_downloaded']}[/green]")
    rprint(f"[yellow]○ PDFs skipped: {overall_stats['pdfs_skipped']}[/yellow]")
    rprint(f"[red]✗ PDFs failed: {overall_stats['pdfs_failed']}[/red]")

def main():
    """Main execution flow"""
    rprint("[bold blue]" + "="*60 + "[/bold blue]")
    rprint("[bold blue]Kenya Law Scraper - Enhanced Version[/bold blue]")
    rprint("[bold blue]Downloads PDFs immediately after each search page[/bold blue]")
    rprint("[bold blue]" + "="*60 + "[/bold blue]\n")
    
    # Initialize database
    rprint("[yellow]Initializing database...[/yellow]")
    init_database()
    
    # Connect to database
    conn = psycopg2.connect(**DB_CONFIG)
    
    try:
        # Scrape and download in one workflow
        scrape_and_download(conn)
        
        rprint("\n[bold green]✓ All operations complete![/bold green]")
        
    except KeyboardInterrupt:
        rprint("\n[yellow]⚠️  Scraping interrupted by user[/yellow]")
        rprint("[cyan]Progress has been saved. You can resume by running the script again.[/cyan]")
    except Exception as e:
        rprint(f"\n[red]✗ Fatal error: {e}[/red]")
    finally:
        conn.close()
        rprint("\n[blue]Database connection closed.[/blue]")

if __name__ == "__main__":
    main()