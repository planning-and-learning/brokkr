# Finds brokkr for an installed package config that uses its helpers, so that the package's consumers need not know
# about brokkr: brokkr_install_native_export / brokkr_install_locator install this file next to the config, which
# include()s it before calling brokkr_* functions. brokkr is taken from CMAKE_PREFIX_PATH or brokkr_DIR, else from the
# Python that has pybrokkr (Python_EXECUTABLE, Python3_EXECUTABLE, else python3 on PATH).
if(NOT COMMAND brokkr_find_python_native_prefix)
    find_package(brokkr QUIET)
    if(NOT brokkr_FOUND)
        if(Python_EXECUTABLE)
            set(_brokkr_python "${Python_EXECUTABLE}")
        elseif(Python3_EXECUTABLE)
            set(_brokkr_python "${Python3_EXECUTABLE}")
        else()
            find_program(_brokkr_python NAMES python3 python)
        endif()
        if(_brokkr_python)
            execute_process(COMMAND "${_brokkr_python}" -m pybrokkr --cmake-dir
                            OUTPUT_VARIABLE _brokkr_dir OUTPUT_STRIP_TRAILING_WHITESPACE ERROR_QUIET)
            if(_brokkr_dir)
                set(brokkr_DIR "${_brokkr_dir}" CACHE PATH "The directory holding brokkrConfig.cmake" FORCE)
            endif()
        endif()
        find_package(brokkr REQUIRED)
    endif()
endif()
