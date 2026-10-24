CC = gcc
CFLAGS = -std=c11 -Wall -Wextra -Wpedantic -Wshadow -Wformat=2 -Wstrict-prototypes -Wmissing-prototypes -O2 -g
LDFLAGS =
LDLIBS = -pthread

.PHONY: all clean

all: server client

server: src/server.c src/protocol.c src/protocol.h
	$(CC) $(CFLAGS) $(LDFLAGS) -o $@ src/server.c src/protocol.c $(LDLIBS)

client: src/client.c src/protocol.c src/protocol.h
	$(CC) $(CFLAGS) $(LDFLAGS) -o $@ src/client.c src/protocol.c

clean:
	rm -f server client
