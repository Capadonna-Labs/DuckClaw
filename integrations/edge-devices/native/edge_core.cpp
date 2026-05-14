#include "edge_core.h"
#include <iostream>
#include <fcntl.h>
#include <termios.h>
#include <unistd.h>
#include <cstring>
#include <chrono>
#include <stdlib.h> // Para getloadavg

extern "C" {

int init_serial_port(const char* port_name, int baud_rate) {
    int fd = open(port_name, O_RDWR | O_NOCTTY | O_SYNC);
    if (fd < 0) return -1;

    struct termios tty;
    if (tcgetattr(fd, &tty) != 0) { close(fd); return -2; }

    speed_t speed = B115200;
    if (baud_rate == 9600) speed = B9600;
    else if (baud_rate == 57600) speed = B57600;

    cfsetospeed(&tty, speed);
    cfsetispeed(&tty, speed);

    tty.c_cflag &= ~PARENB; tty.c_cflag &= ~CSTOPB;
    tty.c_cflag &= ~CSIZE; tty.c_cflag |= CS8;
    tty.c_cflag &= ~CRTSCTS; tty.c_cflag |= CREAD | CLOCAL;
    tty.c_lflag &= ~(ICANON | ECHO | ECHOE | ISIG);
    tty.c_iflag &= ~(IXON | IXOFF | IXANY);
    tty.c_iflag &= ~(IGNBRK|BRKINT|PARMRK|ISTRIP|INLCR|IGNCR|ICRNL);
    tty.c_oflag &= ~OPOST;
    tty.c_cc[VMIN] = 0; tty.c_cc[VTIME] = 10;

    if (tcsetattr(fd, TCSANOW, &tty) != 0) { close(fd); return -3; }
    return fd;
}

int read_sensor_frame(int fd, EdgeTelemetry* output) {
    /*
     * Protocolo Binario Genérico (51 bytes total):
     * [0]     Cabecera: 0xAA
     * [1-16]  Device ID (16 bytes)
     * [17-48] Data (8 x Float 32-bit = 32 bytes)
     * [49]    Checksum (XOR bytes 1 al 48)
     * [50]    Pie: 0xFF
     */
    unsigned char buffer[50];
    unsigned char c;
    int n;

    while (true) {
        n = read(fd, &c, 1);
        if (n <= 0) return -1;
        if (c == 0xAA) break;
    }

    int bytes_read = 0;
    while (bytes_read < 50) {
        n = read(fd, buffer + bytes_read, 50 - bytes_read);
        if (n <= 0) return -1;
        bytes_read += n;
    }

    if (buffer[49] != 0xFF) return -2;

    unsigned char crc = 0;
    for (int i = 0; i < 48; i++) crc ^= buffer[i];
    if (crc != buffer[48]) return -3;

    std::memcpy(output->device_id, buffer, 16);
    output->device_id[15] = '\0';

    std::memcpy(output->data, buffer + 16, 32);

    auto now = std::chrono::system_clock::now();
    output->timestamp_ms = std::chrono::duration_cast<std::chrono::milliseconds>(now.time_since_epoch()).count();
    output->status_code = 0;

    return 0;
}

int read_system_frame(EdgeTelemetry* output) {
    std::strcpy(output->device_id, "VPS-CORE-01");

    double loadavg[3];
    getloadavg(loadavg, 3);
    output->data[0] = static_cast<float>(loadavg[0]);
    output->data[1] = static_cast<float>(loadavg[1]);
    output->data[2] = static_cast<float>(loadavg[2]);

    long pages = sysconf(_SC_PHYS_PAGES);
    long page_size = sysconf(_SC_PAGE_SIZE);
    output->data[3] = static_cast<float>(pages * page_size) / (1024 * 1024);

    long avpages = sysconf(_SC_AVPHYS_PAGES);
    output->data[4] = static_cast<float>(avpages * page_size) / (1024 * 1024);

    output->data[5] = 0.0f;
    output->data[6] = 0.0f;
    output->data[7] = 0.0f;

    auto now = std::chrono::system_clock::now();
    output->timestamp_ms = std::chrono::duration_cast<std::chrono::milliseconds>(
        now.time_since_epoch()
    ).count();

    output->status_code = 0;

    return 0;
}

void close_serial_port(int fd) {
    if (fd >= 0) close(fd);
}

} // extern "C"
