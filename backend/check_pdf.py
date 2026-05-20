#!/usr/bin/env python3
# Check PDF file content

import PyPDF2
import re
import sys

def check_pdf_content(pdf_path: str):
    """Check PDF file content"""
    try:
        print(f"[INFO] Checking PDF file: {pdf_path}")
        
        # Open PDF
        with open(pdf_path, 'rb') as file:
            reader = PyPDF2.PdfReader(file)
            
            print(f"[INFO] File information:")
            print(f"  Pages: {len(reader.pages)}")
            print(f"  Version: {reader.metadata.get('/PDFVersion', 'Unknown')}")
            
            # Check first few pages content
            print("[INFO] First 3 pages content preview:")
            for i in range(min(3, len(reader.pages))):
                page = reader.pages[i]
                text = page.extract_text()
                
                print(f"\nPage {i+1} (length: {len(text)} characters):")
                print(f"Content: {text[:300]}...")
                
                # Check if contains Chinese characters
                chinese_chars = len(re.findall(r'[\u4e00-\u9fff]', text))
                print(f"Chinese characters: {chinese_chars}")
                
                # Check if contains English characters
                english_chars = len(re.findall(r'[a-zA-Z]', text))
                print(f"English characters: {english_chars}")
                
                # Check if empty
                if not text.strip():
                    print("[WARNING] Page content is empty or cannot be extracted")
                elif len(text.strip()) < 50:
                    print("[WARNING] Page content is very short")
                    
    except Exception as e:
        print(f"[ERROR] Error reading PDF: {e}")
        return False
    
    return True

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python check_pdf.py <pdf_file_path>")
        sys.exit(1)
    
    pdf_path = sys.argv[1]
    check_pdf_content(pdf_path)
