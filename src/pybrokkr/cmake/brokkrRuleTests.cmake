# The rule tests every repository of the chain has (docs/directory_layout.rst), labelled `rules`.

# Registers, for the project that calls it (in its tests/CMakeLists.txt):
#
#   layout       every tracked file against the directory layout (python -m pybrokkr.layout)
#   registered   every tracked source built by a target, every test script run (python -m pybrokkr.registered)
#
# Both read the tracked files, so nothing is registered outside a git checkout (a source archive). `registered` reads
# the sources of every target, which this writes to <build>/brokkr/sources.txt once the project's directories are
# all read. A rule added to brokkr is added here: a library gets it with the brokkr it builds with.
#
#     brokkr_add_rule_tests()
function(brokkr_add_rule_tests)
    if(NOT EXISTS "${PROJECT_SOURCE_DIR}/.git")
        return()
    endif()
    if(NOT Python_EXECUTABLE)
        find_package(Python 3.11 REQUIRED COMPONENTS Interpreter)
    endif()
    set(sources "${PROJECT_BINARY_DIR}/brokkr/sources.txt")
    add_test(NAME layout COMMAND "${Python_EXECUTABLE}" -m pybrokkr.layout "${PROJECT_SOURCE_DIR}")
    add_test(NAME registered COMMAND "${Python_EXECUTABLE}" -m pybrokkr.registered --sources "${sources}"
                                     "${PROJECT_SOURCE_DIR}")
    set_tests_properties(layout registered PROPERTIES LABELS rules)
    # A deferred call's arguments are expanded when it runs, in the directory's scope, where this function's variables
    # are gone: the paths are written into the call now.
    cmake_language(EVAL CODE "cmake_language(DEFER DIRECTORY [[${PROJECT_SOURCE_DIR}]] CALL _brokkr_write_sources [[${PROJECT_SOURCE_DIR}]] [[${sources}]])")
endfunction()

# The sources of every target of `directory` and of the directories below it, as absolute paths.
function(_brokkr_collect_sources directory out_var)
    set(found "")
    get_property(targets DIRECTORY "${directory}" PROPERTY BUILDSYSTEM_TARGETS)
    foreach(target IN LISTS targets)
        get_target_property(target_sources ${target} SOURCES)
        get_target_property(source_dir ${target} SOURCE_DIR)
        if(NOT target_sources)
            continue()
        endif()
        foreach(source IN LISTS target_sources)
            if(source MATCHES "^\\$<")
                continue()
            endif()
            cmake_path(ABSOLUTE_PATH source BASE_DIRECTORY "${source_dir}" NORMALIZE OUTPUT_VARIABLE path)
            list(APPEND found "${path}")
        endforeach()
    endforeach()
    get_property(subdirectories DIRECTORY "${directory}" PROPERTY SUBDIRECTORIES)
    foreach(subdirectory IN LISTS subdirectories)
        _brokkr_collect_sources("${subdirectory}" below)
        list(APPEND found ${below})
    endforeach()
    set(${out_var} "${found}" PARENT_SCOPE)
endfunction()

function(_brokkr_write_sources directory output)
    _brokkr_collect_sources("${directory}" sources)
    list(REMOVE_DUPLICATES sources)
    list(JOIN sources "\n" text)
    file(WRITE "${output}" "${text}\n")
endfunction()
