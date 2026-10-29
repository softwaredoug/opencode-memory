.PHONY: install test

install:
	./scripts/install.sh

test:
	npm test
	uv run pytest
