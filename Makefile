.PHONY: build verify synth-echo review-time-estimate quine-smoke verify-unary verify-both-arms test-conformance build-lisp-guest test-lisp-matrix verify-lisp-conformance build-eval-add test-eval-add verify-h9-eval-add verify-h13 verify-h15 fuzz

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

quine-smoke: build
	python3 tools/search_fixed19_quine.py --contract quine/contract.json --budget quine/budget-smoke.json --output-root evidence/quine

verify-unary: build
	build/venv/bin/python tools/verify_unary_blocks.py

verify-both-arms: build
	build/venv/bin/python -O tools/verify_both_arms_branch.py

test-conformance: build
	python3 -m unittest tests/test_lisp_conformance_runner.py

build-lisp-guest: build
	python3 tools/build_lisp_guest.py --out build/lispslop-guest.mb --manifest build/lispslop-guest.manifest.json

test-lisp-matrix: build-lisp-guest
	python3 -m unittest tests/test_complete_guest_matrix.py

verify-lisp-conformance: build-lisp-guest
	python3 tools/verify_lisp_conformance.py

build-eval-add: build
	python3 tools/build_eval_add.py

test-eval-add: build-eval-add
	python3 -m unittest tests/test_native_eval_add.py

verify-h9-eval-add: build-eval-add
	python3 tools/verify_h9_eval_add.py


verify-h13: build
	python3 -B tools/verify_h13_echo_loop.py
	python3 -B tools/verify_h13_cat.py
	python3 -B tools/verify_h14_countdown.py

verify-h15: build
	python3 -B tools/verify_h15_native_ir_loop.py

verify-h16: build
	python3 -B tools/verify_h16_count_in.py

verify-h17: build
	python3 -B tools/verify_h17_ir_count.py

verify-h18: build
	python3 -B tools/verify_h18_arith_loop.py

verify-h19: build
	python3 -B tools/verify_h19_ir_arith.py

verify-h20: build
	python3 -B tools/verify_h20_cipher.py

verify-h21: build
	python3 -B tools/verify_h21_ir_cipher.py

verify-h22: build
	python3 -B tools/verify_h22_cipher2.py

verify-h23: build
	python3 -B tools/verify_h23_ir_cipher2.py

verify-h24: build
	python3 -B tools/verify_h24_native_ir.py

verify-h25: build
	python3 -B tools/verify_h25_native_ir_unified.py

fuzz: build
	python3 -B tools/fuzz_predicated.py
