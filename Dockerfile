# Build stage for npm dependencies
FROM node:24-alpine AS node-builder

WORKDIR /build

# Copy package files first for better layer caching
COPY package.json package-lock.json ./

# Install npm dependencies (including vue, bootstrap, font-awesome)
RUN npm install --only=production

# Final stage
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1

WORKDIR /app

# Copy dependency metadata first for better layer caching.
COPY pyproject.toml ./

# Install runtime dependencies into the system environment.
# (No virtualenv; simpler for OpenShift and minimal images.)
RUN uv sync --no-dev --no-install-project

# Make virtualenv executables available to shell and entrypoint
ENV PATH="/app/.venv/bin:${PATH}"

# Copy application code.
COPY bibra ./bibra

# Install the application package itself (so its version can be determined)
RUN uv pip install .

# Copy installed npm dependencies from build stage
COPY --from=node-builder /build/node_modules ./node_modules

# Create a non-root user (OpenShift-friendly) and ensure /app is writable.
RUN useradd --uid 1001 --create-home --shell /usr/sbin/nologin appuser \
    && chown -R 1001:0 /app

USER 1001

EXPOSE 8000

# Default command: run the FastAPI app.
# Use module path so it works regardless of working directory.
CMD ["uvicorn", "bibra.main:app", "--host", "0.0.0.0", "--port", "8000"]
