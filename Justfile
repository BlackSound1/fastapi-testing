[group("Running")]
[arg('mode', long, short='m', pattern='dev|run')]
run mode='dev':
    @uv run fastapi {{mode}} main.py
