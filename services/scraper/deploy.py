"""Scraper deploy orchestrator.

Two modes:
  build   — docker build + push to ECR (works standalone)
  deploy  — build + push + terraform apply to update the ECS Express service

Examples:
  uv run python services/scraper/deploy.py --mode build
  uv run python services/scraper/deploy.py --mode deploy --env dev
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path
from urllib.request import urlopen

import boto3


def _profile() -> str:
    return os.environ.get("AWS_PROFILE", "aiengineer")


def _session() -> boto3.Session:
    return boto3.Session(profile_name=_profile())


def _account_id(session: boto3.Session) -> str:
    return session.client("sts").get_caller_identity()["Account"]  # type: ignore[no-any-return]


def _region(session: boto3.Session) -> str:
    region = (
        session.region_name or os.environ.get("AWS_REGION") or os.environ.get("AWS_DEFAULT_REGION")
    )
    if not region:
        raise RuntimeError(
            "AWS region not set (profile default, AWS_REGION, or AWS_DEFAULT_REGION)"
        )
    return region


def _ecr_repo() -> str:
    return os.environ.get("ECR_REPO_NAME", "news-scraper")


def _git_sha() -> str:
    return subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()


def _terraform_dir() -> Path:
    return Path(__file__).resolve().parents[2] / "infra" / "scraper"


def _full_image_uri(session: boto3.Session, tag: str) -> str:
    return f"{_account_id(session)}.dkr.ecr.{_region(session)}.amazonaws.com/{_ecr_repo()}:{tag}"


def _ecr_login(session: boto3.Session) -> None:
    region = _region(session)
    account = _account_id(session)
    cmd = (
        f"aws ecr get-login-password --region {region} --profile {_profile()} | "
        f"docker login --username AWS --password-stdin "
        f"{account}.dkr.ecr.{region}.amazonaws.com"
    )
    subprocess.run(cmd, shell=True, check=True)


def _build_image(sha_tag: str) -> None:
    repo_root = Path(__file__).resolve().parents[2]
    subprocess.run(
        [
            "docker",
            "build",
            # Fargate runs linux/amd64 — force this even on Apple Silicon hosts.
            "--platform=linux/amd64",
            "-f",
            str(Path(__file__).parent / "Dockerfile"),
            "-t",
            sha_tag,
            "--build-arg",
            f"GIT_SHA={_git_sha()}",
            str(repo_root),
        ],
        check=True,
    )


def _push_image(session: boto3.Session, sha_tag: str) -> None:
    uri_sha = _full_image_uri(session, _git_sha())
    uri_latest = _full_image_uri(session, "latest")
    subprocess.run(["docker", "tag", sha_tag, uri_sha], check=True)
    subprocess.run(["docker", "tag", sha_tag, uri_latest], check=True)
    subprocess.run(["docker", "push", uri_sha], check=True)
    subprocess.run(["docker", "push", uri_latest], check=True)
    print(f"pushed {uri_sha}")
    print(f"pushed {uri_latest}")


def _scraper_endpoint() -> str:
    """Read the auto-provisioned ECS Express endpoint from terraform output."""
    result = subprocess.run(
        ["terraform", "output", "-raw", "scraper_endpoint"],
        cwd=_terraform_dir(),
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def _smoke_healthz(url: str) -> None:
    """Curl /healthz; assert 200 and git_sha matches HEAD. Retries up to 3 min."""
    expected = _git_sha()
    deadline = time.time() + 180
    last_err: Exception | None = None
    while time.time() < deadline:
        try:
            with urlopen(url, timeout=10) as resp:
                body = resp.read().decode()
                if f'"git_sha":"{expected}"' in body:
                    print(f"healthz OK: {body}")
                    return
                print(f"healthz returned old sha: {body}; retrying...")
        except Exception as exc:
            last_err = exc
            print(f"healthz attempt failed: {exc}; retrying...")
        time.sleep(10)
    raise RuntimeError(
        f"healthz did not reach expected git_sha={expected} within 3 min: {last_err}"
    )


def cmd_build() -> int:
    session = _session()
    _ecr_login(session)
    local_tag = f"news-scraper:{_git_sha()}"
    _build_image(local_tag)
    _push_image(session, local_tag)
    return 0


def cmd_deploy(env: str) -> int:
    """Build + push + terraform apply + smoke test."""
    if cmd_build() != 0:
        return 1

    tf_dir = _terraform_dir()
    if not tf_dir.exists():
        print(
            f"ERROR: {tf_dir} does not exist. Run the bootstrap + scraper init first.",
            file=sys.stderr,
        )
        return 3

    sha = _git_sha()
    tf_env = {**os.environ, "AWS_PROFILE": _profile()}

    # Select workspace (create if missing)
    try:
        subprocess.run(
            ["terraform", "workspace", "select", env],
            cwd=tf_dir,
            check=True,
            env=tf_env,
        )
    except subprocess.CalledProcessError:
        subprocess.run(
            ["terraform", "workspace", "new", env],
            cwd=tf_dir,
            check=True,
            env=tf_env,
        )

    # In-place update: changing image tag or env vars triggers an ECS rolling
    # deployment automatically. We deliberately don't pass -replace because
    # destroy+create hits the AWS INACTIVE service retention (1h block on name reuse).
    subprocess.run(
        [
            "terraform",
            "apply",
            "-auto-approve",
            f"-var=image_tag={sha}",
        ],
        cwd=tf_dir,
        check=True,
        env=tf_env,
    )

    # Smoke against the ECS-auto-provisioned HTTPS endpoint
    endpoint = _scraper_endpoint()
    if not endpoint.startswith(("http://", "https://")):
        endpoint = f"https://{endpoint}"
    _smoke_healthz(f"{endpoint}/healthz")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["build", "deploy"], required=True)
    parser.add_argument("--env", default="dev")
    args = parser.parse_args()
    if args.mode == "build":
        return cmd_build()
    return cmd_deploy(args.env)


if __name__ == "__main__":
    sys.exit(main())
