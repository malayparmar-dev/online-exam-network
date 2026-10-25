#define _POSIX_C_SOURCE 200809L

#include "../src/protocol.h"

#include <errno.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/socket.h>
#include <time.h>
#include <unistd.h>

static void require(int condition, const char *message)
{
    if (!condition) {
        fprintf(stderr, "FAIL: %s\n", message);
        exit(EXIT_FAILURE);
    }
}

int main(void)
{
    int sockets[2];
    char buffer[MESSAGE_SIZE];
    LineReader reader = {0};

    require(socketpair(AF_UNIX, SOCK_STREAM, 0, sockets) == 0,
            "create socketpair");
    require(write(sockets[0], "al", 2) == 2, "write first fragment");
    require(write(sockets[0], "pha\r\nbeta\n", 10) == 10,
            "write remaining framed input");
    require(read_line(sockets[1], &reader, buffer, sizeof(buffer), NULL, 0) == 5,
            "read fragmented CRLF line");
    require(strcmp(buffer, "alpha") == 0, "strip carriage return");
    require(read_line(sockets[1], &reader, buffer, sizeof(buffer), NULL, 0) == 4,
            "preserve second buffered line");
    require(strcmp(buffer, "beta") == 0, "read second line");

    char oversized[MESSAGE_SIZE + 32];
    memset(oversized, 'x', sizeof(oversized));
    oversized[sizeof(oversized) - 2] = '\n';
    oversized[sizeof(oversized) - 1] = '\0';
    require(write(sockets[0], oversized, sizeof(oversized) - 1) ==
                (ssize_t)(sizeof(oversized) - 1),
            "write oversized frame and recovery line");
    require(write(sockets[0], "ok\n", 3) == 3, "write recovery frame");
    require(read_line(sockets[1], &reader, buffer, sizeof(buffer), NULL, 0) == -2,
            "reject oversized frame");
    require(read_line(sockets[1], &reader, buffer, sizeof(buffer), NULL, 0) == 2,
            "recover after oversized frame");
    require(strcmp(buffer, "ok") == 0, "read frame after oversized input");

    struct timespec expired = {.tv_sec = 0, .tv_nsec = 0};
    require(read_line(sockets[1], &reader, buffer, sizeof(buffer), &expired, 0) == -3,
            "report expired absolute deadline");
    close(sockets[0]);
    close(sockets[1]);

    puts("PROTOCOL TESTS PASSED");
    return EXIT_SUCCESS;
}
