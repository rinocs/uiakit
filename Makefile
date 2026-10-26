.PHONY: test test-capacity test-contracts test-release test-security test-go test-python test-typescript test-widget test-console test-console-browser test-go-sdk test-php build-packages e2e e2e-upgrade e2e-two-instances e2e-restore config storage-s3 vector-store-qdrant plugin-sdk-test plugin-sdk-check plugin-sdk-build release-inventory release-packages release-images release-manifest release-check release-dry-run docs docs-serve

test: test-capacity test-contracts test-release test-security test-go test-python test-typescript test-widget test-console test-go-sdk test-php

test-capacity:
	python3 tests/performance/check_baseline.py tests/performance/baseline.json

test-release:
	python3 -m unittest discover -s tests/release -p 'test_*.py'
	python3 tests/release/check_release.py --source

test-contracts:
	python3 tests/contracts/check_contracts.py

test-security:
	python3 tests/e2e/check_security_config.py
	python3 tests/security/check_matrix.py --run

test-go:
	cd apps/gateway && go test -race ./... && go vet ./...

test-python:
	cd apps/runtime && python -m pytest tests -q
	cd apps/worker && python -m pytest tests -q

test-typescript:
	cd packages/sdk-typescript && npm run check && npm run build

test-widget:
	cd packages/chat-widget && npm run check

test-console:
	cd apps/console && npm run check

test-console-browser:
	cd apps/console && npm run test:browser

test-go-sdk:
	cd packages/sdk-go && go test -race ./... && go vet ./...

test-php:
	cd packages/sdk-php && composer test

build-packages:
	cd packages/sdk-typescript && npm run build
	cd packages/sdk-go && go build ./...
	cd packages/sdk-php && composer validate --no-check-publish
	cd packages/chat-widget && npm run build
	cd apps/console && npm run build

e2e:
	bash tests/e2e/run.sh

e2e-upgrade:
	python3 tests/e2e/check_upgrade.py

e2e-two-instances:
	python3 tests/e2e/check_two_instances.py

e2e-restore:
	python3 tests/e2e/check_restore.py

storage-s3:
	bash tests/e2e/run_storage_s3.sh

vector-store-qdrant:
	bash tests/e2e/run_qdrant.sh

config:
	docker compose config --quiet

plugin-sdk-test:
	cd apps/runtime && python -m pytest tests/test_plugin_manifest.py tests/test_skills.py -q

plugin-sdk-check:
	python -m compileall -q packages/plugin-sdk/src

plugin-sdk-build:
	cd packages/plugin-sdk && python -c "from setuptools.build_meta import build_wheel; build_wheel('dist')"

release-inventory:
	python3 scripts/release.py inventory --output release

release-packages:
	python3 scripts/release.py packages --output release/packages

release-images:
	python3 scripts/release.py images --output release

release-manifest:
	python3 scripts/release.py manifest --output release

release-check:
	python3 tests/release/check_release.py --artifacts release

release-dry-run: release-inventory release-packages release-images release-manifest release-check

docs:
	python3 -m mkdocs build --strict

docs-serve:
	python3 -m mkdocs serve
