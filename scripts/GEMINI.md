# scripts Module

## Purpose
Contains utility shell scripts used for development, testing, and CI/CD operations. These scripts automate tasks like running smoke tests (`smoke-test.sh`), completing work cycles (`complete_work.sh`), and monitoring GitHub Actions (`monitor_gh_actions.sh`).

## Internal Dependencies
- Most scripts rely on the local project structure and environment variables.
- `smoke-test.sh` depends on `pytest` and the `tests/e2e/` directory.

## External Dependencies
- Executed directly by developers or continuous integration pipelines to streamline workflows.