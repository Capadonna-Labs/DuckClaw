#ifndef DUCKCLAW_EDGE_CORE_H
#define DUCKCLAW_EDGE_CORE_H

#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/**
 * @brief Estructura de telemetría genérica para dispositivos Edge.
 */
typedef struct {
    char device_id[16];   // Identificador único (ej. "NODE-01")
    float data[8];        // Array genérico para hasta 8 lecturas de sensores
    int64_t timestamp_ms; // Timestamp inyectado por el host
    int status_code;      // 0 = OK, < 0 = Error
} EdgeTelemetry;

/**
 * @brief Lee métricas del sistema host (VPS/Mac) usando llamadas POSIX.
 * @param output Puntero a la estructura de telemetría.
 * @return int 0 si es exitoso.
 */
int read_system_frame(EdgeTelemetry* output);

int init_serial_port(const char* port_name, int baud_rate);
int read_sensor_frame(int fd, EdgeTelemetry* output);
void close_serial_port(int fd);

#ifdef __cplusplus
}
#endif

#endif // DUCKCLAW_EDGE_CORE_H
