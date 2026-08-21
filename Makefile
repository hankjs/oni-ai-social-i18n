SHELL := /bin/bash
.SHELLFLAGS := -eu -o pipefail -c
ROOT := $(abspath $(dir $(lastword $(MAKEFILE_LIST))))

.PHONY: export validate check

export:
	@python3 "$(ROOT)/tools/export.py" --root "$(ROOT)"

validate:
	@python3 "$(ROOT)/tools/validate.py" --root "$(ROOT)"

check: validate
	@python3 -m unittest discover -s "$(ROOT)/tools/tests" -p 'test_*.py'
	@python3 "$(ROOT)/tools/export.py" --root "$(ROOT)" --check
