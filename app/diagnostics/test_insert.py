import traceback
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from app.models.schema import Source, RawContent

try:
    engine = create_engine('postgresql://tamilsh:pocpassword@localhost:5433/tamilsh_poc_test')
    session = Session(engine)
    
    # Clean previous
    session.query(RawContent).delete()
    session.query(Source).delete()
    session.commit()
    
    # 1. Insert page
    page = Source(username="test_page_1", profile_url="htty://test.com", tier=1)
    session.add(page)
    session.commit()
    print("Page insert success")
    
    # 2. Insert post
    post = RawContent(
        page_id=page.id,
        instagram_post_id="post_ABC123",
        post_url="http://test.com/p/ABC123",
        caption="#Tamil trend testing"
    )
    session.add(post)
    session.commit()
    print("Post insert success")
    
    # 3. Read back
    fetched_page = session.query(Source).filter_by(username="test_page_1").first()
    print("Fetched page posts:", [p.instagram_post_id for p in fetched_page.posts])
except Exception as e:
    traceback.print_exc()
