#!/usr/bin/env python3
# pylint: disable=unspecified-encoding disable=C

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from subprocess import PIPE, Popen, check_call
from getpass import getuser


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
            f"SSH_PUBKEY is not defined and {authorized_keys} file doesn't exist. "
            f"You won't be able to SSH into the container."
        )


def install_packages() -> None:
    check_call(["sudo", "apt-get", "-q", "update"])
    check_call(
        ["sudo", "apt-get", "-q", "install", "-y", "--no-install-recommends", "curl", "gpg"]
    )
    # Based on linux installation instructions at https://ngrok.com/docs/getting-started
    # Instead of using /etc/apt/trusted.gpg.d, which seems deprecated and isn't
    # supported by GitHub actions, we use what's described here:
    # https://github.com/docker/docs/issues/11625#issuecomment-751388087
    check_call("curl -sSL https://ngrok-agent.s3.amazonaws.com/ngrok.asc | gpg --dearmor | sudo tee /usr/share/keyrings/ngrok.gpg > /dev/null", shell=True)
    check_call('echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/ngrok.gpg] https://ngrok-agent.s3.amazonaws.com buster main" | sudo tee /etc/apt/sources.list.d/ngrok.list > /dev/null', shell=True)
    check_call("sudo apt-get -q update && sudo apt-get -q install -y --no-install-recommends ngrok openssh-server", shell=True)


def fix_bitbucket_tty() -> None:
    with Path("~/.bashrc").expanduser().open("a") as f:
        f.write(
            "\n"
            "# Fix TTY set by bitbucket\n"
            'if [[ "$SSH_TTY" == "$(readlink -f /dev/stdin)" ]]; then exec 1<&0 2<&0; fi\n'
            "\n"
        )


def add_copyenv_script() -> None:
    env_cmd = (
        f"cd {os.getcwd()}; "
        f""". <(xargs -0 bash -c 'printf "export %q\\n" "$@"' -- < /proc/{os.getpid()}/environ)\n"""
    )
    Path("/tmp/copyenv").write_text(env_cmd)

    with open("/etc/motd", "a") as f:
        f.write(
            "\n"
            "\n"
            "=======================================================\n"
            "To copy the environment from the pipeline process, run:\n"
            "\n"
            "source /tmp/copyenv\n"
            "=======================================================\n"
            "\n"
        )


def start_ssh_server(ngrok_token: str) -> None:
    check_call(["ngrok", "config", "add-authtoken", ngrok_token])
    run_sshd = Path("/run/sshd")
    run_sshd.mkdir(parents=True, exist_ok=True)
    ROOT_UID = 0
    os.chown(run_sshd, ROOT_UID, ROOT_UID)
    run_sshd.chmod(0o755)
    # Hint: replace "-D" with "-d" to get sshd to print debug info.
    with Popen(["/usr/sbin/sshd", "-d", "-o", "Port=2222"]) as sshd:
        with Popen(
            "ngrok tcp 2222 --log=stdout --log-format=json | tee /dev/stderr",
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

                    print(
                        f" \n"
                        f" \n"
                        f"Tunnel started. To connect, run:\n"
                        f" \n"
                        f"ssh -p {port} {getuser()}@{host}\n"
                        f" \n"
                        f" \n"
                        f"Tip: to copy the environment from the pipeline, run this in the SSH session:\n"
                        f" \n"
                        f"source /tmp/copyenv\n"
                        f" \n"
                        f" \n",
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

    add_copyenv_script()

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
