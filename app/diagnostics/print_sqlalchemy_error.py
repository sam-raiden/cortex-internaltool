import traceback
try:
    from app.models.schema import *
    from sqlalchemy.orm import configure_mappers
    configure_mappers()
    print("SUCCESS MAILING")
except Exception as e:
    traceback.print_exc()
