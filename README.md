# Motif: An In-depth Movie Exploring App

# Introduction

## *This app let the users gain in-depth readings on one specific movies, compares movies through different lens, and get recommendation on films to watch depending on the psycological theme they wanted to explore*

# Project Setup

## Prerequisite

### Utilities: 
Python 3.12: [https://www.python.org/downloads/windows/]

Docker: [https://docs.docker.com/engine/install/]

Postgres/PgAdmin: [https://www.postgresql.org/download/]

Pnpm: [https://pnpm.io/installation]


### API Keys: 

OpenAI API Key: [https://openai.com/api/]

---
## Environment Setup (Assuming Windows OS)

### Root

#### Make sure you are in the project root directory (motif)

1. create a file called `.env`
2. copy the content in `.env.example`
3. add your own API key into the file


---
### Frontend

#### Make sure you are in the frontend directory `cd ./frontend/`
Install the frondend packages via pnpm `pnpm install`

---
### Backend

#### Make sure you are in the backend directory `cd ./backend/`

Set up virtual environment for python (**please note the version**)

`py -3.12 -m venv .venv`

Activate the virtual environmnet

`.\.venv\Scripts\Activate.ps1`

Install the requirements

`pip install -r .\requirements.txt`

# Running the Project Locally

## In a separate terminal:
in the backend directory, run `uvicorn app.main:app --reload --port 8000`

## In a separate terminal:
in the frontend directory, run `npm run dev`


# Test Deploy

1. Build the Docker image from your change: `docker compose up -d`

2. check the backend health status by visiting [http://localhost:8000/health]

3. you should see 
```json 
{"status":"ok"}
```
4. run `vercel --prod` type in the project name `motif` and follow the prompt

5. get a temporay vercel deployment, check for any frontend error


