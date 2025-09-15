# MomCare-Backend

Backend for [MomCare](https://github.com/rtk-rnjn/MomCare) iOS application. This backend is responsible for handling the requests from the iOS application and interacting with the database to fetch the required data.

We are using MongoDB as our database and FastAPI as our backend.

## Features

- **User Management**: Complete user registration, authentication, and profile management
- **Health Tracking**: Medical data tracking, mood monitoring, and history management  
- **Nutrition Planning**: AI-powered meal planning with detailed nutritional information
- **Exercise Management**: Personalized exercise routines with progress tracking
- **Content Discovery**: Food search, exercise recommendations, and wellness tips
- **Media Management**: Secure file storage and multimedia content handling

## Installation

Rename `.example-env` to `.env` and fill in the required values, especially the database credentials.

```bash
$ git clone --depth=1 https://github.com/rtk-rnjn/MomCare-Backend
$ cd MomCare-Backend
```
```bash
$ python3 -m venv .venv
$ source .venv/bin/activate
$ pip install -r requirements.txt
```

## Usage

```bash
$ python3 main.py
```

### Example Usage

```bash
# Register a new user
curl -X POST "http://localhost:8000/auth/register" \
  -H "Content-Type: application/json" \
  -d '{
    "id": "user_123",
    "first_name": "Sarah",
    "email_address": "sarah@example.com",
    "password": "securePassword123"
  }'

# Login and get access token
curl -X POST "http://localhost:8000/auth/login" \
  -H "Content-Type: application/json" \
  -d '{
    "email_address": "sarah@example.com",
    "password": "securePassword123"
  }'

# Use token to access protected endpoints
curl -X GET "http://localhost:8000/content/plan" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN"
```

## TODO:

- [x] Add user registration
- [x] Add user update
- [x] AI Models?
- [x] Add comprehensive API documentation
- [x] Add tests
- [x] Add CI/CD

## Testing

This project includes comprehensive unit and integration tests to ensure code quality and reliability.

### Test Structure

```
tests/
├── unit/           # Unit tests (no external dependencies)
├── integration/    # Integration tests (require secrets)
├── conftest.py     # Shared test fixtures
└── __init__.py
```

### Running Tests

#### Prerequisites

Install testing dependencies:
```bash
pip install -r requirements.txt
```

#### Unit Tests

Unit tests run without external dependencies using mocks:

```bash
# Run all unit tests
python -m pytest tests/unit/ -v

# Run specific test file
python -m pytest tests/unit/test_token_handler.py -v

# Run tests with coverage
python -m pytest tests/unit/ --cov=src --cov-report=html
```

#### Integration Tests

Integration tests require real environment variables and external services:

```bash
# Set up environment variables first
cp .example-env .env
# Edit .env with real values

# Run integration tests
python -m pytest tests/integration/ -v -m integration

# Run specific integration test
python -m pytest tests/integration/test_database.py -v
```

#### Required Environment Variables for Integration Tests

```bash
AWS_ACCESS_KEY=""
AWS_SECRET_KEY=""
AWS_REGION=""
AWS_BUCKET_NAME=""
EMAIL_ADDRESS=""
EMAIL_PASSWORD=""
GEMINI_API_KEY=""
JWT_SECRET=""
MONGODB_URI=""
PIXEL_API_KEY=""
SEARCH_API_KEY=""
SEARCH_API_CX=""
```

#### Test Markers

Tests are organized using pytest markers:

```bash
# Run only unit tests
python -m pytest -m "unit"

# Run only integration tests  
python -m pytest -m "integration"

# Skip integration tests
python -m pytest -m "not integration"
```

### Continuous Integration

Tests run automatically on GitHub Actions:

- **Unit Tests**: Run on every push and PR (no secrets required)
- **Integration Tests**: Run only on `main` branch and scheduled workflows (secrets injected)
- **Security Scans**: Run Bandit and Safety checks
- **Code Quality**: Check formatting with Black, import sorting with isort, and linting with Ruff

### Writing Tests

#### Unit Test Example

```python
import pytest
from unittest.mock import patch, AsyncMock

pytestmark = pytest.mark.unit

class TestMyFeature:
    def test_my_function(self):
        # Test implementation with mocks
        pass
```

#### Integration Test Example

```python
import pytest
import os

pytestmark = pytest.mark.integration

class TestMyIntegration:
    async def test_database_connection(self):
        if not os.getenv("MONGODB_URI"):
            pytest.skip("MONGODB_URI not set")
        # Test with real database
```

### Test Coverage

Generate coverage reports:

```bash
# HTML coverage report
python -m pytest tests/unit/ --cov=src --cov-report=html
open htmlcov/index.html

# Terminal coverage report
python -m pytest tests/unit/ --cov=src --cov-report=term-missing
```
