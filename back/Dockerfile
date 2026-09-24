FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Dependencies first, in their own layer: a source change does not reinstall them.
COPY pyproject.toml ./
RUN python -c "import tomllib; print('\n'.join(tomllib.load(open('pyproject.toml', 'rb'))['project']['dependencies']))" > /tmp/requirements.txt \
    && pip install -r /tmp/requirements.txt

# Installed in editable mode, as for a local run: the app imports itself as `src.*`
# and reads its version from the package metadata.
COPY src ./src
COPY alembic.ini ./
COPY alembic ./alembic
RUN pip install --no-deps -e . \
    && useradd --system --no-create-home app

USER app
EXPOSE 8001

# Migrations are applied by the `migrate` service of the stand, from the same image.
# `--no-access-log`: the app's own middleware logs each request as one structured record.
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8001", "--no-access-log"]
