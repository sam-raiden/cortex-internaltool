import os

schema_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'models', 'schema.py'))

with open(schema_path, "r", encoding="utf-8") as f:
    text = f.read()

# Fix references in CollectionPageResult, CollectionError, TrendRepresentative
text = text.replace("ForeignKey('instagram_pages.id')", "ForeignKey('sources.id')")
text = text.replace("ForeignKey('instagram_posts.id')", "ForeignKey('raw_contents.id')")

with open(schema_path, "w", encoding="utf-8") as f:
    f.write(text)

print("Foreign Key bindings restored safely!")
