[group("Running")]
[arg('mode', long, short='m', pattern='dev|run')]
run mode='dev':
    @uv run fastapi {{mode}} main.py


[group("Docs")]
[arg('type', long, short='t', pattern='docs|redoc')]
docs type='docs':
    @firefox --new-tab http://localhost:8000/{{type}}


[group("Migrations")]
current-migration:
    @uv run alembic current


[group("Migrations")]
[arg('message', long, short='m')]
create-migration message:
    @uv run alembic revision --autogenerate -m "{{message}}"


[group("Migrations")]
[arg('name', long, short='n')]
commit-migration name:
    @uv run alembic upgrade {{name}}


[group("Migrations")]
revert-migration:
    @uv run alembic downgrade -1


[group("Migrations")]
history-migration:
    @uv run alembic history
