import os
import json
from sqlalchemy.orm import Session
from app.storage.database import SessionLocal
from app.models.schema import InstagramPage

def sync_and_audit():
    config_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "config", "pages.json"))
    with open(config_path, "r", encoding="utf-8") as f:
        pages_config = json.load(f)
        
    db = SessionLocal()
    
    medical_target = 25
    general_target = 75
    
    # Sync config to DB
    for cfg in pages_config:
        username = cfg.get("username")
        page = db.query(InstagramPage).filter_by(username=username).first()
        if page:
            page.vertical = cfg.get("vertical", "GENERAL")
            page.priority = cfg.get("priority", 1)
            page.active = cfg.get("active", True)
        else:
            page = InstagramPage(
                username=username,
                profile_url=cfg.get("url"),
                vertical=cfg.get("vertical", "GENERAL"),
                priority=cfg.get("priority", 1),
                active=cfg.get("active", True)
            )
            db.add(page)
    db.commit()
    
    # Audit DB allocation
    all_pages = db.query(InstagramPage).all()
    configured = len(all_pages)
    active = sum(1 for p in all_pages if p.active)
    medical = sum(1 for p in all_pages if p.vertical == "MEDICAL")
    general = sum(1 for p in all_pages if p.vertical == "GENERAL")
    
    db.close()
    
    print("========================================")
    print("MEDICAL SOURCE AUDIT")
    print("========================================")
    print("Instagram")
    print(f"  configured: {configured}")
    print(f"  active: {active}")
    print(f"  medical: {medical}")
    print(f"  general: {general}")
    
    allocation_status = "PASS" if (medical == medical_target and general == general_target) else "NOT_READY"
    print(f"  allocation: {allocation_status}")
    if allocation_status == "NOT_READY":
        print(f"    STATUS: NOT_READY")
        if medical < medical_target:
            print(f"    medical: {medical} (required: {medical_target})")
        if general < general_target:
            print(f"    general: {general} (required: {general_target})")
            
    # Output STAGE_10_5_SOURCE_AUDIT.json
    out_dict = {
      "stage": "10.5",
      "status": "PARTIAL" if allocation_status == "NOT_READY" else "PASS",
      "platforms": {
        "instagram": {
          "configured": configured,
          "active": active,
          "medical": medical,
          "general": general,
          "medical_target": medical_target,
          "general_target": general_target,
          "allocation_status": allocation_status
        },
        "youtube": {
          "status": "NOT_COLLECTED"
        },
        "rss": {
          "status": "NOT_COLLECTED"
        }
      },
      "verticals": [
        "GENERAL",
        "MEDICAL"
      ]
    }
    
    out_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "output"))
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "STAGE_10_5_SOURCE_AUDIT.json"), "w", encoding="utf-8") as f:
        json.dump(out_dict, f, indent=2)

if __name__ == "__main__":
    sync_and_audit()
