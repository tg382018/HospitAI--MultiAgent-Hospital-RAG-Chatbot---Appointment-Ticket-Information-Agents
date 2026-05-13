FROM python:3.12-slim-bookworm

WORKDIR /app

RUN pip install --no-cache-dir --upgrade pip

COPY pyproject.toml README.md ./
COPY src ./src

RUN pip install --no-cache-dir .

ENV XYZ_DATABASE_URL=sqlite+aiosqlite:////data/xyz_hospital.db

EXPOSE 8010

CMD ["uvicorn", "xyz_hospital.main:app", "--host", "0.0.0.0", "--port", "8010"]
