"""Build, upload, and deploy the email Lambda.

Modes:
  build   — package_docker.py → S3 upload
  deploy  — build + terraform apply (requires MAIL_FROM env var)

Examples:
  uv run python services/agents/email/deploy.py --mode build
  MAIL_FROM=hi@yourdomain.com uv run python services/agents/email/deploy.py --mode deploy --env dev
  MAIL_FROM=hi@yourdomain.com MAIL_TO_DEFAULT=you@yourdomain.com \\
      uv run python services/agents/email/deploy.py --mode deploy --env dev

The MAIL_FROM env var is REQUIRED for --mode deploy — Resend rejects sends
from unverified domains. MAIL_TO_DEFAULT is optional (defaults to empty,
meaning the email goes to the user's actual address from the DB).
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
PACKAGE = "news_email"
TF_DIR = AGENT_DIR.parents[2] / "infra" / "email"


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
    key = f"email/{sha}.zip"
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
    mail_from = os.environ.get("MAIL_FROM")
    if not mail_from:
        print(
            "ERROR: MAIL_FROM env var is required for --mode deploy. "
            "Resend rejects emails from unverified domains. Set it to a "
            "Resend-verified address like 'hi@yourdomain.com' and retry.",
            file=sys.stderr,
        )
        return 2

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

    extra_vars = [f"-var=mail_from={mail_from}"]
    if os.environ.get("MAIL_TO_DEFAULT"):
        extra_vars.append(f"-var=mail_to_default={os.environ['MAIL_TO_DEFAULT']}")

    subprocess.run(
        [
            "terraform",
            "apply",
            "-auto-approve",
            f"-var=zip_s3_key={key}",
            f"-var=zip_sha256={sha256}",
            *extra_vars,
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
