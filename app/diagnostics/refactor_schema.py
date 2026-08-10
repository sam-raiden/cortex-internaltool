import os
import re

schema_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'models', 'schema.py'))

with open(schema_path, "r", encoding="utf-8") as f:
    text = f.read()

# Make imports correct
text = text.replace(
    'from sqlalchemy.orm import relationship',
    'from sqlalchemy.orm import relationship, synonym'
)

# Refactor InstagramPage -> Source
text = text.replace("class InstagramPage(Base):", "class Source(Base):")
text = text.replace("__tablename__ = 'instagram_pages'", "__tablename__ = 'sources'")

text = text.replace("username = Column(String(255), unique=True, nullable=False, index=True)",
                    "external_id = Column(String(255), unique=True, nullable=False, index=True)\n    username = synonym('external_id')\n    platform = Column(String(50), default='instagram', index=True)\n    source_type = Column(String(50))\n    status = Column(String(50), default='ACTIVE')")
text = text.replace("profile_url = Column(String(512), nullable=False)",
                    "url = Column(String(512), nullable=False)\n    profile_url = synonym('url')")
text = text.replace("active = Column(Boolean, default=True, index=True)",
                    "enabled = Column(Boolean, default=True, index=True)\n    active = synonym('enabled')")

text = text.replace('posts = relationship("InstagramPost", back_populates="page")',
                    'raw_contents = relationship("RawContent", back_populates="source")\n    posts = synonym("raw_contents")')

# Refactor InstagramPost -> RawContent
text = text.replace("class InstagramPost(Base):", "class RawContent(Base):")
text = text.replace("__tablename__ = 'instagram_posts'", "__tablename__ = 'raw_contents'")
text = text.replace("ForeignKey('instagram_pages.id')", "ForeignKey('sources.id')")
text = text.replace("page_id = Column(", "source_id = Column(")
text = text.replace("instagram_post_id = Column(String(100), unique=True, nullable=False, index=True)",
                    "external_content_id = Column(String(100), unique=True, nullable=False, index=True)\n    instagram_post_id = synonym('external_content_id')\n    platform = Column(String(50), default='instagram')\n    vertical = Column(String(50), default='GENERAL')\n    content_type = Column(String(50))\n    title = Column(String(512))\n    raw_payload = Column(JSON)")
text = text.replace("post_url = Column(String(512), nullable=False)",
                    "url = Column(String(512), nullable=False)\n    post_url = synonym('url')")
text = text.replace("caption = Column(Text)",
                    "text = Column(Text)\n    caption = synonym('text')")
text = text.replace('page = relationship("InstagramPage", back_populates="posts")',
                    'source = relationship("Source", back_populates="raw_contents")\n    page = synonym("source")')

# Fix references in other tables
text = text.replace("ForeignKey('instagram_posts.id')", "ForeignKey('raw_contents.id')")

# Fix backward compatibility aliases at the bottom
aliases = """

# Backwards compatibility aliases for Stage 1-10.5 logic
InstagramPage = Source
InstagramPost = RawContent
"""
text += aliases

with open(schema_path, "w", encoding="utf-8") as f:
    f.write(text)

print("Schema refactor written natively!")
