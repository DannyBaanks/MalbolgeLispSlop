.PHONY: build verify

build:
	./tools/build.sh

verify: build
	python3 tools/verify_slice.py
