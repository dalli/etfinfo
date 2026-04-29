FROM python:3.12-slim

# 시스템 의존성 설치 (psycopg2, pykrx 빌드에 필요)
RUN apt-get update && apt-get install -y \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# pip 최신화 및 setuptools 먼저 설치 (pykrx가 pkg_resources 필요)
RUN pip install --no-cache-dir --upgrade pip setuptools

# 의존성 파일 복사 후 설치
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 소스 코드 복사
COPY . .

# 앱 실행 (--reload: 파일 변경 감지로 자동 재시작, 개발 환경용)
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
