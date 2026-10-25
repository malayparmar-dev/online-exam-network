#define _POSIX_C_SOURCE 200809L

#include <arpa/inet.h>
#include <errno.h>
#include <netinet/in.h>
#include <pthread.h>
#include <signal.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/socket.h>
#include <sys/time.h>
#include <sys/stat.h>
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
static pthread_mutex_t metrics_mutex = PTHREAD_MUTEX_INITIALIZER;

static char active_students[MAX_STUDENTS][MAX_ID_LENGTH + 1];
static size_t active_count;
static int server_port = PORT;
static int exam_duration_seconds = EXAM_DURATION_SECONDS;
static const char *metrics_path = "results/app_metrics.csv";

static double elapsed_ms(const struct timespec *start)
{
    struct timespec now;

    if (start == NULL || clock_gettime(CLOCK_MONOTONIC, &now) == -1)
        return 0.0;

    return ((double)(now.tv_sec - start->tv_sec) * 1000.0) +
           ((double)(now.tv_nsec - start->tv_nsec) / 1000000.0);
}

static void csv_write_field(FILE *file, const char *value)
{
    fputc('"', file);
    for (const char *p = value; *p != '\0'; p++) {
        if (*p == '"')
            fputc('"', file);
        fputc(*p, file);
    }
    fputc('"', file);
}

static void record_metric(const char *student_id, const char *event,
                          const struct timespec *start, const char *detail)
{
    struct timespec now;
    struct tm utc;
    char timestamp[32];
    FILE *file;

    if (clock_gettime(CLOCK_REALTIME, &now) == -1 ||
        gmtime_r(&now.tv_sec, &utc) == NULL)
        return;

    if (strftime(timestamp, sizeof(timestamp), "%Y-%m-%dT%H:%M:%S", &utc) == 0)
        return;

    pthread_mutex_lock(&metrics_mutex);
    file = fopen(metrics_path, "a+");
    if (file == NULL) {
        pthread_mutex_unlock(&metrics_mutex);
        perror("open application metrics file");
        return;
    }

    if (fseek(file, 0, SEEK_END) == 0 && ftell(file) == 0)
        fputs("timestamp_utc,student,event,latency_ms,detail\n", file);

    fputc('"', file);
    fprintf(file, "%s.%03ldZ", timestamp, now.tv_nsec / 1000000L);
    fputc('"', file);
    fputc(',', file);
    csv_write_field(file, student_id != NULL ? student_id : "unknown");
    fputc(',', file);
    csv_write_field(file, event);
    fprintf(file, ",%.3f,", elapsed_ms(start));
    csv_write_field(file, detail != NULL ? detail : "");
    fputc('\n', file);
    fflush(file);
    fclose(file);
    pthread_mutex_unlock(&metrics_mutex);
}

static int parse_positive_env(const char *name, int fallback, int maximum)
{
    const char *value = getenv(name);
    char *end = NULL;
    long parsed;

    if (value == NULL || *value == '\0')
        return fallback;

    errno = 0;
    parsed = strtol(value, &end, 10);
    if (errno != 0 || end == value || *end != '\0' ||
        parsed < 1 || parsed > maximum) {
        fprintf(stderr, "Invalid %s value: %s\n", name, value);
        return -1;
    }

    return (int)parsed;
}

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

static int score_answers(const char *answers, int *answered)
{
    int score = 0;

    *answered = 0;
    for (int i = 0; i < QUESTION_COUNT; i++) {
        if (answers[i] != '\0')
            (*answered)++;
        if (answers[i] == questions[i].correct)
            score++;
    }

    return score;
}

static void finish_exam(int fd, const char *student_id,
                        const char *answers, bool timed_out,
                        const struct timespec *request_start)
{
    char response[BUFFER_SIZE];
    int answered;
    int score = score_answers(answers, &answered);

    if (timed_out) {
        snprintf(response, sizeof(response),
                 "TIMEOUT: Exam deadline reached. RESULT: Student=%s Score=%d/%d Answered=%d/%d\n",
                 student_id, score, QUESTION_COUNT,
                 answered, QUESTION_COUNT);
        record_metric(student_id, "timeout_finalized", NULL,
                      "attempt automatically scored at deadline");
    } else {
        snprintf(response, sizeof(response),
                 "RESULT: Student=%s Score=%d/%d Answered=%d/%d\n",
                 student_id, score, QUESTION_COUNT,
                 answered, QUESTION_COUNT);
        record_metric(student_id, "submitted", request_start,
                      "attempt finalized and scored");
    }

    send_line(fd, response);
}

static void handle_exam(int fd, const char *student_id,
                         LineReader *reader)
{
    char message[BUFFER_SIZE];
    char answers[QUESTION_COUNT] = {0};
    struct timespec deadline = {0, 0};
    bool started = false;
    bool finalized = false;

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
    deadline.tv_sec += exam_duration_seconds;

    record_metric(student_id, "started", NULL, "exam timer started");

    snprintf(message, sizeof(message),
             "STARTED: Duration is %d seconds.\n", exam_duration_seconds);
    if (send_line(fd, message) == -1)
        return;

    while (started && !finalized) {
        if (deadline_reached(&deadline)) {
            finish_exam(fd, student_id, answers, true, NULL);
            finalized = true;
            break;
        }

        n = read_line(fd, reader, message, sizeof(message),
                      &deadline, 2000);

        if (n == -3) {
            finish_exam(fd, student_id, answers, true, NULL);
            finalized = true;
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

        struct timespec request_start;
        (void)clock_gettime(CLOCK_MONOTONIC, &request_start);

        if (deadline_reached(&deadline)) {
            finish_exam(fd, student_id, answers, true, NULL);
            finalized = true;
            break;
        }

        if (strcmp(message, "SUBMIT") == 0) {
            finish_exam(fd, student_id, answers, false, &request_start);
            finalized = true;
            break;
        }

        if (strcmp(message, "QUIT") == 0) {
            send_line(fd, "QUIT: Examination abandoned.\n");
            record_metric(student_id, "abandoned", NULL,
                          "student disconnected without submitting");
            finalized = true;
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

            record_metric(student_id, "question", &request_start, message);

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

            record_metric(student_id, "answer", &request_start, message);

            continue;
        }

        if (send_line(fd,
                      "ERROR: Invalid command or question number.\n") == -1)
            break;
        record_metric(student_id, "invalid_request", &request_start, message);
    }
}

static void *client_thread(void *argument)
{
    ClientArgs *args = argument;
    int fd = args->fd;
    char student_id[MAX_ID_LENGTH + 1];
    LineReader reader = args->reader;
    char initial_message[BUFFER_SIZE];
    struct sockaddr_in peer_address;
    socklen_t peer_length = sizeof(peer_address);
    bool registered = false;
    ssize_t n;

    free(args);

    n = read_line(fd, &reader, initial_message, sizeof(initial_message),
                  NULL, 10000);
    if (n <= 0 || strncmp(initial_message, "STUDENT ", 8) != 0) {
        send_line(fd, "ERROR: First send STUDENT <your_id>.\n");
        record_metric("unknown", "invalid_login", NULL,
                      "missing STUDENT identity line");
        close(fd);
        return NULL;
    }

    const char *requested_id = initial_message + 8;
    if (!valid_student_id(requested_id)) {
        send_line(fd, "ERROR: Invalid student ID.\n");
        record_metric("unknown", "invalid_login", NULL,
                      "invalid student ID format");
        close(fd);
        return NULL;
    }

    int registration = register_student(requested_id);
    if (registration == -1) {
        send_line(fd, "ERROR: Student ID already has an active session.\n");
        record_metric(requested_id, "login_rejected", NULL,
                      "duplicate active student ID");
        close(fd);
        return NULL;
    }
    if (registration == -2) {
        send_line(fd, "ERROR: Server student capacity reached.\n");
        record_metric(requested_id, "login_rejected", NULL,
                      "server capacity reached");
        close(fd);
        return NULL;
    }

    registered = true;
    snprintf(student_id, sizeof(student_id), "%s", requested_id);
    if (getpeername(fd, (struct sockaddr *)&peer_address, &peer_length) == 0) {
        char address[INET_ADDRSTRLEN];
        if (inet_ntop(AF_INET, &peer_address.sin_addr,
                      address, sizeof(address)) != NULL) {
            pthread_mutex_lock(&log_mutex);
            printf("[server] Accepted connection from %s\n", address);
            fflush(stdout);
            pthread_mutex_unlock(&log_mutex);
        }
    }

    pthread_mutex_lock(&log_mutex);
    printf("[server] Student %s connected.\n", student_id);
    fflush(stdout);
    pthread_mutex_unlock(&log_mutex);
    record_metric(student_id, "connected", NULL, "TCP session accepted");

    handle_exam(fd, student_id, &reader);
    close(fd);
    if (registered)
        unregister_student(student_id);
    record_metric(student_id, "disconnected", NULL,
                  "TCP session closed");

    pthread_mutex_lock(&log_mutex);
    printf("[server] Student %s disconnected.\n", student_id);
    fflush(stdout);
    pthread_mutex_unlock(&log_mutex);

    return NULL;
}

int main(void)
{
    server_port = parse_positive_env("EXAM_PORT", PORT, 65535);
    exam_duration_seconds = parse_positive_env(
        "EXAM_DURATION_SECONDS", EXAM_DURATION_SECONDS, 86400);
    if (server_port < 0 || exam_duration_seconds < 0)
        return EXIT_FAILURE;

    const char *configured_metrics = getenv("EXAM_METRICS_FILE");
    if (configured_metrics != NULL && *configured_metrics != '\0')
        metrics_path = configured_metrics;
    else if (mkdir("results", 0775) == -1 && errno != EEXIST) {
        perror("create results directory");
        return EXIT_FAILURE;
    }

    FILE *metrics = fopen(metrics_path, "a+");
    if (metrics == NULL) {
        perror("open application metrics file");
        return EXIT_FAILURE;
    }
    if (fseek(metrics, 0, SEEK_END) == 0 && ftell(metrics) == 0)
        fputs("timestamp_utc,student,event,latency_ms,detail\n", metrics);
    fclose(metrics);

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
    address.sin_port = htons((uint16_t)server_port);

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

    printf("Online Examination Server listening on port %d\n", server_port);
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

        ClientArgs *args = malloc(sizeof(*args));

        if (args == NULL) {
            perror("malloc");
            close(client_fd);
            continue;
        }

        args->fd = client_fd;
        args->reader = (LineReader){0};

        pthread_t thread;
        int error = pthread_create(&thread, NULL, client_thread, args);

        if (error != 0) {
            fprintf(stderr, "pthread_create: %s\n", strerror(error));
            free(args);
            close(client_fd);
            continue;
        }

        pthread_detach(thread);

        char address_text[INET_ADDRSTRLEN];
        if (inet_ntop(AF_INET, &client_address.sin_addr, address_text,
                      sizeof(address_text)) != NULL)
            printf("[server] Accepted connection from %s\n", address_text);
        fflush(stdout);
    }

    close(server_fd);
    return EXIT_SUCCESS;
}
