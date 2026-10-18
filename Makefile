.PHONY: build verify synth-echo

build:
	./tools/build.sh

verify: build
	python3 tools/verify_slice.py

synth-echo: build
	python3 tools/synthesize_guest.py examples/echo.json --profile profiles/fixed19.json --output build/synth/echo.mb --manifest build/synth/echo.manifest.json --max-cells 3 --max-nodes 10000 --max-steps 8 --max-address 8
