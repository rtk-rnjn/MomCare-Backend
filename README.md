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
- [ ] Add tests
- [x] Add CI/CD
