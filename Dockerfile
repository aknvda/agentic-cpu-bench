FROM python:3.12-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
      build-essential \
      ca-certificates \
      curl \
      git \
      make \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir pytest uv

WORKDIR /app

COPY pyproject.toml README.md ./
COPY src ./src
COPY tasks ./tasks
COPY fixtures ./fixtures

RUN pip install --no-cache-dir .

CMD ["agentic-cpu-bench", "--help"]
