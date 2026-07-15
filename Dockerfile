FROM python:3.11-slim-bookworm

# --- Java: Spark needs a JVM. Installed INSIDE the image, not on your host. ---
# Pinned to bookworm (Debian 12) above because the newer "trixie" base
# dropped openjdk-17 in favor of openjdk-21, which Spark 3.5 doesn't officially support.
RUN apt-get update && \
    apt-get install -y --no-install-recommends openjdk-17-jdk-headless procps && \
    rm -rf /var/lib/apt/lists/*

ENV JAVA_HOME=/usr/lib/jvm/java-17-openjdk-amd64
ENV PATH="$JAVA_HOME/bin:$PATH"

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ /app/src/

CMD ["sleep", "infinity"]