#ifndef PROTOCOL_H
#define PROTOCOL_H

#include <stdbool.h>
#include <stddef.h>
#include <sys/types.h>
#include <time.h>

#define MESSAGE_SIZE 1024

typedef struct {
    char partial[MESSAGE_SIZE];
    size_t used;
    bool discarding;
} LineReader;

ssize_t read_line(int fd, LineReader *reader,
                  char *buffer, size_t capacity,
                  const struct timespec *deadline,
                  int idle_timeout_ms);

#endif
