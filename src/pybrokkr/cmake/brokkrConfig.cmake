# brokkr: CMake helpers for native libraries shipped as Python wheels (nanobind modules, bundled native
# prefixes, relative rpaths into sibling provider wheels, stub post-processing).
#
# Found through scikit-build-core's cmake.prefix entry point in wheel builds; in a manual configure, pass
# -Dbrokkr_DIR="$(python -m pybrokkr --cmake-dir)". Usable before project(). The functions are global, so
# repeated find_package(brokkr) calls are harmless.
include("${CMAKE_CURRENT_LIST_DIR}/brokkrReadProjectVersion.cmake")
include("${CMAKE_CURRENT_LIST_DIR}/brokkrPythonHelpers.cmake")
include("${CMAKE_CURRENT_LIST_DIR}/brokkrPythonPackaging.cmake")
