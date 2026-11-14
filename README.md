# brokkr

Build tooling for native C++ libraries shipped as Python wheels (the provider-wheel family: pyyggdrasil, pypddl,
pytyr, pyrunir). A provider wheel bundles its native library, headers and exported CMake package under
`<pkg>/native/`, and other wheels build and link against it through relative rpaths.

- **CMake** (`find_package(brokkr)`): `brokkr_read_project_version` (usable before `project()`),
  `brokkr_find_python_native_prefix`, `brokkr_register_*`, `brokkr_python_package_init`,
  `brokkr_python_module_rpaths`, `brokkr_install_native_export`, `brokkr_install_runtime_path_fixup`,
  `brokkr_install_provider_env`, `brokkr_install_python_stubs`, `brokkr_install_python_files`,
  `brokkr_unity_directories` (unity batches by directory), `brokkr_limit_compile_jobs` (a target's TUs compiled at most
  so many at once; no limit when the count is empty).
- **Fallback check** (`python -m pybrokkr.fallbacks --compile-commands build/compile_commands.json`, with
  `pybrokkr[fallbacks]`): reports the silent fallbacks of a C++ project, as the coding rules define them.
- **Compile cost** (`python -m pybrokkr.compile_cost`): records every compile's time and peak memory through CMake's
  compiler launcher, compares two builds by object, and finds what a build compiles in more than one translation unit,
  as the template rules measure it.
- **Unity check** (`python -m pybrokkr.unity_check --compile-commands build/compile_commands.json <directory>...`,
  with `pybrokkr[fallbacks]`): the file-local functions that a unity batch of each directory would make overloads of
  each other.
- **PEP 517 backend** (`pybrokkr.build_backend.ProviderBackend`): scikit-build-core, with the providers' prefixes put
  on `CMAKE_PREFIX_PATH` and the loader path, then the wheel's stubs published and its native libraries stripped.

```toml
[build-system]
requires = ["scikit-build-core>=1.0.3,<2", "pybrokkr>=0.1,<0.2", "pyyggdrasil>=0.6,<0.7"]
build-backend = "mypkg_build_backend"
backend-path = ["python"]
```

```python
# python/mypkg_build_backend.py
from pybrokkr.build_backend import ProviderBackend

ProviderBackend(
    package="mypkg",
    providers=("pyyggdrasil",),
    prefix_defines={"pyyggdrasil": "YGGDRASIL_NATIVE_PREFIX"},
).install_hooks(globals())
```

```cmake
cmake_minimum_required(VERSION 3.21)
find_package(brokkr REQUIRED)  # wheel builds: found through pybrokkr's cmake.prefix entry point
brokkr_read_project_version(MYPKG_VERSION "${CMAKE_CURRENT_SOURCE_DIR}/pyproject.toml")
project(mypkg VERSION "${MYPKG_VERSION}" LANGUAGES CXX)
```

In a manual configure, pass `-Dbrokkr_DIR="$(python -m pybrokkr --cmake-dir)"`.

## Rules

The rules the libraries share (the release cycle, the template and include rules and the coding rules) are
maintained here, in `docs/`, and published at <https://planning-and-learning.github.io/brokkr/>.
