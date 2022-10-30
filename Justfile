set dotenv-load

run:
    docker run --rm -it -e NGROK_TOKEN="$NGROK_TOKEN" -e SSH_PUBKEY="$SSH_PUBKEY" -v $PWD:/mnt python:3.8-slim /mnt/ssh_to_pipeline.py
