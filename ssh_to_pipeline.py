#!/usr/bin/env python3
# pylint: disable=unspecified-encoding disable=C

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from subprocess import PIPE, Popen, check_call, check_output


def update_authorized_keys() -> None:
    # I have seen sshd refuse to accept the public key because the home directory
    # was writable by others.
    check_call("chmod go-w ~", shell=True)

    authorized_keys = Path("~/.ssh/authorized_keys").expanduser()
    ssh_pubkey = os.environ.get("SSH_PUBKEY")
    if ssh_pubkey is not None:
        authorized_keys.parent.mkdir(exist_ok=True)
        with open(authorized_keys, "a") as f:
            f.write("\n" + ssh_pubkey + "\n")
        authorized_keys.chmod(0o644)
    if not authorized_keys.exists():
        raise RuntimeError(
            "SSH_PUBKEY is not defined and ~/.ssh/authorized_keys file doesn't exist. "
            "You won't be able to SSH into the container."
        )


def install_packages() -> None:
    # Based on linux installation instructions at https://ngrok.com/docs/getting-started
    ngrok_asc = check_output(
        ["curl", "-s", "https://ngrok-agent.s3.amazonaws.com/ngrok.asc"],
        encoding="ascii",
    )
    Path("/etc/apt/trusted.gpg.d/ngrok.asc").write_text(ngrok_asc)
    Path("/etc/apt/sources.list.d/ngrok.list").write_text(
        "deb https://ngrok-agent.s3.amazonaws.com buster main\n"
    )
    check_call(["apt-get", "-q", "update"])
    check_call(
        [
            "apt-get",
            "-q",
            "install",
            "-y",
            "--no-install-recommends",
            "ngrok",
            "openssh-server",
        ]
    )


def fix_bitbucket_tty() -> None:
    with Path("~/.bashrc").expanduser().open("a") as f:
        f.write(
            "\n"
            "# Fix TTY set by bitbucket\n"
            'if [[ "$SSH_TTY" == "$(readlink -f /dev/stdin)" ]]; then exec 1<&0 2<&0; fi\n'
            "\n"
        )


def start_ssh_server(ngrok_token: str) -> None:
    check_call(["ngrok", "config", "add-authtoken", ngrok_token])
    run_sshd = Path("/run/sshd")
    run_sshd.mkdir(parents=True, exist_ok=True)
    ROOT_UID = 0
    os.chown(run_sshd, ROOT_UID, ROOT_UID)
    run_sshd.chmod(0o755)
    with Popen(["/usr/sbin/sshd", "-D"]) as sshd:
        with Popen(
            "ngrok tcp 22 --log=stdout --log-format=json | tee /dev/stderr",
            shell=True,
            stdout=PIPE,
            bufsize=0,
            encoding="ascii",
        ) as ngrok:
            assert ngrok.stdout is not None  # for mypy
            while True:
                line = ngrok.stdout.readline()
                if sshd.poll() is not None:
                    raise RuntimeError("sshd terminated unexpectedly")
                if line == "":
                    break
                d = json.loads(line)
                # print(f"d = {d!r}", flush=True)
                if d.get("msg") == "started tunnel":
                    url = d["url"]
                    m = re.match(r"^tcp://(.+):(\d+)$", url)
                    assert m is not None
                    host, port = m.groups()
                    env_cmd = f"""cd {os.getcwd()}; . <(xargs -0 bash -c 'printf "export %q\\n" "$@"' -- < /proc/{os.getpid()}/environ)"""
                    print(
                        f"\n"
                        f"\n"
                        f"Tunnel started. To connect, run:\n"
                        f"\n"
                        f"ssh -p {port} root@{host}\n"
                        f"\n"
                        f"\n"
                        f"Tip: to get the environment of the pipeline, run this in the SSH session:\n"
                        f"\n"
                        f"{env_cmd}\n"
                        f"\n"
                        f"\n",
                        flush=True,
                    )
        # If ngrok exited, close sshd
        sshd.kill()


def ssh_to_pipeline() -> None:
    ngrok_token = os.environ.get("NGROK_TOKEN")
    if ngrok_token is None:
        raise RuntimeError(
            "NGROK_TOKEN is not defined. Please define this environment variable."
        )
    if len(ngrok_token.strip().split()) != 1:
        raise RuntimeError(
            "NGROK_TOKEN is not one word. Please make sure it is just the token."
        )

    update_authorized_keys()

    install_packages()

    fix_bitbucket_tty()

    start_ssh_server(ngrok_token)


def main() -> None:
    from argparse import ArgumentParser

    parser = ArgumentParser(
        description="Open a SSH server to allow access to the pipeline container"
    )
    _args = parser.parse_args()

    ssh_to_pipeline()


if __name__ == "__main__":
    main()
