#define _POSIX_C_SOURCE 200809L

#include "protocol.h"

#include <errno.h>
#include <limits.h>
#include <poll.h>
#include <string.h>
#include <time.h>
#include <unistd.h>

static int remaining_ms(const struct timespec *end,
                        const struct timespec *now)
{
    long long milliseconds =
        ((long long)end->tv_sec - (long long)now->tv_sec) * 1000LL;

    milliseconds +=
        ((long long)end->tv_nsec - (long long)now->tv_nsec
         + 999999LL) / 1000000LL;

    if (milliseconds <= 0)
        return 0;

    if (milliseconds > INT_MAX)
        return INT_MAX;

    return (int)milliseconds;
}

ssize_t read_line(int fd, LineReader *reader,
                  char *buffer, size_t capacity,
                  const struct timespec *deadline,
                  int idle_timeout_ms)
{
    struct timespec call_start;

    if (reader == NULL || buffer == NULL ||
        capacity < 2 || capacity > MESSAGE_SIZE ||
        reader->used >= MESSAGE_SIZE) {
        errno = EINVAL;
        return -1;
    }

    if (clock_gettime(CLOCK_MONOTONIC, &call_start) == -1)
        return -1;

    for (;;) {
        struct timespec now;
        int timeout = -1;

        if (clock_gettime(CLOCK_MONOTONIC, &now) == -1)
            return -1;

        if (deadline != NULL) {
            int left = remaining_ms(deadline, &now);

            if (left == 0) {
                errno = ETIMEDOUT;
                return -3;
            }

            timeout = left;
        }

        if (idle_timeout_ms > 0) {
            long long end_ms =
                (long long)call_start.tv_sec * 1000LL +
                call_start.tv_nsec / 1000000LL +
                idle_timeout_ms;

            struct timespec idle_end = {
                .tv_sec = (time_t)(end_ms / 1000LL),
                .tv_nsec = (long)((end_ms % 1000LL) * 1000000LL)
            };

            int left = remaining_ms(&idle_end, &now);

            if (left == 0) {
                errno = EAGAIN;
                return -1;
            }

            if (timeout < 0 || left < timeout)
                timeout = left;
        }

        struct pollfd pfd = {
            .fd = fd,
            .events = POLLIN,
            .revents = 0
        };

        int ready = poll(&pfd, 1, timeout);

        if (ready == -1) {
            if (errno == EINTR)
                continue;

            return -1;
        }

        if (ready == 0) {
            if (deadline != NULL) {
                if (clock_gettime(CLOCK_MONOTONIC, &now) == -1)
                    return -1;

                if (remaining_ms(deadline, &now) == 0) {
                    errno = ETIMEDOUT;
                    return -3;
                }
            }

            errno = EAGAIN;
            return -1;
        }

        if (pfd.revents & POLLNVAL) {
            errno = EBADF;
            return -1;
        }

        char ch;
        ssize_t n = read(fd, &ch, 1);

        if (n == -1) {
            if (errno == EINTR ||
                errno == EAGAIN ||
                errno == EWOULDBLOCK)
                continue;

            return -1;
        }

        if (n == 0) {
            if (reader->used != 0 || reader->discarding) {
                reader->used = 0;
                reader->discarding = false;
                errno = EPROTO;
                return -1;
            }

            return 0;
        }

        if (ch == '\n') {
            if (reader->discarding) {
                reader->used = 0;
                reader->discarding = false;
                buffer[0] = '\0';
                errno = EMSGSIZE;
                return -2;
            }

            size_t length = reader->used;

            memcpy(buffer, reader->partial, length);
            buffer[length] = '\0';
            reader->used = 0;

            return (ssize_t)length;
        }

        if (ch == '\r' || reader->discarding)
            continue;

        if (reader->used < capacity - 1 &&
            reader->used < MESSAGE_SIZE - 1) {
            reader->partial[reader->used++] = ch;
        } else {
            reader->discarding = true;
        }
    }
}
