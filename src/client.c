#define _POSIX_C_SOURCE 200809L

#include <arpa/inet.h>
#include <errno.h>
#include <netinet/in.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/socket.h>
#include <unistd.h>
#include "protocol.h"

#define DEFAULT_PORT 8080
#define BUFFER_SIZE 1024
#define QUESTION_COUNT 5
#define MAX_ID_LENGTH 32

static int send_line(int fd, const char *message)
{
    size_t length = strlen(message);
    size_t sent = 0;

    while (sent < length) {
        ssize_t n = send(fd, message + sent, length - sent, MSG_NOSIGNAL);

        if (n < 0) {
            if (errno == EINTR) {
                continue;
            }
            return -1;
        }

        if (n == 0) {
            return -1;
        }

        sent += (size_t)n;
    }

    return 0;
}

static int receive_line(int fd, LineReader *reader,
                        char *buffer, size_t capacity)
{
    ssize_t n = read_line(fd, reader, buffer, capacity, NULL, 0);

    if (n == -2) {
        fprintf(stderr, "\nServer response exceeded the message limit.\n");
        return -1;
    }

    if (n <= 0) {
        fprintf(stderr, "\nConnection closed or communication failed.\n");
        return -1;
    }

    return 0;
}

static int valid_student_id(const char *id)
{
    size_t length = strlen(id);

    if (length == 0 || length > MAX_ID_LENGTH) {
        return 0;
    }

    for (size_t i = 0; i < length; i++) {
        if (!((id[i] >= 'A' && id[i] <= 'Z') ||
              (id[i] >= 'a' && id[i] <= 'z') ||
              (id[i] >= '0' && id[i] <= '9') ||
              id[i] == '_' || id[i] == '-')) {
            return 0;
        }
    }

    return 1;
}

static int receive_question(int fd, LineReader *reader,
                            int question_number)
{
    char command[BUFFER_SIZE];
    char response[BUFFER_SIZE];

    snprintf(command, sizeof(command), "GET %d\n", question_number);

    if (send_line(fd, command) == -1 ||
        receive_line(fd, reader, response, sizeof(response)) == -1) {
        perror("Question request");
        return -1;
    }

    if (strncmp(response, "QUESTION ", 9) == 0) {
        printf("\n%s\n", response);
        return 0;
    }

    if (strncmp(response, "TIMEOUT:", 8) == 0) {
        printf("\n%s\n", response);
        return 1;
    }

    fprintf(stderr, "Unexpected response to question request: %s\n", response);
    return -1;
}

static void print_help(void)
{
    puts("\nCommands:");
    puts("  1-5  View a question");
    puts("  A-D  Select an answer for the current question");
    puts("  N    Next question");
    puts("  P    Previous question");
    puts("  S    Submit examination");
    puts("  Q    Disconnect without submitting");
}

int main(int argc, char *argv[])
{
    const char *server_ip = "10.0.0.10";
    int server_port = DEFAULT_PORT;

    if (argc > 3) {
        fprintf(stderr, "Usage: %s [server-ip [port]]\n", argv[0]);
        return EXIT_FAILURE;
    }

    if (argc == 2) {
        server_ip = argv[1];
    } else if (argc == 3) {
        server_ip = argv[1];
    }

    if (argc == 3) {
        char *end = NULL;
        long parsed = strtol(argv[2], &end, 10);
        if (end == argv[2] || *end != '\0' || parsed < 1 || parsed > 65535) {
            fprintf(stderr, "Invalid TCP port. Use a value from 1 to 65535.\n");
            return EXIT_FAILURE;
        }
        server_port = (int)parsed;
    }

    char student_id[MAX_ID_LENGTH + 2];

    printf("====================================\n");
    printf("      ONLINE EXAMINATION SYSTEM\n");
    printf("====================================\n");
    printf("Enter student ID: ");

    if (fgets(student_id, sizeof(student_id), stdin) == NULL) {
        return EXIT_FAILURE;
    }

    student_id[strcspn(student_id, "\r\n")] = '\0';

    if (!valid_student_id(student_id)) {
        fprintf(stderr,
                "Invalid ID. Use 1-%d letters, digits, hyphens or underscores.\n",
                MAX_ID_LENGTH);
        return EXIT_FAILURE;
    }

    int sock = socket(AF_INET, SOCK_STREAM, 0);

    if (sock == -1) {
        perror("socket");
        return EXIT_FAILURE;
    }

    struct sockaddr_in server_address;
    memset(&server_address, 0, sizeof(server_address));

    server_address.sin_family = AF_INET;
    server_address.sin_port = htons((uint16_t)server_port);

    if (inet_pton(AF_INET, server_ip, &server_address.sin_addr) != 1) {
        fprintf(stderr, "Invalid server IP address.\n");
        close(sock);
        return EXIT_FAILURE;
    }

    printf("Connecting to %s:%d...\n", server_ip, server_port);

    if (connect(sock, (struct sockaddr *)&server_address,
                sizeof(server_address)) == -1) {
        perror("connect");
        close(sock);
        return EXIT_FAILURE;
    }

    char command[BUFFER_SIZE];
    char response[BUFFER_SIZE];
    LineReader reader = {0};

    snprintf(command, sizeof(command), "STUDENT %s\n", student_id);

    if (send_line(sock, command) == -1 ||
        receive_line(sock, &reader, response, sizeof(response)) == -1) {
        close(sock);
        return EXIT_FAILURE;
    }

    if (strncmp(response, "ERROR:", 6) == 0) {
        printf("%s\n", response);
        close(sock);
        return EXIT_FAILURE;
    }

    printf("\n%s\n", response);

    if (receive_line(sock, &reader, response, sizeof(response)) == -1) {
        close(sock);
        return EXIT_FAILURE;
    }

    printf("%s\n", response);

    printf("\nType START to begin: ");

    if (fgets(command, sizeof(command), stdin) == NULL) {
        close(sock);
        return EXIT_FAILURE;
    }

    command[strcspn(command, "\r\n")] = '\0';

    if (strcmp(command, "START") != 0) {
        puts("Examination not started.");
        close(sock);
        return EXIT_SUCCESS;
    }

    if (send_line(sock, "START\n") == -1 ||
        receive_line(sock, &reader, response, sizeof(response)) == -1) {
        close(sock);
        return EXIT_FAILURE;
    }

    printf("\n%s\n", response);

    if (strncmp(response, "ERROR:", 6) == 0) {
        close(sock);
        return EXIT_FAILURE;
    }

    int current_question = 1;
    bool finished = false;
    int exit_status = EXIT_SUCCESS;

    print_help();

    while (!finished) {
        int question_status = receive_question(sock, &reader, current_question);
        if (question_status == 1) {
            finished = true;
            break;
        }
        if (question_status == -1) {
            exit_status = EXIT_FAILURE;
            break;
        }

        printf("\nStudent ID: %s | Question: %d/%d\n",
               student_id, current_question, QUESTION_COUNT);
        printf("Enter A-D to answer, N/P to navigate, S to submit, H for help, Q to quit: ");

        if (fgets(command, sizeof(command), stdin) == NULL) {
            fprintf(stderr, "\nInput ended unexpectedly.\n");
            exit_status = EXIT_FAILURE;
            break;
        }

        command[strcspn(command, "\r\n")] = '\0';

        if (strlen(command) == 1 &&
            command[0] >= 'a' && command[0] <= 'z') {
            command[0] = (char)(command[0] - 'a' + 'A');
        }

        if (strlen(command) == 1 &&
            command[0] >= 'A' && command[0] <= 'D') {
            char answer_command[64];

            snprintf(answer_command, sizeof(answer_command),
                     "ANSWER %d %c\n", current_question, command[0]);

            if (send_line(sock, answer_command) == -1 ||
                receive_line(sock, &reader, response, sizeof(response)) == -1) {
                perror("Answer request");
                exit_status = EXIT_FAILURE;
                break;
            }

            if (strncmp(response, "OK:", 3) == 0) {
                printf("%s\n", response);
            } else if (strncmp(response, "TIMEOUT:", 8) == 0) {
                printf("%s\n", response);
                finished = true;
                break;
            } else {
                fprintf(stderr, "Unexpected response after answering: %s\n",
                        response);
                exit_status = EXIT_FAILURE;
                break;
            }
        } else if (strcmp(command, "N") == 0) {
            if (current_question < QUESTION_COUNT) {
                current_question++;
            } else {
                puts("Already at the last question.");
            }
        } else if (strcmp(command, "P") == 0) {
            if (current_question > 1) {
                current_question--;
            } else {
                puts("Already at the first question.");
            }
        } else if (strcmp(command, "S") == 0) {
            printf("Submit your examination? Type YES to confirm: ");

            if (fgets(command, sizeof(command), stdin) == NULL) {
                fprintf(stderr, "\nInput ended unexpectedly.\n");
                exit_status = EXIT_FAILURE;
                break;
            }

            command[strcspn(command, "\r\n")] = '\0';

            if (strcmp(command, "YES") != 0) {
                continue;
            }

            if (send_line(sock, "SUBMIT\n") == -1 ||
                receive_line(sock, &reader, response, sizeof(response)) == -1) {
                perror("Submission request");
                exit_status = EXIT_FAILURE;
                break;
            }

            if (strncmp(response, "RESULT:", 7) == 0) {
                printf("\n%s\n", response);
                finished = true;
            } else if (strncmp(response, "TIMEOUT:", 8) == 0) {
                printf("\n%s\n", response);
                finished = true;
            } else {
                fprintf(stderr, "Unexpected response after submission: %s\n",
                        response);
                exit_status = EXIT_FAILURE;
                break;
            }
        } else if (strcmp(command, "Q") == 0) {
            if (send_line(sock, "QUIT\n") == -1 ||
                receive_line(sock, &reader, response, sizeof(response)) == -1) {
                perror("Quit request");
                exit_status = EXIT_FAILURE;
                break;
            }

            if (strncmp(response, "QUIT:", 5) == 0) {
                printf("%s\n", response);
                finished = true;
            } else if (strncmp(response, "TIMEOUT:", 8) == 0) {
                printf("%s\n", response);
                finished = true;
            } else {
                fprintf(stderr, "Unexpected response to quit request: %s\n",
                        response);
                exit_status = EXIT_FAILURE;
                break;
            }
        } else if (strcmp(command, "H") == 0) {
            print_help();
        } else if (strlen(command) == 1 &&
                   command[0] >= '1' && command[0] <= '5') {
            current_question = command[0] - '0';
        } else {
            puts("Invalid command. Enter H to see the available commands.");
        }
    }

    close(sock);
    puts("\nClient disconnected.");

    return exit_status;
}

