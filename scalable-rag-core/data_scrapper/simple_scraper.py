# Enhanced Script: Scrape Top 100 "family" Cases + Download PDFs
# - Collects all available 100 documents via the search API
# - For each case, constructs the public case page URL using the FRBR URI
# - Example case page: https://new.kenyalaw.org/akn/ke/judgment/keelc/2020/981/eng@2020-10-19
# - On the case page, there is a "Download PDF" button linking to the full judgment PDF
# - We fetch the case page HTML, extract the PDF URL, and download the PDF
# - Saves PDFs in a folder named after the case ID (e.g., 551506_In_re_Family_Bank_Limited.pdf)
# - Polite scraping: 3-second delay between case page requests, 5-second between PDF downloads
# - Skips if PDF already exists (resume-friendly)

# pip install curl-cffi rich beautifulsoup4

import json
import os
import time
import re
from urllib.parse import urljoin

from curl_cffi import requests
from bs4 import BeautifulSoup
from rich import print as rprint

OUTPUT_JSON = "kenya_law_family_documents.json"
PDF_FOLDER = "kenya_law_family_pdfs"
MAX_PAGE = 10

os.makedirs(PDF_FOLDER, exist_ok=True)

def get_page(session: requests.Session, page: int = 1) -> dict:
    url = "https://new.kenyalaw.org/search/api/documents/"
    params = {
        "search": "family",
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

def extract_pdf_url(html: str, base_url: str) -> str | None:
    soup = BeautifulSoup(html, "html.parser")
    
    # Look for Download button or link containing "PDF" or "download"
    pdf_link = soup.find("a", string=re.compile(r"Download|PDF", re.I))
    if pdf_link and pdf_link.get("href"):
        return urljoin(base_url, pdf_link["href"])
    
    # Alternative: some pages have a button with data-url or onclick
    download_btn = soup.find("button", attrs={"data-action": "download"})
    if download_btn and download_btn.get("data-url"):
        return urljoin(base_url, download_btn["data-url"])
    
    # Fallback: common pattern observed on kenyalaw.org
    possible = soup.find("a", href=re.compile(r"\.pdf$", re.I))
    if possible:
        return urljoin(base_url, possible["href"])
    
    return None

def main():
    session = requests.Session(impersonate="chrome124")
    
    # Load or scrape metadata
    if os.path.exists(OUTPUT_JSON):
        rprint(f"[yellow]Loading existing metadata from {OUTPUT_JSON}...[/yellow]")
        with open(OUTPUT_JSON, "r", encoding="utf-8") as f:
            all_documents = json.load(f)
    else:
        all_documents = []
        rprint("[bold cyan]Scraping metadata (top 100 cases)...[/bold cyan]")
        for page in range(1, MAX_PAGE + 1):
            rprint(f"[yellow]Fetching metadata page {page}/{MAX_PAGE}...[/yellow]")
            data = get_page(session, page)
            results = data.get("results", [])
            all_documents.extend(results)
            rprint(f"[green]✓ Page {page}: +{len(results)} cases (total: {len(all_documents)})[/green]")
            time.sleep(2)
        
        with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
            json.dump(all_documents, f, indent=4, ensure_ascii=False)
        rprint(f"[bold green]Metadata saved to {OUTPUT_JSON}[/bold green]")
    
    rprint(f"[bold magenta]Starting PDF downloads for {len(all_documents)} cases...[/bold magenta]")
    
    downloaded = 0
    skipped = 0
    failed = 0
    
    for doc in all_documents:
        doc_id = doc.get("id")
        title = doc.get("title", "unknown_case").replace("/", "_")[:100]  # Safe filename
        expression_uri = doc.get("expression_frbr_uri")  # e.g., "/akn/ke/judgment/keelc/2020/981/eng@2020-10-19"
        
        if not expression_uri:
            rprint(f"[red]No expression_frbr_uri for ID {doc_id} – skipping[/red]")
            failed += 1
            continue
        
        case_url = "https://new.kenyalaw.org" + expression_uri
        pdf_filename = f"{doc_id}_{title}.pdf"
        pdf_path = os.path.join(PDF_FOLDER, pdf_filename)
        
        if os.path.exists(pdf_path):
            rprint(f"[cyan]Already exists: {pdf_filename}[/cyan]")
            skipped += 1
            continue
        
        try:
            rprint(f"[yellow]Fetching case page: {case_url}[/yellow]")
            page_resp = session.get(case_url, timeout=30)
            page_resp.raise_for_status()
            
            pdf_url = extract_pdf_url(page_resp.text, case_url)
            if not pdf_url:
                rprint(f"[red]No PDF link found for ID {doc_id} ({title})[/red]")
                failed += 1
                time.sleep(3)
                continue
            
            rprint(f"[green]Downloading PDF: {pdf_url}[/green]")
            pdf_resp = session.get(pdf_url, timeout=60)
            pdf_resp.raise_for_status()
            
            with open(pdf_path, "wb") as f:
                f.write(pdf_resp.content)
            
            rprint(f"[bold green]✓ Saved: {pdf_filename}[/bold green]")
            downloaded += 1
            
        except Exception as e:
            rprint(f"[red]Error downloading ID {doc_id}: {e}[/red]")
            failed += 1
        
        time.sleep(5)  # Be extra polite for PDF downloads
    
    rprint("[bold magenta]PDF Download Summary:[/bold magenta]")
    rprint(f"[green]Downloaded: {downloaded}[/green]")
    rprint(f"[cyan]Skipped (already exists): {skipped}[/cyan]")
    rprint(f"[red]Failed/No PDF: {failed}[/red]")
    rprint(f"[bold]PDFs saved in folder: {PDF_FOLDER}[/bold]")

if __name__ == "__main__":
    main()