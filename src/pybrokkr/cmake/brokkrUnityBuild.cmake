# Unity batches by directory (brokkr's template rules, rule 11).

# Compiles the sources of `target` that sit directly in each of DIRECTORIES (relative to the target's source directory)
# as one translation unit per directory, where ENABLED is true. Sources of one directory that work with the same types
# share most of their instantiations; batched, they compile them once. List a directory only while its batch stays
# below the heaviest translation unit of the build (merge its sources into one file and measure). A batch puts its
# sources' file-local names into one translation unit: each source keeps its own in a namespace of its own. Disabled,
# every source compiles on its own and compile_commands.json lists each, as clang-tidy needs. With BATCH_SIZE, a
# directory's sources are batched by at most that many, in name order: for a directory whose sources share much but
# exceed the heaviest translation unit merged.
#
#     brokkr_unity_directories(_pyfoo ENABLED ${FOO_UNITY_BUILD} DIRECTORIES pyfoo/a pyfoo/b)
#     brokkr_unity_directories(_pyfoo ENABLED ${FOO_UNITY_BUILD} BATCH_SIZE 10 DIRECTORIES pyfoo/c)
function(brokkr_unity_directories target)
    cmake_parse_arguments(PARSE_ARGV 1 ARG "" "ENABLED;BATCH_SIZE" "DIRECTORIES")
    if(NOT ARG_ENABLED)
        return()
    endif()
    get_target_property(sources ${target} SOURCES)
    list(SORT sources)
    get_target_property(source_dir ${target} SOURCE_DIR)
    foreach(source IN LISTS sources)
        cmake_path(ABSOLUTE_PATH source BASE_DIRECTORY "${source_dir}" OUTPUT_VARIABLE path)
        cmake_path(GET path PARENT_PATH directory)
        cmake_path(RELATIVE_PATH directory BASE_DIRECTORY "${source_dir}")
        if(directory IN_LIST ARG_DIRECTORIES)
            string(MAKE_C_IDENTIFIER "${directory}" group)
            if(ARG_BATCH_SIZE)
                if(NOT DEFINED ${group}_sources)
                    set(${group}_sources 0)
                endif()
                math(EXPR batch "${${group}_sources} / ${ARG_BATCH_SIZE}")
                math(EXPR ${group}_sources "${${group}_sources} + 1")
                string(APPEND group "_${batch}")
            endif()
            set_source_files_properties("${path}" PROPERTIES UNITY_GROUP "${group}")
        endif()
    endforeach()
    set_target_properties(${target} PROPERTIES UNITY_BUILD ON UNITY_BUILD_MODE GROUP)
endfunction()
