import os

schema_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'models', 'schema.py'))

with open(schema_path, "r", encoding="utf-8") as f:
    text = f.read()

# Fix the declarative registry names to point to the actual class names
text = text.replace('relationship("InstagramPage"', 'relationship("Source"')
text = text.replace('relationship("InstagramPost"', 'relationship("RawContent"')

with open(schema_path, "w", encoding="utf-8") as f:
    f.write(text)

print("Relationships rewired!")
