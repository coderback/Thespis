"""Railway's settings for the Thespis service, as code. It replaces railway.toml, which Railway stops reading on 2026-12-01.

    railway config plan     # what would change on the live service; read it before every apply
    railway config apply    # make the change

Railway doesn't read this file when it deploys, so a push changes nothing here; only `railway config apply` does.
Apply treats anything this file leaves out as something to remove: a variable set in the dashboard but missing from
VARIABLES below would be deleted. Add its name here first. Values never go in this file: `preserve()` keeps whatever
Railway holds.
"""

from railway_sdk import define_railway, github, preserve, project, service, volume

# This repository manages only its own resources in the environment.
PARTIAL = "Thespis"

# The service's variables, by name only. Their values live on Railway (and locally in .env, which is never committed).
VARIABLES = (
    "ADMIN_TOKEN",
    "CONTENT_SAFETY_ENDPOINT", "CONTENT_SAFETY_KEY",
    "GLOBAL_CALL_CAP", "SESSION_CALL_CAP",
    "LLM_API_KEY", "LLM_BASE_URL", "LLM_EXTRA", "LLM_MODEL",
    "LLM_BACKUP_API_KEY", "LLM_BACKUP_BASE_URL", "LLM_BACKUP_EXTRA", "LLM_BACKUP_MODEL",
    "REPLAY",
)


@define_railway
def main(ctx=None):
    thespis = service(
        "Thespis",
        source=github("coderback/Thespis", branch="main", rootDirectory="/"),
        build={"builder": "DOCKERFILE", "dockerfilePath": "Dockerfile"},
        healthcheck="/health",
        healthcheckTimeout=60,
        deploy={"restartPolicyType": "ON_FAILURE"},
        # SQLite lives on this one volume, so there must only ever be one replica.
        replicas=1,
        # The volume holds both games' databases (README, Deploy: back it up before a risky deploy).
        volumeMounts={"/data": volume("thespis-volume", region="europe-west4-drams3a", sizeMB=5000)},
        env={name: preserve() for name in VARIABLES},
    )
    return project("responsible-education", resources=[thespis])
