.PHONY: build verify synth-echo review-time-estimate

build:
	./tools/build.sh

verify: build
	python3 tools/verify_slice.py

synth-echo: build
	@if test -e build/synth/echo.mb || test -e build/synth/echo.manifest.json; then \
		python3 tools/verify_generated_guest.py build/synth/echo.mb build/synth/echo.manifest.json --profile profiles/fixed19.json --goal examples/echo.json; \
	else \
		python3 tools/synthesize_guest.py examples/echo.json --profile profiles/fixed19.json --output build/synth/echo.mb --manifest build/synth/echo.manifest.json --max-cells 3 --max-nodes 10000 --max-steps 8 --max-address 8; \
	fi

review-time-estimate: synth-echo
	python3 tools/estimate_review_time.py build/synth/echo.mb --bytes-per-second 1 --hours-per-day 8
