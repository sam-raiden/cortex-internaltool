import json
import os
import sys

def run():
    config_path = os.path.join(os.path.dirname(__file__), "..", "..", "config", "pages.json")
    with open(config_path, "r", encoding="utf-8") as f:
        data = json.load(f)
        
    updated = 0
    medical_accounts = ["news7tamilhealth", "drchetanachetan"] # Examples of known health accounts
    
    for page in data:
        username = page.get("username", "").lower()
        if username in medical_accounts or "health" in username or "doctor" in username or "medi" in username:
            page["vertical"] = "MEDICAL"
        else:
            page["vertical"] = "GENERAL"
            
        page["priority"] = page.get("tier", 1)  # migrate tier up to priority as well
        
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
        
if __name__ == "__main__":
    run()
