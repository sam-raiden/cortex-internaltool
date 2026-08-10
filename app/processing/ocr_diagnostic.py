import sys
import subprocess
import pytesseract

def run_diagnostic():
    pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
    
    tess_installed = "NO"
    tam_installed = "NO"
    eng_installed = "NO"
    
    try:
        ver = pytesseract.get_tesseract_version()
        if ver:
            tess_installed = "YES"
            
        langs = pytesseract.get_languages(config="")
        if "tam" in langs:
            tam_installed = "YES"
        if "eng" in langs:
            eng_installed = "YES"
    except Exception as e:
        print(f"Error accessing Tesseract: {e}")
        
    print(f"Tesseract installed: {tess_installed}")
    print(f"Tamil language pack: {tam_installed}")
    print(f"English language pack: {eng_installed}")
    print("OCR provider: Tesseract")

if __name__ == "__main__":
    run_diagnostic()
