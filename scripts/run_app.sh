#!/usr/bin/env bash

set -e

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd -- "$SCRIPT_DIR/.." && pwd)"
SERVER_BIN="$PROJECT_DIR/server"
CLIENT_BIN="$PROJECT_DIR/client"

if [[ ! -x "$SERVER_BIN" || ! -x "$CLIENT_BIN" ]]; then
    echo "Error: server or client executable is missing."
    echo "Build the project first by running: make"
    exit 1
fi

if [[ $# -lt 1 ]]; then
    echo "Usage: $0 server"
    echo "       $0 client <server-ip> [port]"
    exit 1
fi

case "$1" in
    server)
        exec "$SERVER_BIN"
        ;;
    client)
        if [[ $# -lt 2 || $# -gt 3 ]]; then
            echo "Usage: $0 client <server-ip> [port]"
            exit 1
        fi
        if [[ $# -eq 3 ]]; then
            exec "$CLIENT_BIN" "$2" "$3"
        fi
        exec "$CLIENT_BIN" "$2"
        ;;
    *)
        echo "Usage: $0 server"
        echo "       $0 client <server-ip>"
        exit 1
        ;;
esac
