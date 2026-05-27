ARIA
====

Quickstart
----------

1) Create and activate a virtual environment:

```bash
python -m venv .venv
source .venv/bin/activate
```

2) Install in editable mode:

```bash
pip install -e .
```

3) Run the API and app:

```bash
aria-api
aria-app
```

API Examples
------------

Health check:

```bash
curl http://localhost:8000/status
```

Chat:

```bash
curl -X POST http://localhost:8000/chat \
	-H "Content-Type: application/json" \
	-d '{"message":"Merhaba"}'
```

Streaming chat (SSE):

```bash
curl -N -X POST http://localhost:8000/chat/stream \
	-H "Content-Type: application/json" \
	-d '{"message":"Merhaba"}'
```

Chat + local TTS:

```bash
curl -X POST http://localhost:8000/chat \
	-H "Content-Type: application/json" \
	-d '{"message":"Merhaba","speak":true}'
```

Configuration
-------------

Config file is stored at `~/.aria/config.json`.
Example config is in `presets/config.example.json`.

Notes
-----

- Code lives in `src/ARIA` (src layout).
- Requires Python 3.9+.
