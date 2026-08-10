# Cortex Trends

This is the technical proof-of-concept for the Cortex Trends trend intelligence pipeline.
It is a backend-only pipeline designed to validate that real Instagram data can travel through the collection, extraction, and clustering processes for Tamil and Tanglish content.

## Architecture Pipeline
- **Collection**: Playwright-based Instagram public profile scraper.
- **Deduplication**: Identifier-based skip tracking.
- **Extraction**: paddleocr, faster-whisper, and normalization logic.
- **Embeddings**: Sentence-transformers (multilingual).
- **Clustering**: HDBSCAN

## Requirements
- Python 3.9+
- Docker (for PostgreSQL database)

## Running
1. Copy `.env.example` to `.env` and adjust variables if needed.
2. Start the database:
   ```bash
   docker compose up -d
   ```
3. Run migrations to create tables:
   ```bash
   alembic upgrade head
   ```
