# ssh-to-pipeline: SSH to bitbucket pipelines

Sometimes the pipeline fails, and it would really help to SSH into the container
running the script, to try to find out why it doesn't work. This script helps you do that.

In order to SSH into the container, create an account at https://ngrok.com.
You'll get a secret token at https://dashboard.ngrok.com/ (Search for "authtoken").
Set the token as a private environment variable named `NGROK_TOKEN`.

Also set an environment variable `SSH_PUBKEY` with your SSH public key. This
isn't secret, so it can be done with a line like:

```
export SSH_PUBKEY='ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIGu247t0lOwm/8LOUsqkm0/m7T8dx21YIZAOFHJ96Qqk'
```

Now, add this line to the pipeline script, before the failure:

```
curl -s https://raw.githubusercontent.com/noamraph/ssh-to-pipeline/master/ssh_to_pipeline.py | python3 -
```

Push this and wait for the pipeline to run. When the `ssh_to_pipeline.py` script
is run, it will install `openssh-server` and `ngrok`, start the SSH server and
ngrok, and when the connection is established, it will print something like this:

```
Tunnel started. To connect, run:

ssh -p 12280 root@4.tcp.ngrok.io
```

Copy the command to your terminal, and you should be able to SSH into the container
to investigate the problem.
