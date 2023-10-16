pip install --upgrade pip
pip install poetry
poetry config virtualenvs.create false --local
poetry self add poetry-version-plugin
poetry install
pre-commit install
