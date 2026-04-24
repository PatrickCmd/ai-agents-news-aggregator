"""Scraper deploy orchestrator.

Two modes:
  build   — docker build + push to ECR (works standalone; needs ECR repo to exist)
  deploy  — calls into #6's Terraform to update the ECS service (blocked until
            that module lands; raises a clear error until then)

Examples:
  uv run python services/scraper/deploy.py --mode build
  uv run python services/scraper/deploy.py --mode deploy --env dev
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

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


def cmd_build() -> int:
    session = _session()
    _ecr_login(session)
    local_tag = f"news-scraper:{_git_sha()}"
    _build_image(local_tag)
    _push_image(session, local_tag)
    return 0


def cmd_deploy(env: str) -> int:
    tf_dir = Path(__file__).resolve().parents[2] / "infra" / "envs" / env
    if not tf_dir.exists():
        print(
            f"ERROR: {tf_dir} does not exist yet. #6 Terraform must be in "
            "place before `deploy` can run. Use --mode build until then.",
            file=sys.stderr,
        )
        return 3
    sha = _git_sha()
    subprocess.run(
        [
            "terraform",
            "apply",
            "-replace=module.scraper.aws_ecs_service.this",
            f"-var=image_tag={sha}",
            "-auto-approve",
        ],
        cwd=tf_dir,
        check=True,
        env={**os.environ, "AWS_PROFILE": _profile()},
    )
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
