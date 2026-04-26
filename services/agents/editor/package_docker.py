"""Build a Lambda zip artifact for the editor agent.

Uses public.ecr.aws/lambda/python:3.12 as the build image so wheels are amd64
manylinux. Output: services/agents/editor/dist/news_editor.zip.

Assumes every workspace package follows the src/<pkg>/ layout with an
__init__.py at src/<pkg>/__init__.py — the Dockerfile cp-copies these
trees verbatim into /pkg/. If a new workspace package uses a different
layout, this script will silently produce an unimportable artifact.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
AGENT_DIR = Path(__file__).resolve().parent
DIST = AGENT_DIR / "dist"
PACKAGE_NAME = "news_editor"


_DOCKERFILE = """
FROM public.ecr.aws/lambda/python:3.12 AS build

WORKDIR /work
RUN dnf install -y zip && dnf clean all

COPY pyproject.toml uv.lock ./
COPY packages/ ./packages/
COPY services/agents/{agent}/ ./services/agents/{agent}/

# uv from astral
COPY --from=ghcr.io/astral-sh/uv:0.4 /uv /usr/local/bin/uv

RUN uv export --no-dev --no-emit-workspace --package {package} --frozen \\
        --format requirements-txt > /tmp/req.txt
RUN python -m pip install -r /tmp/req.txt --target /pkg --no-cache-dir
# Copy first-party workspace packages too (they aren't on PyPI).
RUN cp -r packages/schemas/src/news_schemas /pkg/ \\
 && cp -r packages/config/src/news_config /pkg/ \\
 && cp -r packages/observability/src/news_observability /pkg/ \\
 && cp -r packages/db/src/news_db /pkg/ \\
 && cp -r services/agents/{agent}/src/{package} /pkg/ \\
 && cp services/agents/{agent}/lambda_handler.py /pkg/lambda_handler.py

WORKDIR /pkg
RUN zip -r9 /tmp/{package}.zip . -x '*.pyc' '__pycache__/*' 'tests/*' '*/tests/*' '*/tests/**'

FROM scratch AS export
COPY --from=build /tmp/{package}.zip /
"""


def main() -> int:
    if shutil.which("docker") is None:
        print("ERROR: docker not found", file=sys.stderr)
        return 2

    DIST.mkdir(parents=True, exist_ok=True)
    dockerfile = AGENT_DIR / ".package.Dockerfile"
    dockerfile.write_text(_DOCKERFILE.format(agent=AGENT_DIR.name, package=PACKAGE_NAME))

    cmd = [
        "docker",
        "build",
        "--platform=linux/amd64",
        "--target=export",
        "--output",
        f"type=local,dest={DIST}",
        "-f",
        str(dockerfile),
        str(REPO_ROOT),
    ]
    subprocess.run(cmd, check=True)
    print(f"built: {DIST / (PACKAGE_NAME + '.zip')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
