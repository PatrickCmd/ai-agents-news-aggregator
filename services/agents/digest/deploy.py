"""Build, upload, and deploy the digest Lambda.

Modes:
  build   — package_docker.py → S3 upload
  deploy  — build + terraform apply

Examples:
  uv run python services/agents/digest/deploy.py --mode build
  uv run python services/agents/digest/deploy.py --mode deploy --env dev
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import os
import subprocess
import sys
from pathlib import Path

import boto3

AGENT_DIR = Path(__file__).resolve().parent
PACKAGE = "news_digest"
TF_DIR = AGENT_DIR.parents[2] / "infra" / "digest"


def _profile() -> str:
    return os.environ.get("AWS_PROFILE", "aiengineer")


def _session() -> boto3.Session:
    return boto3.Session(profile_name=_profile())


def _account_id(s: boto3.Session) -> str:
    return s.client("sts").get_caller_identity()["Account"]  # type: ignore[no-any-return]


def _git_sha() -> str:
    return subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()


def _bucket(s: boto3.Session) -> str:
    return f"news-aggregator-lambda-artifacts-{_account_id(s)}"


def _zip_path() -> Path:
    return AGENT_DIR / "dist" / f"{PACKAGE}.zip"


def _build_zip() -> Path:
    subprocess.run(
        ["uv", "run", "python", str(AGENT_DIR / "package_docker.py")],
        check=True,
    )
    z = _zip_path()
    if not z.exists():
        raise RuntimeError(f"build did not produce {z}")
    return z


def _b64_sha256(path: Path) -> str:
    h = hashlib.sha256(path.read_bytes()).digest()
    return base64.b64encode(h).decode()


def _upload(s: boto3.Session, sha: str, zip_path: Path) -> str:
    key = f"digest/{sha}.zip"
    s.client("s3").upload_file(str(zip_path), _bucket(s), key)
    print(f"uploaded s3://{_bucket(s)}/{key}")
    return key


def cmd_build() -> int:
    s = _session()
    sha = _git_sha()
    zip_path = _build_zip()
    _upload(s, sha, zip_path)
    print(f"sha256(zip) = {_b64_sha256(zip_path)}")
    return 0


def cmd_deploy(env: str) -> int:
    s = _session()
    sha = _git_sha()
    zip_path = _build_zip()
    key = _upload(s, sha, zip_path)
    sha256 = _b64_sha256(zip_path)

    tf_env = {**os.environ, "AWS_PROFILE": _profile()}
    try:
        subprocess.run(
            ["terraform", "workspace", "select", env],
            cwd=TF_DIR,
            check=True,
            env=tf_env,
        )
    except subprocess.CalledProcessError:
        subprocess.run(
            ["terraform", "workspace", "new", env],
            cwd=TF_DIR,
            check=True,
            env=tf_env,
        )

    subprocess.run(
        [
            "terraform",
            "apply",
            "-auto-approve",
            f"-var=zip_s3_key={key}",
            f"-var=zip_sha256={sha256}",
        ],
        cwd=TF_DIR,
        check=True,
        env=tf_env,
    )
    return 0


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--mode", choices=["build", "deploy"], required=True)
    p.add_argument("--env", default="dev")
    args = p.parse_args()
    return cmd_build() if args.mode == "build" else cmd_deploy(args.env)


if __name__ == "__main__":
    sys.exit(main())
