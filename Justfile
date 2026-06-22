[group("Running")]
[arg('mode', long, short='m', pattern='dev|run')]
run mode='dev':
    @uv run fastapi {{mode}} main.py


[group("Docs")]
[arg('type', long, short='t', pattern='docs|redoc')]
docs type='docs':
    @firefox --new-tab http://localhost:8000/{{type}}
