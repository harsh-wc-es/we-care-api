# WECARE — Local Development & Setup Guide
## FastAPI / Python 3.13 + MySQL + Vite/React + SMTP OTP

---

## 1. Project Overview

WeCare is a healthcare and caretaker booking platform built with:
- **Backend:** FastAPI (Python 3.13), SQLAlchemy 2.0, PyMySQL, Uvicorn ASGI Server
- **Authentication:** JWT Bearer tokens with Bcrypt password & OTP hashing
- **Email Delivery:** Standard library SMTP (`smtplib` + `EmailMessage`) with STARTTLS
- **Database:** MySQL 8.0 / MariaDB
- **Frontend:** Vite + React 19 Single Page Application

---

## 2. Prerequisites

1. **Python:** Python 3.11, 3.12, or 3.13
2. **Node.js:** Node.js v18+ and npm
3. **Database:** MySQL Server (e.g., MySQL Community Server or MariaDB)
4. **SMTP Service:** Standard Gmail SMTP with an App Password or local SMTP server

---

## 3. Backend Setup (`wecare-api`)

### Step 1: Navigate to Backend Directory
```powershell
cd "wecare-api"
```

### Step 2: Create and Activate Virtual Environment
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

### Step 3: Install Dependencies
```powershell
pip install -r requirements.txt
```

### Step 4: Configure Environment (`.env`)
Copy `.env.example` to `.env` and fill in your local settings:
```powershell
cp .env.example .env
```

Example `.env` configuration:
```env
APP_ENV=local
APP_URL=http://localhost:8000
API_BASE_URL=http://localhost:8000/api/v1
APP_TIMEZONE=Asia/Kolkata
APP_DEBUG=true

RATE_LIMIT_ENABLED=false

JWT_SECRET=your_super_secret_jwt_key_at_least_32_characters

SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USERNAME=your_email@gmail.com
SMTP_PASSWORD=your_16_char_app_password
SMTP_FROM_EMAIL=your_email@gmail.com
SMTP_FROM_NAME=WeCare

DB_HOST=127.0.0.1
DB_PORT=3306
DB_DATABASE=wecare_db
DB_USERNAME=root
DB_PASSWORD=
DB_CHARSET=utf8mb4

UPLOAD_BASE_PATH=uploads
UPLOAD_MAX_MB=5
CORS_ALLOWED_ORIGINS=http://localhost:5173,http://localhost:3000
```

### Step 5: Initialize the Database
Import the SQL schema into your MySQL server:
```powershell
mysql -u root -p wecare_db < database/wecare_db.sql
```

### Step 6: Start the FastAPI Backend
```powershell
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

Backend will be live at `http://127.0.0.1:8000`.
- API Health Check: `http://127.0.0.1:8000/api/v1/health`
- Interactive Swagger Docs: `http://127.0.0.1:8000/api/v1/docs`
- ReDoc Docs: `http://127.0.0.1:8000/api/v1/redoc`

---

## 4. Frontend Setup (`frontend`)

### Step 1: Navigate to Frontend Directory
```powershell
cd "../frontend"
```

### Step 2: Install Node Dependencies
```powershell
npm install
```

### Step 3: Configure Frontend Environment (`.env`)
```env
VITE_API_BASE_URL=http://localhost:8000/api/v1
```

### Step 4: Start Frontend Development Server
```powershell
npm run dev
```

Frontend application will open at `http://localhost:5173`.

### Step 5: Build for Production
```powershell
npm run build
```

---

## 5. Running Automated Backend Tests

To run the complete automated test suite:
```powershell
cd "wecare-api"
pytest -q
```
All 198 test cases will execute against the local test database with mocked SMTP.
