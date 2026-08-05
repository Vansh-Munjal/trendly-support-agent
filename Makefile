.PHONY: install run test

install:
	python3 -m venv venv && source venv/bin/activate && pip install -r requirements.txt

run:
	source venv/bin/activate && python3 -m uvicorn src.api.main:app --host 127.0.0.1 --port 8000 --reload

test:
	source venv/bin/activate && python3 -m pytest tests/ -v
