# MomCare-Backend

Backend for [MomCare](https://github.com/rtk-rnjn/MomCare) iOS application. This backend is responsible for handling the requests from the iOS application and interacting with the database to fetch the required data.

We are using MongoDB as our database and FastAPI as our backend.

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

## TODO:

- [x] Add user registration
- [x] Add user update
- [ ] AI Models?
- [ ] Add tests
- [x] Add CI/CD
