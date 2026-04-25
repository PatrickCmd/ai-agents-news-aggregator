"""Push .env sensitive values into SSM Parameter Store (SecureString).

Run after `terraform apply` creates the placeholder params:

    uv run python infra/scraper/sync_secrets.py --env dev
"""

from __future__ import annotations

import argparse
import os
import sys

import boto3
from dotenv import find_dotenv, load_dotenv

ENV_TO_PARAM: dict[str, str] = {
    "SUPABASE_DB_URL": "supabase_db_url",
    "SUPABASE_POOLER_URL": "supabase_pooler_url",
    "OPENAI_API_KEY": "openai_api_key",
    "LANGFUSE_PUBLIC_KEY": "langfuse_public_key",
    "LANGFUSE_SECRET_KEY": "langfuse_secret_key",
    "YOUTUBE_PROXY_USERNAME": "youtube_proxy_username",
    "YOUTUBE_PROXY_PASSWORD": "youtube_proxy_password",
    "RESEND_API_KEY": "resend_api_key",
}


def push_params(ssm_client: object, env: str) -> int:
    """Push all set .env values to SSM. Returns number of params pushed."""
    pushed = 0
    for env_key, param_suffix in ENV_TO_PARAM.items():
        value = os.environ.get(env_key)
        if not value:
            print(f"skip {env_key} (not set)")
            continue
        name = f"/news-aggregator/{env}/{param_suffix}"
        ssm_client.put_parameter(  # type: ignore[attr-defined]
            Name=name, Value=value, Type="SecureString", Overwrite=True
        )
        print(f"pushed {name}")
        pushed += 1
    return pushed


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--env", required=True, choices=["dev", "prod"])
    parser.add_argument("--profile", default=os.environ.get("AWS_PROFILE", "aiengineer"))
    args = parser.parse_args()

    load_dotenv(find_dotenv())
    session = boto3.Session(profile_name=args.profile)
    ssm = session.client("ssm")
    count = push_params(ssm, env=args.env)
    print(f"done: {count} parameters updated")
    return 0


if __name__ == "__main__":
    sys.exit(main())
