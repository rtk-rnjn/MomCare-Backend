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

## API Documentation

The MomCare API provides comprehensive, interactive documentation that's automatically generated from the code.

### Accessing Documentation

#### Local Development
When running the server locally:
- **Swagger UI (Interactive)**: http://localhost:8000/docs
- **ReDoc (Alternative)**: http://localhost:8000/redoc  
- **OpenAPI Schema**: http://localhost:8000/openapi.json

#### Production
When deployed to production:
- **Swagger UI**: https://your-domain.com/docs
- **ReDoc**: https://your-domain.com/redoc
- **OpenAPI Schema**: https://your-domain.com/openapi.json

### Documentation Features

- **Interactive Testing**: Try out API endpoints directly in the browser
- **Request/Response Examples**: See sample data for all models and endpoints
- **Authentication Testing**: Use the "Authorize" button to test protected endpoints
- **Schema Validation**: View detailed parameter requirements and data types
- **Comprehensive Descriptions**: Each endpoint includes detailed usage instructions

### Getting Started with the API

1. **Start the server** using the installation instructions above
2. **Open your browser** to http://localhost:8000/docs
3. **Explore endpoints** organized by functional categories:
   - **Authentication**: User registration and login
   - **Content Management**: Nutrition plans, exercises, food search
   - **OTP Authentication**: Email verification
   - **System & Meta**: Health checks and API information

4. **Test authentication**:
   - Use `/auth/register` to create a test account
   - Use `/auth/login` to get an access token
   - Click "Authorize" in Swagger UI and enter your token
   - Test protected endpoints with your authenticated session

### API Categories

- **Authentication**: User management, registration, login, profile updates
- **Content Management**: Meal planning, exercise routines, food database, wellness tips
- **OTP Authentication**: Email verification and account security
- **System & Meta**: Service health, versioning, and metadata

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
- [ ] Add tests
- [x] Add CI/CD
