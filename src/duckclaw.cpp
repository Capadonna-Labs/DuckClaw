#include "duckclaw.hpp"

namespace duckclaw {

DuckClaw::DuckClaw(const std::string& db_path) : db(db_path), con(db) {
    if (db_path.empty()) {
        throw std::runtime_error("La ruta de la base de datos no puede estar vacía.");
    }
}

std::vector<std::map<std::string, std::string>> DuckClaw::query(const std::string& sql) {
    auto result = con.Query(sql);
    if (result->HasError()) {
        throw std::runtime_error("DuckDB Query Error: " + result->GetError());
    }

    std::vector<std::map<std::string, std::string>> rows;
    const auto& names = result->names;

    for (auto& row : *result) {
        std::map<std::string, std::string> row_map;
        for (size_t col_idx = 0; col_idx < names.size(); col_idx++) {
            row_map[names[col_idx]] = row.GetValue<duckdb::Value>(col_idx).ToString();
        }
        rows.push_back(row_map);
    }
    return rows;
}

void DuckClaw::execute(const std::string& sql) {
    auto result = con.Query(sql);
    if (result->HasError()) {
        throw std::runtime_error("DuckDB Execute Error: " + result->GetError());
    }
}

std::string DuckClaw::get_version() const {
    return duckdb::DuckDB::LibraryVersion();
}

} // namespace duckclaw