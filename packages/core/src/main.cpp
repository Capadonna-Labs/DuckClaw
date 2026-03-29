#include "duckclaw.hpp"
#include <iostream>

int main() {
    try {
        // 1. Inicializar la conexión a una base de datos de prueba
        std::cout << "Iniciando DuckClaw..." << std::endl;
        duckclaw::DuckClaw db("test_database.duckdb");

        // 2. Imprimir la versión de DuckDB
        std::cout << "Versión de DuckDB: " << db.get_version() << std::endl;

        // 3. Crear una tabla de prueba y meter datos
        db.execute("CREATE TABLE IF NOT EXISTS usuarios (id INTEGER, nombre VARCHAR);");
        db.execute("INSERT INTO usuarios VALUES (1, 'Juan'), (2, 'Leila');");

        // 4. Hacer una consulta (retorna JSON gracias a tu método)
        std::string json_result = db.query("SELECT * FROM usuarios;");
        std::cout << "Resultado JSON: " << json_result << std::endl;

        // 5. Probar la creación del Data Lake (exportar a Parquet)
        std::cout << "Exportando a Data Lake en ./datalake_out/ ..." << std::endl;
        db.create_datalake("./datalake_out");
        
        std::cout << "¡Ejecución exitosa!" << std::endl;

    } catch (const std::exception& e) {
        std::cerr << "Error crítico: " << e.what() << std::endl;
        return 1;
    }

    return 0;
}