# Compile job pools (brokkr's template rules, rule 11).

# At most JOBS of the translation units of `target` compile at once (Ninja's job pools; other generators ignore them):
# where a target's TUs are the build's heaviest (bindings, unity batches), they would otherwise take every parallel slot
# at the same time, and that sets the build's peak memory; limited, lighter TUs of other targets fill the other slots,
# so the wall time stays. How many depends on the machine (its memory and -j), so the caller leaves JOBS to
# configuration time: empty, the target is not limited beyond -j.
#
#     set(FOO_PYTHON_COMPILE_JOBS "" CACHE STRING "Most pyfoo translation units compiled at once (Ninja); empty: no limit.")
#     brokkr_limit_compile_jobs(_pyfoo JOBS "${FOO_PYTHON_COMPILE_JOBS}")
function(brokkr_limit_compile_jobs target)
    cmake_parse_arguments(PARSE_ARGV 1 ARG "" "JOBS" "")
    if("${ARG_JOBS}" STREQUAL "")
        return()
    endif()
    set(pool "${target}_compile")
    set_property(GLOBAL APPEND PROPERTY JOB_POOLS "${pool}=${ARG_JOBS}")
    set_target_properties(${target} PROPERTIES JOB_POOL_COMPILE "${pool}")
endfunction()
