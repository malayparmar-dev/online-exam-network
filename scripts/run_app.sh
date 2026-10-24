#!/usr/bin/env bash

set -e

PROJECT_DIR="$HOME/online-exam-network"
SERVER_BIN="$PROJECT_DIR/server"
CLIENT_BIN="$PROJECT_DIR/client"

if [[ ! -x "$SERVER_BIN" || ! -x "$CLIENT_BIN" ]]; then
    echo "Error: server or client executable is missing."
    echo "Build the project first by running: make"
    exit 1
fi

if [[ $# -lt 1 ]]; then
    echo "Usage: $0 server"
    echo "       $0 client <server-ip>"
    exit 1
fi

case "$1" in
    server)
        exec "$SERVER_BIN"
        ;;
    client)
        if [[ $# -ne 2 ]]; then
            echo "Usage: $0 client <server-ip>"
            exit 1
        fi
        exec "$CLIENT_BIN" "$2"
        ;;
    *)
        echo "Usage: $0 server"
        echo "       $0 client <server-ip>"
        exit 1
        ;;
esac
