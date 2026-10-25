CC = gcc
CFLAGS = -std=c11 -Wall -Wextra -Wpedantic -Wshadow -Wformat=2 -Wstrict-prototypes -Wmissing-prototypes -O2 -g
LDFLAGS =
LDLIBS = -pthread

.PHONY: all clean test test-controller

all: server client

server: src/server.c src/protocol.c src/protocol.h
	$(CC) $(CFLAGS) $(LDFLAGS) -o $@ src/server.c src/protocol.c $(LDLIBS)

client: src/client.c src/protocol.c src/protocol.h
	$(CC) $(CFLAGS) $(LDFLAGS) -o $@ src/client.c src/protocol.c

build/test_protocol: tests/test_protocol.c src/protocol.c src/protocol.h
	mkdir -p build
	$(CC) $(CFLAGS) $(LDFLAGS) -o $@ tests/test_protocol.c src/protocol.c

test: all build/test_protocol
	./build/test_protocol
	python3 tests/test_performance_metrics.py
	python3 tests/test_application.py

test-controller:
	@test -x .venv-sdn/bin/osken-manager || { echo "Create .venv-sdn from requirements-sdn.txt first."; exit 1; }
	python3 tests/test_controller_control.py

clean:
	rm -f server client
	rm -rf build
