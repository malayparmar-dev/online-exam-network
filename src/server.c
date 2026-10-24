#define _POSIX_C_SOURCE 200809L

#include <arpa/inet.h>
#include <errno.h>
#include <netinet/in.h>
#include <pthread.h>
#include <signal.h>
#include <stdbool.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/socket.h>
#include <sys/time.h>
#include <time.h>
#include <unistd.h>
#include "protocol.h"

#define PORT 8080
#define BACKLOG 50
#define BUFFER_SIZE 1024
#define EXAM_DURATION_SECONDS 300
#define QUESTION_COUNT 5
#define MAX_STUDENTS 1000
#define MAX_ID_LENGTH 32

typedef struct {
    const char *text;
    const char *options[4];
    char correct;
} Question;

typedef struct {
    int fd;
    char student_id[MAX_ID_LENGTH + 1];
    LineReader reader;
} ClientArgs;

static const Question questions[QUESTION_COUNT] = {
    {"Which protocol provides reliable, ordered byte-stream delivery?",
     {"UDP", "TCP", "IP", "ARP"}, 'B'},
    {"Which function assigns a local address to a socket?",
     {"connect()", "listen()", "bind()", "accept()"}, 'C'},
    {"Which OSI layer is responsible for routing packets?",
     {"Physical", "Data Link", "Network", "Presentation"}, 'C'},
    {"Which address identifies a process endpoint on a host?",
     {"Port number", "MAC address", "Subnet mask", "Frame checksum"}, 'A'},
    {"Which protocol lets OpenFlow switches communicate with a controller?",
     {"SMTP", "OpenFlow", "FTP", "DHCP"}, 'B'}
};

static pthread_mutex_t students_mutex = PTHREAD_MUTEX_INITIALIZER;
static pthread_mutex_t log_mutex = PTHREAD_MUTEX_INITIALIZER;

static char active_students[MAX_STUDENTS][MAX_ID_LENGTH + 1];
static size_t active_count;

static int send_line(int fd, const char *message)
{
    size_t length = strlen(message);
    size_t sent = 0;

    while (sent < length) {
        ssize_t n = send(fd, message + sent, length - sent, MSG_NOSIGNAL);

        if (n < 0) {
            if (errno == EINTR)
                continue;
            return -1;
        }

        if (n == 0)
            return -1;

        sent += (size_t)n;
    }

    return 0;
}

static bool valid_student_id(const char *id)
{
    size_t len = strlen(id);

    if (len == 0 || len > MAX_ID_LENGTH)
        return false;

    for (size_t i = 0; i < len; i++) {
        char c = id[i];

        if (!((c >= 'A' && c <= 'Z') ||
              (c >= 'a' && c <= 'z') ||
              (c >= '0' && c <= '9') ||
              c == '_' || c == '-'))
            return false;
    }

    return true;
}

static int register_student(const char *id)
{
    int result = 0;

    pthread_mutex_lock(&students_mutex);

    for (size_t i = 0; i < active_count; i++) {
        if (strcmp(active_students[i], id) == 0) {
            result = -1;
            goto done;
        }
    }

    if (active_count >= MAX_STUDENTS) {
        result = -2;
        goto done;
    }

    snprintf(active_students[active_count],
             sizeof(active_students[active_count]), "%s", id);
    active_count++;

done:
    pthread_mutex_unlock(&students_mutex);
    return result;
}

static void unregister_student(const char *id)
{
    pthread_mutex_lock(&students_mutex);

    for (size_t i = 0; i < active_count; i++) {
        if (strcmp(active_students[i], id) == 0) {
            if (i + 1 < active_count) {
                memmove(&active_students[i], &active_students[i + 1],
                        (active_count - i - 1) *
                        sizeof(active_students[0]));
            }

            active_count--;
            break;
        }
    }

    pthread_mutex_unlock(&students_mutex);
}

static int send_question(int fd, int index, char answer)
{
    const Question *q = &questions[index];
    char message[BUFFER_SIZE];

    snprintf(message, sizeof(message),
             "QUESTION %d/%d: %s | A) %s | B) %s | C) %s | D) %s | Your answer: %c\n",
             index + 1, QUESTION_COUNT, q->text,
             q->options[0], q->options[1],
             q->options[2], q->options[3],
             answer ? answer : '-');

    return send_line(fd, message);
}

static bool deadline_reached(const struct timespec *deadline)
{
    struct timespec now;

    if (clock_gettime(CLOCK_MONOTONIC, &now) == -1) {
        perror("clock_gettime");
        return true;
    }

    return now.tv_sec > deadline->tv_sec ||
           (now.tv_sec == deadline->tv_sec &&
            now.tv_nsec >= deadline->tv_nsec);
}

static void handle_exam(int fd, const char *student_id,
                         LineReader *reader)
{
    char message[BUFFER_SIZE];
    char answers[QUESTION_COUNT] = {0};
    struct timespec deadline = {0, 0};
    bool started = false;
    bool submitted = false;

    if (send_line(fd,
                  "WELCOME: Online Examination System\n"
                  "Enter START to begin your examination.\n") == -1)
        return;

    ssize_t n = read_line(fd, reader, message, sizeof(message),
                           NULL, 10000);

    if (n <= 0)
        return;

    if (strcmp(message, "START") != 0) {
        send_line(fd, "ERROR: Expected START.\n");
        return;
    }

    started = true;
    if (clock_gettime(CLOCK_MONOTONIC, &deadline) == -1) {
        perror("clock_gettime");
        return;
    }
    deadline.tv_sec += EXAM_DURATION_SECONDS;

    if (send_line(fd,
                  "STARTED: Duration is 300 seconds.\n") == -1)
        return;

    while (started && !submitted) {
        if (deadline_reached(&deadline)) {
            send_line(fd, "TIMEOUT: Exam deadline reached.\n");
            break;
        }

        n = read_line(fd, reader, message, sizeof(message),
                      &deadline, 2000);

        if (n == -3) {
            send_line(fd, "TIMEOUT: Exam deadline reached.\n");
            break;
        }

        if (n == -1 && (errno == EAGAIN || errno == EWOULDBLOCK))
            continue;

        if (n == -2) {
            if (send_line(fd, "ERROR: Command too long.\n") == -1)
                break;
            continue;
        }

        if (n <= 0)
            break;

        if (deadline_reached(&deadline)) {
            send_line(fd, "TIMEOUT: Exam deadline reached.\n");
            break;
        }

        if (strcmp(message, "SUBMIT") == 0) {
            submitted = true;
            break;
        }

        if (strcmp(message, "QUIT") == 0) {
            send_line(fd, "QUIT: Examination abandoned.\n");
            break;
        }

        int question_number;
        char answer;
        char extra;

        if (sscanf(message, "GET %d %c",
                   &question_number, &extra) == 1 &&
            question_number >= 1 &&
            question_number <= QUESTION_COUNT) {
            if (send_question(fd, question_number - 1,
                              answers[question_number - 1]) == -1)
                break;

            continue;
        }

        if (sscanf(message, "ANSWER %d %c %c",
                   &question_number, &answer, &extra) == 2 &&
            question_number >= 1 &&
            question_number <= QUESTION_COUNT &&
            answer >= 'A' && answer <= 'D') {
            answers[question_number - 1] = answer;

            if (send_line(fd, "OK: Answer recorded.\n") == -1)
                break;

            continue;
        }

        if (send_line(fd,
                      "ERROR: Invalid command or question number.\n") == -1)
            break;
    }

    if (submitted) {
        int score = 0;
        int answered = 0;

        for (int i = 0; i < QUESTION_COUNT; i++) {
            if (answers[i] != '\0')
                answered++;

            if (answers[i] == questions[i].correct)
                score++;
        }

        snprintf(message, sizeof(message),
                 "RESULT: Student=%s Score=%d/%d Answered=%d/%d\n",
                 student_id, score, QUESTION_COUNT,
                 answered, QUESTION_COUNT);

        send_line(fd, message);
    }
}

static void *client_thread(void *argument)
{
    ClientArgs *args = argument;
    int fd = args->fd;
    char student_id[MAX_ID_LENGTH + 1];
    LineReader reader = args->reader;

    snprintf(student_id, sizeof(student_id), "%s", args->student_id);
    free(args);

    pthread_mutex_lock(&log_mutex);
    printf("[server] Student %s connected.\n", student_id);
    fflush(stdout);
    pthread_mutex_unlock(&log_mutex);

    handle_exam(fd, student_id, &reader);
    close(fd);
    unregister_student(student_id);

    pthread_mutex_lock(&log_mutex);
    printf("[server] Student %s disconnected.\n", student_id);
    fflush(stdout);
    pthread_mutex_unlock(&log_mutex);

    return NULL;
}

int main(void)
{
    signal(SIGPIPE, SIG_IGN);

    int server_fd = socket(AF_INET, SOCK_STREAM, 0);

    if (server_fd == -1) {
        perror("socket");
        return EXIT_FAILURE;
    }

    int opt = 1;

    if (setsockopt(server_fd, SOL_SOCKET, SO_REUSEADDR,
                   &opt, sizeof(opt)) == -1) {
        perror("setsockopt");
        close(server_fd);
        return EXIT_FAILURE;
    }

    struct sockaddr_in address;
    memset(&address, 0, sizeof(address));

    address.sin_family = AF_INET;
    address.sin_addr.s_addr = htonl(INADDR_ANY);
    address.sin_port = htons(PORT);

    if (bind(server_fd, (struct sockaddr *)&address,
             sizeof(address)) == -1) {
        perror("bind");
        close(server_fd);
        return EXIT_FAILURE;
    }

    if (listen(server_fd, BACKLOG) == -1) {
        perror("listen");
        close(server_fd);
        return EXIT_FAILURE;
    }

    printf("Online Examination Server listening on port %d\n", PORT);
    fflush(stdout);

    for (;;) {
        struct sockaddr_in client_address;
        socklen_t address_length = sizeof(client_address);

        int client_fd = accept(server_fd,
                               (struct sockaddr *)&client_address,
                               &address_length);

        if (client_fd == -1) {
            if (errno == EINTR)
                continue;

            perror("accept");
            continue;
        }

        char initial_message[BUFFER_SIZE];
        LineReader reader = {0};
        ssize_t n = read_line(client_fd, &reader, initial_message,
                              sizeof(initial_message), NULL, 10000);

        if (n <= 0 ||
            strncmp(initial_message, "STUDENT ", 8) != 0) {
            send_line(client_fd,
                      "ERROR: First send STUDENT <your_id>.\n");
            close(client_fd);
            continue;
        }

        const char *student_id = initial_message + 8;

        if (!valid_student_id(student_id)) {
            send_line(client_fd, "ERROR: Invalid student ID.\n");
            close(client_fd);
            continue;
        }

        int registration = register_student(student_id);

        if (registration == -1) {
            send_line(client_fd,
                      "ERROR: Student ID already has an active session.\n");
            close(client_fd);
            continue;
        }

        if (registration == -2) {
            send_line(client_fd,
                      "ERROR: Server student capacity reached.\n");
            close(client_fd);
            continue;
        }

        ClientArgs *args = malloc(sizeof(*args));

        if (args == NULL) {
            perror("malloc");
            unregister_student(student_id);
            close(client_fd);
            continue;
        }

        args->fd = client_fd;
        args->reader = reader;
        snprintf(args->student_id, sizeof(args->student_id),
                 "%s", student_id);

        pthread_t thread;
        int error = pthread_create(&thread, NULL, client_thread, args);

        if (error != 0) {
            fprintf(stderr, "pthread_create: %s\n", strerror(error));
            unregister_student(student_id);
            free(args);
            close(client_fd);
            continue;
        }

        pthread_detach(thread);

        printf("[server] Accepted connection from %s\n",
               inet_ntoa(client_address.sin_addr));
        fflush(stdout);
    }

    close(server_fd);
    return EXIT_SUCCESS;
}
