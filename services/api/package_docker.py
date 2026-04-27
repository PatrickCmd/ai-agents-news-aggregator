"""Build a Lambda zip artifact for the API service.

Uses public.ecr.aws/lambda/python:3.12 as the build image so wheels are amd64
manylinux. Output: services/api/dist/news_api.zip.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
AGENT_DIR = Path(__file__).resolve().parent
DIST = AGENT_DIR / "dist"
PACKAGE_NAME = "news_api"


_DOCKERFILE = """
FROM public.ecr.aws/lambda/python:3.12 AS build

WORKDIR /work
RUN dnf install -y zip && dnf clean all

COPY pyproject.toml uv.lock ./
COPY packages/ ./packages/
COPY services/{agent}/ ./services/{agent}/

COPY --from=ghcr.io/astral-sh/uv:0.4 /uv /usr/local/bin/uv

RUN uv export --no-dev --no-emit-workspace --package {package} --frozen \\
        --format requirements-txt > /tmp/req.txt
RUN python -m pip install -r /tmp/req.txt --target /pkg --no-cache-dir
RUN cp -r packages/schemas/src/news_schemas /pkg/ \\
 && cp -r packages/config/src/news_config /pkg/ \\
 && cp -r packages/observability/src/news_observability /pkg/ \\
 && cp -r packages/db/src/news_db /pkg/ \\
 && cp -r services/{agent}/src/{package} /pkg/ \\
 && cp services/{agent}/lambda_handler.py /pkg/lambda_handler.py

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
