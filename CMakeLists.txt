cmake_minimum_required(VERSION 3.18)
project(duckclaw)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# Pybind11 (required)
find_package(pybind11 REQUIRED)

# DuckDB: use FetchContent if not already found (e.g. from vcpkg or system)
if(NOT TARGET duckdb_static AND NOT TARGET duckdb)
    include(FetchContent)
    FetchContent_Declare(
        duckdb
        URL https://github.com/duckdb/duckdb/archive/refs/tags/v1.1.3.tar.gz
    )
    set(BUILD_SHELL OFF CACHE BOOL "" FORCE)
    set(BUILD_UNITTESTS OFF CACHE BOOL "" FORCE)
    set(BUILD_BENCHMARKS OFF CACHE BOOL "" FORCE)
    set(DISABLE_BUILTIN_EXTENSIONS ON CACHE BOOL "" FORCE)
    FetchContent_MakeAvailable(duckdb)
endif()

# Our headers
include_directories(${CMAKE_CURRENT_SOURCE_DIR}/include)

# Python extension module
pybind11_add_module(duckclaw src/bindings.cpp src/duckclaw.cpp)
target_include_directories(duckclaw PRIVATE ${CMAKE_CURRENT_SOURCE_DIR}/include)
if(TARGET duckdb_static)
    target_include_directories(duckclaw PRIVATE ${duckdb_SOURCE_DIR}/src/include)
    target_link_libraries(duckclaw PRIVATE duckdb_static)
else()
    target_link_libraries(duckclaw PRIVATE duckdb)
endif()

# Apple Silicon
if(APPLE)
    target_compile_options(duckclaw PRIVATE "-march=armv8.5-a+sha3+sm4")
endif()