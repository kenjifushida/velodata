# Claude Code Reference Guide - VeloData

## Project Overview

VeloData is a high-frequency arbitrage SaaS platform built on a **monorepo architecture** with a polymorphic data model supporting multiple product niches (Pokemon Cards, Watches, Camera Gear, etc.).

### Tech Stack
- **Python**: 3.11+
- **Framework**: Pydantic v2 (data validation)
- **Database**: MongoDB (Atlas)
- **Web Scraping**: Playwright (browser automation)
- **Logging**: Structured JSON logging with rotation

---

## Project Structure

```
/velodata
  ├── core/                    # Shared libraries
  │   ├── models/
  │   │   └── product.py      # Polymorphic product models (CRITICAL)
  │   ├── database.py         # MongoDB singleton
  │   ├── config.py           # Environment configuration
  │   └── logging.py          # Production logging system
  ├── services/               # Independent services
  │   └── seeder/
  │       └── main.py         # Canonical products seeder (multi-niche)
  ├── logs/                   # Service-specific log files
  ├── tests/                  # Test suites
  │   └── test_product_models.py
  ├── docs/                   # Documentation
  │   ├── ARCHITECTURE.md     # System architecture
  │   └── LOGGING.md          # Logging guide
  ├── .env                    # Environment variables (NEVER COMMIT)
  ├── requirements.txt        # Python dependencies
  └── CLAUDE.md              # This file
```

---

## Core Architecture Concepts

### 1. Polymorphic Identity System (CRITICAL)

**Pattern**: Discriminated Unions via Pydantic v2

Each product niche has its own identity model with different fields:

```python
# Pokemon Cards
PokemonCardIdentity:
  - set_code: str
  - card_number: str
  - name_jp: str
  - rarity: str

# Watches
WatchIdentity:
  - brand: str
  - model: str
  - reference_number: str
  - serial_number: str | None
  - production_year: int | None

# Camera Gear
CameraGearIdentity:
  - brand: str
  - model_number: str
  - subcategory: Literal["CAMERA", "LENS", "VIDEO_CAMERA", ...]
  - condition: str | None
  - serial_number: str | None
```

**Key Files**:
- [core/models/product.py](core/models/product.py) - Contains ALL identity models and factory functions
- [tests/test_product_models.py](tests/test_product_models.py) - Comprehensive test suite

**Why This Matters**:
- Adding new niches requires ZERO changes to existing code
- Type-safe validation prevents data corruption
- Each niche has custom ID generation logic

### 2. Factory Pattern for Product Creation

Always use factory functions, never create products manually:

```python
from core.models.product import (
    create_pokemon_card_product,
    create_watch_product,
    create_camera_gear_product
)

# ✅ CORRECT
product = create_pokemon_card_product(
    set_code="sv2a",
    card_number="165",
    name_jp="ピカチュウex",
    rarity="RR",
    image_url="https://...",
    source_url="https://..."
)

# ❌ WRONG - Don't do this
product = CanonicalProduct(
    _id="manual-id",  # This bypasses ID generation logic!
    identity={"niche_type": "POKEMON_CARD", ...},  # Type-unsafe!
    metadata={...}
)
```

### 3. Type Guards for Safe Access

Use type guards before accessing niche-specific fields:

```python
from core.models.product import is_pokemon_card, is_watch, is_camera_gear

if is_pokemon_card(product):
    # Now safe to access Pokemon-specific fields
    print(f"Set: {product.identity.set_code}")
    print(f"Card: {product.identity.card_number}")

elif is_watch(product):
    # Now safe to access Watch-specific fields
    print(f"Brand: {product.identity.brand}")
    print(f"Model: {product.identity.model}")
```

---

## Working with Claude Code

### Running the Seeder Service

The seeder service is designed to scrape and seed canonical products across various niches. Currently, the main implementation focuses on Pokemon cards, but the architecture supports multiple niches.

```bash
# Activate virtual environment
source venv/bin/activate

# Run seeder (headed mode - shows browser)
python services/seeder/main.py --sets sv2a sv4a

# Run seeder (headless mode - no browser UI)
python services/seeder/main.py --sets sv2a sv4a --headless
```

**Current Implementation**: The seeder uses Playwright to scrape pokemon-card.com and seeds Pokemon card products into the `canonical_products` collection.

**Future Expansion**: The seeder will be extended to support multiple niches by:
1. Adding niche-specific scraping logic
2. Using appropriate factory functions based on niche type
3. Supporting multiple data sources per niche

### Running Tests

```bash
# Activate venv
source venv/bin/activate

# Run all tests
python tests/test_product_models.py

# Expected output: "SUMMARY: 7 passed, 0 failed"
```

### Checking Logs

```bash
# Tail the seeder logs
tail -f logs/seeder.log

# Search for errors
grep "ERROR" logs/seeder.log

# View JSON logs (pretty print)
tail logs/seeder.log | python -m json.tool
```

---

## Common Tasks with Claude Code

### Task 1: Add a New Product Niche (e.g., Sneakers)

**What to tell Claude**:
> "Add a new niche type for sneakers with fields: brand, model, colorway, size, sku. Include factory function and type guard."

**Expected Changes**:
1. New `SneakerIdentity` class in [core/models/product.py](core/models/product.py)
2. Update `ProductIdentity` union to include `SneakerIdentity`
3. Update `CanonicalProduct.niche_type` property return type
4. New `create_sneaker_product()` factory function
5. New `is_sneaker()` type guard
6. New test function in [tests/test_product_models.py](tests/test_product_models.py)

**Validation**:
```bash
python tests/test_product_models.py
# Should pass with N+1 tests
```

### Task 2: Add New Scraping Logic for a Niche

**What to tell Claude**:
> "Extend the seeder service to support scraping [niche] products from [website]. Use the [create_niche_product] factory function and maintain the same logging patterns."

**Architecture Options**:

**Option A: Extend Current Seeder** (for similar workflows)
```python
# Add niche-specific scraping function to services/seeder/main.py
@log_execution_time(logger)
def scrape_watches_from_source(query: str, headless: bool = True) -> List[Dict]:
    """Scrape watch products from source."""
    # Implementation...
    pass
```

**Option B: Create Separate Seeder Service** (for different workflows)
```
services/
  ├── seeder/
  │   └── main.py          # Original multi-niche seeder
  └── watch-seeder/
      └── main.py          # Specialized watch seeder
```

**Required Elements**:
- Import appropriate factory function (e.g., `create_watch_product`)
- Use `get_logger("seeder")` for logging consistency
- Use correlation IDs for tracing
- Use `@log_execution_time` decorator for timing
- Graceful error handling with logging
- Support for both headed and headless modes

### Task 3: Add New Fields to Existing Identity

**IMPORTANT**: This requires careful consideration!

**Safe Additions** (backward-compatible):
```python
# ✅ SAFE - Adding optional fields
class WatchIdentity(BaseModel):
    ...
    production_year: int | None  # Existing optional
    box_included: bool | None = None  # NEW optional field
    papers_included: bool | None = None  # NEW optional field
```

**Breaking Changes** (requires migration):
```python
# ❌ BREAKING - Adding required fields
class WatchIdentity(BaseModel):
    ...
    certification: str  # NEW required field - breaks existing data!
```

**What to tell Claude**:
> "Add optional fields [field1], [field2] to [NicheIdentity]. Ensure backward compatibility."

Then update tests and run:
```bash
python tests/test_product_models.py
```

### Task 4: Debug Scraping Issues

**What to tell Claude**:
> "The seeder is failing to extract [niche] data from [source]. Debug the CSS selectors and add fallbacks."

**Claude should**:
1. Read [services/seeder/main.py](services/seeder/main.py)
2. Check the relevant selector lists
3. Potentially run the scraper in headed mode to inspect the page
4. Add debug screenshots (`page.screenshot()`)
5. Check logs in `logs/seeder.log` for clues

**Helpful Commands**:
```bash
# Run in headed mode to see what's happening
python services/seeder/main.py --sets sv2a

# Check logs for selector matches
grep "Found.*cards" logs/seeder.log
grep "No.*elements found" logs/seeder.log
```

### Task 5: Query Canonical Products by Niche

**What to tell Claude**:
> "Show me how to query all [niche] products from the database and process them safely."

**Expected Response**:
```python
from core.database import get_db
from core.models.product import CanonicalProduct, is_pokemon_card, is_watch

db = get_db()
collection = db["canonical_products"]

# Query by niche type
results = collection.find({"identity.niche_type": "POKEMON_CARD"})

for doc in results:
    # Deserialize to CanonicalProduct
    product = CanonicalProduct(**doc)

    # Use type guard for safe access
    if is_pokemon_card(product):
        print(f"Card: {product.identity.set_code}-{product.identity.card_number}")
    elif is_watch(product):
        print(f"Watch: {product.identity.brand} {product.identity.model}")
```

---

## Key Architectural Rules

### ✅ DO

1. **Always use factory functions** for creating products
2. **Always use type guards** before accessing niche-specific fields
3. **Always use structured logging** with `extra={}` for context
4. **Always include correlation IDs** for multi-step operations
5. **Always add tests** when modifying [core/models/product.py](core/models/product.py)
6. **Always run tests** before committing changes
7. **Always use Pydantic validation** - let it catch errors early
8. **Always query by niche_type** when fetching specific products
9. **Always deserialize MongoDB docs** to CanonicalProduct before use

### ❌ DON'T

1. **Don't bypass factory functions** - they handle ID generation
2. **Don't add required fields** to existing identities (breaking change)
3. **Don't use `print()`** - use `logger.info()` instead
4. **Don't log sensitive data** (passwords, API keys, PII)
5. **Don't modify `_id` after creation** - it's immutable
6. **Don't mix niche types** - the discriminator prevents this
7. **Don't skip tests** - they're your safety net
8. **Don't hardcode niche logic** - use type guards and polymorphism

---

## Environment Setup

### First-Time Setup

```bash
# Clone repository (if not already done)
git clone <repo-url>
cd velodata

# Create Python 3.11 virtual environment
python3.11 -m venv venv

# Activate venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Install Playwright browsers
playwright install chromium

# Create .env file (see .env.example)
cp .env.example .env
# Edit .env with your MongoDB credentials
```

### Daily Development

```bash
# Always activate venv first
source venv/bin/activate

# Run tests before starting work
python tests/test_product_models.py

# Make changes...

# Run tests after changes
python tests/test_product_models.py

# Deactivate when done
deactivate
```

---

## MongoDB Schema

### Collection: `canonical_products`

The `canonical_products` collection stores all products across all niches using the polymorphic identity pattern.

**Example: Pokemon Card**
```json
{
  "_id": "sv2a-165",
  "identity": {
    "niche_type": "POKEMON_CARD",
    "set_code": "sv2a",
    "card_number": "165",
    "name_jp": "ピカチュウex",
    "rarity": "RR"
  },
  "metadata": {
    "image_url": "https://...",
    "source_url": "https://..."
  }
}
```

**Example: Watch**
```json
{
  "_id": "rolex-ABC123XYZ",
  "identity": {
    "niche_type": "WATCH",
    "brand": "Rolex",
    "model": "Submariner",
    "reference_number": "126610LN",
    "serial_number": "ABC123XYZ",
    "production_year": 2023
  },
  "metadata": {
    "image_url": "https://...",
    "source_url": "https://..."
  }
}
```

**Example: Camera Gear**
```json
{
  "_id": "canon-camera-eos-r5",
  "identity": {
    "niche_type": "CAMERA_GEAR",
    "brand": "Canon",
    "model_number": "EOS R5",
    "subcategory": "CAMERA",
    "condition": "New",
    "serial_number": null
  },
  "metadata": {
    "image_url": "https://...",
    "source_url": "https://..."
  }
}
```

### Indexes

```javascript
// Recommended indexes for canonical_products collection
db.canonical_products.createIndex({ "_id": 1 })
db.canonical_products.createIndex({ "identity.niche_type": 1 })
db.canonical_products.createIndex({ "identity.set_code": 1 })  // Pokemon cards
db.canonical_products.createIndex({ "identity.brand": 1 })     // Watches, Camera Gear
db.canonical_products.createIndex({ "identity.subcategory": 1 })  // Camera Gear
```

### Querying by Niche Type

```python
# Get all Pokemon cards
pokemon_cards = collection.find({"identity.niche_type": "POKEMON_CARD"})

# Get all watches from Rolex
rolex_watches = collection.find({
    "identity.niche_type": "WATCH",
    "identity.brand": "Rolex"
})

# Get all camera lenses
lenses = collection.find({
    "identity.niche_type": "CAMERA_GEAR",
    "identity.subcategory": "LENS"
})
```

---

## Logging Architecture

### Log Levels

| Level    | When to Use                     | Example                          |
|----------|---------------------------------|----------------------------------|
| DEBUG    | Detailed diagnostic info        | "Entering function with params" |
| INFO     | General informational messages  | "Seeder session started"        |
| WARNING  | Non-critical issues             | "Slow query detected"           |
| ERROR    | Recoverable errors              | "Failed to parse card data"     |
| CRITICAL | System-level failures           | "Database connection lost"      |

### Structured Logging Example

```python
from core.logging import get_logger, log_execution_time
import uuid

logger = get_logger("seeder")

# Basic logging
logger.info("Seeder service started")

# Structured logging with context
correlation_id = str(uuid.uuid4())[:8]
logger.info(
    "Processing niche",
    extra={
        "correlation_id": correlation_id,
        "niche_type": "POKEMON_CARD",
        "source": "pokemon-card.com"
    }
)

# Error logging with stack trace
try:
    process_data()
except Exception as e:
    logger.error(
        "Processing failed",
        exc_info=True,  # Includes full stack trace
        extra={
            "correlation_id": correlation_id,
            "niche_type": niche_type
        }
    )

# Function timing decorator
@log_execution_time(logger)
def scrape_products(source: str) -> List[Dict]:
    # Automatically logs execution time
    pass
```

---

## Testing Strategy

### Test Coverage

Current test suite ([tests/test_product_models.py](tests/test_product_models.py)):

1. ✅ `test_pokemon_card_creation` - Factory function test
2. ✅ `test_watch_creation` - Watch product test
3. ✅ `test_camera_gear_creation` - Camera gear test (camera + lens)
4. ✅ `test_manual_pokemon_card` - Manual creation test
5. ✅ `test_wrong_niche_type_validation` - Validation error test
6. ✅ `test_serialization` - MongoDB round-trip test
7. ✅ `test_type_guards` - Type guard function test

### Adding New Tests for New Niches

When adding a new niche, add a corresponding test:

```python
def test_new_niche_creation():
    """Test new niche product creation with factory function."""
    print("\n=== Test N: New Niche Creation ===")

    product = create_new_niche_product(
        field1="value1",
        field2="value2",
        image_url="https://...",
        source_url="https://..."
    )

    # Assertions
    assert product.id == "expected-id-format"
    assert product.niche_type == "NEW_NICHE"
    assert isinstance(product.identity, NewNicheIdentity)
    assert is_new_niche(product), "Type guard should return True"

    print("✓ New niche creation test passed")
    print(f"   Product ID: {product.id}")

# Don't forget to add to the tests list in main()!
```

---

## Seeder Service Architecture

### Current Implementation

**File**: [services/seeder/main.py](services/seeder/main.py)

**Current Capabilities**:
- Scrapes Pokemon card data from pokemon-card.com using Playwright
- Validates data using `create_pokemon_card_product()` factory
- Upserts products into `canonical_products` collection
- Structured logging with correlation IDs
- Supports both headed and headless modes
- Multiple CSS selector fallbacks for robustness
- Debug screenshots on failure

**Key Functions**:
```python
@log_execution_time(logger)
def scrape_set_with_playwright(set_code: str, headless: bool = True) -> List[Dict]:
    """Scrape Pokemon cards from pokemon-card.com."""
    # Browser automation logic
    # Returns list of raw card data dictionaries

@log_execution_time(logger)
def seed_database(cards_data: List[Dict]) -> int:
    """Validate and upsert card data into MongoDB."""
    # Uses create_pokemon_card_product() factory
    # Returns count of successfully seeded products
```

### Extending for Multiple Niches

**Option 1: Modular Functions in Same Service**
```python
# services/seeder/main.py

@log_execution_time(logger)
def scrape_pokemon_cards(set_code: str, headless: bool = True) -> List[Dict]:
    """Scrape Pokemon cards."""
    pass

@log_execution_time(logger)
def scrape_watches(brand: str, headless: bool = True) -> List[Dict]:
    """Scrape luxury watches."""
    pass

@log_execution_time(logger)
def scrape_camera_gear(category: str, headless: bool = True) -> List[Dict]:
    """Scrape camera equipment."""
    pass

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--niche", choices=["pokemon", "watches", "camera_gear"])
    parser.add_argument("--query", required=True)

    if args.niche == "pokemon":
        data = scrape_pokemon_cards(args.query, headless=args.headless)
        products = [create_pokemon_card_product(**item) for item in data]
    elif args.niche == "watches":
        data = scrape_watches(args.query, headless=args.headless)
        products = [create_watch_product(**item) for item in data]
    # ... etc
```

**Option 2: Niche-Specific Seeder Services**
```
services/
  ├── pokemon-seeder/
  │   └── main.py
  ├── watch-seeder/
  │   └── main.py
  └── camera-seeder/
      └── main.py
```

**Recommendation**: Use Option 1 for niches with similar scraping patterns (web-based), Option 2 for niches with significantly different workflows (API-based, file-based, etc.).

---

## Troubleshooting Guide

### Issue: Tests Failing After Changes

**Symptoms**: `python tests/test_product_models.py` fails

**Solutions**:
1. Check if you added required fields (breaking change)
2. Verify factory function signatures match test calls
3. Check ID generation logic in `generate_id()` methods
4. Run with verbose mode: `python -v tests/test_product_models.py`
5. Verify all identity models are in the `ProductIdentity` union

### Issue: Seeder Getting 403 Errors

**Symptoms**: `logger.error("Playwright error occurred")`

**Solutions**:
1. Website may have updated bot detection
2. Try running in headed mode: remove `--headless` flag
3. Update User-Agent string in [services/seeder/main.py](services/seeder/main.py):61
4. Check if IP is rate-limited (wait 1 hour)
5. Verify website is accessible: `curl -I https://pokemon-card.com`
6. Add random delays: `time.sleep(random.uniform(2, 5))`

### Issue: MongoDB Connection Errors

**Symptoms**: `Failed to connect to MongoDB`

**Solutions**:
1. Verify `.env` file exists with correct `MONGO_URI`
2. Check MongoDB Atlas allows your IP address
3. Test connection manually: `mongosh "YOUR_MONGO_URI"`
4. Check logs: `grep "database" logs/seeder.log`
5. Verify database name in `.env` matches MongoDB Atlas

### Issue: No Logs Generated

**Symptoms**: `logs/` directory empty

**Solutions**:
1. Verify `logs/` directory exists: `mkdir -p logs`
2. Check file permissions: `ls -la logs/`
3. Verify logger initialization: `logger = get_logger("seeder")`
4. Check log level: `export LOG_LEVEL=DEBUG`
5. Verify log rotation settings in [core/logging.py](core/logging.py)

### Issue: Invalid Product Data

**Symptoms**: `ValidationError` during seeding

**Solutions**:
1. Check scraped data structure matches factory function parameters
2. Verify all required fields are present
3. Check data types (strings vs. integers, etc.)
4. Use `logger.debug()` to log raw scraped data before validation
5. Add data sanitization before calling factory functions

---

## API Reference

### Factory Functions

```python
# Pokemon Cards
create_pokemon_card_product(
    set_code: str,
    card_number: str,
    name_jp: str,
    rarity: str,
    image_url: str,
    source_url: str
) -> CanonicalProduct

# Watches
create_watch_product(
    brand: str,
    model: str,
    reference_number: str,
    image_url: str,
    source_url: str,
    serial_number: str | None = None,
    production_year: int | None = None
) -> CanonicalProduct

# Camera Gear
create_camera_gear_product(
    brand: str,
    model_number: str,
    subcategory: Literal["CAMERA", "LENS", "VIDEO_CAMERA", "VIDEO_ACCESSORY", "PHOTO_ACCESSORY"],
    image_url: str,
    source_url: str,
    condition: str | None = None,
    serial_number: str | None = None
) -> CanonicalProduct
```

### Type Guards

```python
is_pokemon_card(product: CanonicalProduct) -> bool
is_watch(product: CanonicalProduct) -> bool
is_camera_gear(product: CanonicalProduct) -> bool
```

### Logging

```python
get_logger(
    service_name: str,
    log_level: str | None = None,
    enable_console: bool = True,
    enable_file: bool = True,
    enable_json: bool = False
) -> logging.Logger

@log_execution_time(logger: logging.Logger)
def your_function():
    """Automatically logs execution time."""
    pass
```

### Database

```python
from core.database import get_db, close_db

# Get database instance
db = get_db()
collection = db["canonical_products"]

# Close connection (always call in finally block)
close_db()
```

---

## Performance Considerations

### Scraping Best Practices

1. **Use headless mode in production**: Faster and uses less resources
   ```bash
   python services/seeder/main.py --sets sv2a --headless
   ```

2. **Batch operations**: Process multiple queries in one session
   ```bash
   python services/seeder/main.py --sets sv1 sv2a sv4a sv10 --headless
   ```

3. **Respect rate limits**: Add delays between requests if needed
   ```python
   time.sleep(2)  # Already implemented in seeder
   ```

4. **Reuse browser contexts**: Don't create new browsers for each request
   ```python
   browser = p.chromium.launch(headless=headless)
   context = browser.new_context()  # Reuse this
   ```

### Database Best Practices

1. **Use upserts**: Avoid duplicate entries
   ```python
   collection.update_one(
       {"_id": product.id},
       {"$set": product_dict},
       upsert=True  # Creates if doesn't exist, updates if exists
   )
   ```

2. **Index strategically**: Query performance depends on indexes
   ```javascript
   db.canonical_products.createIndex({ "identity.niche_type": 1 })
   ```

3. **Batch operations**: Use `bulk_write()` for large datasets
   ```python
   operations = [
       UpdateOne({"_id": p.id}, {"$set": p.model_dump(by_alias=True)}, upsert=True)
       for p in products
   ]
   collection.bulk_write(operations)
   ```

4. **Query by niche_type first**: Leverage index for faster queries
   ```python
   # Good: Uses index
   collection.find({"identity.niche_type": "POKEMON_CARD", "identity.set_code": "sv2a"})

   # Bad: Full collection scan
   collection.find({"identity.set_code": "sv2a"})
   ```

---

## Security Considerations

### Environment Variables

**NEVER commit these to git**:
- `MONGO_URI` (contains password)
- `DATABASE_NAME`
- Any API keys or secrets

**Always**:
1. Use `.env` file for local development
2. Use environment variables in production
3. Keep `.env` in `.gitignore`
4. Rotate credentials regularly

### MongoDB Security

1. **Use least-privilege users**: Database user should only have read/write on `velodata` DB
2. **Whitelist IPs**: Only allow known IPs in MongoDB Atlas
3. **Use connection string secrets**: Never hardcode credentials
4. **Enable audit logging**: Track who accesses what
5. **Regular backups**: Enable automated backups in MongoDB Atlas

### Web Scraping Ethics

1. **Respect robots.txt**: Check before scraping new sites
2. **Rate limiting**: Don't overwhelm target servers
3. **User-Agent**: Use descriptive User-Agent string
4. **Terms of Service**: Ensure scraping is allowed
5. **Data attribution**: Track source URLs in metadata

---

## Future Enhancements

### Planned Features

- [ ] API service for querying canonical products
- [ ] Real-time price tracking workers
- [ ] Arbitrage detection algorithms
- [ ] User authentication system
- [ ] Dashboard frontend (React/Next.js)
- [ ] Webhook notifications for price changes
- [ ] Multi-region deployment
- [ ] Multi-niche seeder orchestration
- [ ] Scheduled seeding jobs (cron/Celery)

### Technical Debt

- [ ] Async database operations with Motor
- [ ] Async logging for high-throughput
- [ ] Connection pooling optimization
- [ ] Caching layer (Redis)
- [ ] GraphQL API instead of REST
- [ ] OpenTelemetry integration
- [ ] Seeder service refactoring for multi-niche support
- [ ] Integration tests for seeder workflows

---

## Resources

### Documentation

- [ARCHITECTURE.md](docs/ARCHITECTURE.md) - System architecture deep dive
- [LOGGING.md](docs/LOGGING.md) - Comprehensive logging guide
- [Pydantic v2 Docs](https://docs.pydantic.dev/latest/) - Data validation
- [Playwright Docs](https://playwright.dev/python/) - Browser automation
- [MongoDB Python Driver](https://pymongo.readthedocs.io/) - Database operations

### Related Files

- [core/models/product.py](core/models/product.py) - **MOST IMPORTANT FILE**
- [core/logging.py](core/logging.py) - Logging system
- [core/database.py](core/database.py) - MongoDB singleton
- [services/seeder/main.py](services/seeder/main.py) - Canonical products seeder
- [tests/test_product_models.py](tests/test_product_models.py) - Test suite

---

## Quick Reference: Common Commands

```bash
# Activate virtual environment
source venv/bin/activate

# Run tests
python tests/test_product_models.py

# Run seeder (Pokemon cards example)
python services/seeder/main.py --sets sv2a sv4a --headless

# Check logs
tail -f logs/seeder.log

# MongoDB shell
mongosh "YOUR_MONGO_URI"

# Query products
# In MongoDB shell:
use velodata
db.canonical_products.find({"identity.niche_type": "POKEMON_CARD"}).limit(5)

# Install new dependencies
pip install package-name
pip freeze > requirements.txt

# Playwright browser install
playwright install chromium
```

---

## Version History

| Version | Date       | Changes                                          |
|---------|------------|--------------------------------------------------|
| 1.0     | 2025-12-02 | Initial release with 3 niches supported         |
| 1.0.1   | 2025-12-02 | Clarified seeder as multi-niche architecture    |
| 1.1     | TBD        | Add sneakers niche (planned)                    |
| 2.0     | TBD        | Multi-niche seeder refactoring (planned)        |
| 3.0     | TBD        | API service launch (planned)                    |

---

**Document Maintained By**: VeloData Engineering Team
**Last Updated**: 2025-12-02
**Claude Code Version**: Latest
