# SPDX-License-Identifier: CC0-1.0

py3_dep = dependency('python3', required : get_option('pycamera'))

if py3_dep.found() == false
    subdir_done()
endif

pybind11_proj = subproject('pybind11')
pybind11_dep = pybind11_proj.get_variable('pybind11_dep')

pycamera_sources = files([
    'pymain.cpp',
])

pycamera_deps = [
    libcamera_public,
    py3_dep,
    pybind11_dep,
]

pycamera_args = [ '-fvisibility=hidden' ]
pycamera_args += [ '-Wno-shadow' ]

destdir = get_option('libdir') + '/python' + py3_dep.version() + '/site-packages/pycamera'

pycamera = shared_module('pycamera',
                         pycamera_sources,
                         install : true,
                         install_dir : destdir,
                         name_prefix : '',
                         dependencies : pycamera_deps,
                         cpp_args : pycamera_args)

# XXX > You could also create a symlink. There's an example in the top-level
# > meson.build.
# Copy __init__.py to build dir so that we can run without installing
configure_file(input: '__init__.py', output: '__init__.py', copy: true)

install_data(['__init__.py'], install_dir : destdir)
