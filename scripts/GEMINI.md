# scripts Module

## Purpose

Contains utility shell scripts used for development, testing, and CI/CD operations. These scripts automate tasks like running smoke tests in a production-like Docker container (`smoke-test.sh`) to verify building and startup, and monitoring the status of the latest GitHub Actions runs (`monitor_gh_actions.sh`).

## Internal Dependencies

- **Project Structure**: Both scripts are designed to be executed from the repository root and depend on the presence of project files such as the root `Dockerfile`.
- **Docker Configuration**: `smoke-test.sh` probes for an existing `gemini-webui-dev` container to extract configuration like ports, environment variables, volumes, and networks.

## External Dependencies

- **System Tools**: Requires `bash` as the execution environment and common utilities like `grep`, `sed`, and `docker`.
- **Docker and Buildx**: `smoke-test.sh` depends on `docker` and `docker buildx` for building and running test containers.
- **GitHub CLI**: `monitor_gh_actions.sh` requires the `gh` tool to be installed and authenticated to monitor GitHub Actions runs.
- **Manual Execution**: Primarily executed by developers to streamline their local development and monitoring workflows.
