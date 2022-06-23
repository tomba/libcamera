# SPDX-License-Identifier: CC0-1.0

py3_dep = dependency('python3', required : get_option('pycamera'))

if not py3_dep.found()
    pycamera_enabled = false
    subdir_done()
endif

pycamera_enabled = true

pybind11_proj = subproject('pybind11')
pybind11_dep = pybind11_proj.get_variable('pybind11_dep')

pycamera_sources = files([
    'py_camera_manager.cpp',
    'py_enums.cpp',
    'py_geometry.cpp',
    'py_helpers.cpp',
    'py_main.cpp',
])

# Generate controls

gen_py_controls_input_files = files([
    '../../libcamera/control_ids.yaml',
    'py_controls_generated.cpp.in',
])

gen_py_controls = files('gen-py-controls.py')

pycamera_sources += custom_target('py_gen_controls',
                                  input : gen_py_controls_input_files,
                                  output : ['py_controls_generated.cpp'],
                                  command : [gen_py_controls, '--mode', 'controls', '-o', '@OUTPUT@', '@INPUT@'])

# Generate properties

gen_py_property_enums_input_files = files([
    '../../libcamera/property_ids.yaml',
    'py_properties_generated.cpp.in',
])

pycamera_sources += custom_target('py_gen_properties',
                                  input : gen_py_property_enums_input_files,
                                  output : ['py_properties_generated.cpp'],
                                  command : [gen_py_controls, '--mode', 'properties', '-o', '@OUTPUT@', '@INPUT@'])

# Generate formats

gen_py_formats_input_files = files([
    '../../libcamera/formats.yaml',
    'py_formats_generated.cpp.in',
])

gen_py_formats = files('gen-py-formats.py')

pycamera_sources += custom_target('py_gen_formats',
                                  input : gen_py_formats_input_files,
                                  output : ['py_formats_generated.cpp'],
                                  command : [gen_py_formats, '-o', '@OUTPUT@', '@INPUT@'])

pycamera_deps = [
    libcamera_public,
    py3_dep,
    pybind11_dep,
]

pycamera_args = [
    '-fvisibility=hidden',
    '-Wno-shadow',
    '-DPYBIND11_USE_SMART_HOLDER_AS_DEFAULT',
    '-DLIBCAMERA_BASE_PRIVATE',
]

destdir = get_option('libdir') / ('python' + py3_dep.version()) / 'site-packages' / 'libcamera'

pycamera = shared_module('_libcamera',
                         pycamera_sources,
                         install : true,
                         install_dir : destdir,
                         name_prefix : '',
                         dependencies : pycamera_deps,
                         cpp_args : pycamera_args)

# Create symlinks from the build dir to the source dir so that we can use the
# Python module directly from the build dir.

run_command('ln', '-fsrT', files('__init__.py'),
            meson.current_build_dir() / '__init__.py',
            check: true)

run_command('ln', '-fsrT', meson.current_source_dir() / 'utils',
            meson.current_build_dir() / 'utils',
            check: true)

install_data(['__init__.py'], install_dir : destdir)

if not meson.is_cross_build()
    # \todo Generate stubs when building, and install them.
    # See https://peps.python.org/pep-0484/#stub-files
    # Note: Depends on pybind11-stubgen. To generate pylibcamera stubs:
    # $ PYTHONPATH=build/src/py pybind11-stubgen --no-setup-py -o build/src/py libcamera
    # The target below can be ran manually, but how to create a meson target that
    # is run if pycamera is built?

    stubgen = find_program('pybind11-stubgen', required : false)

    if stubgen.found()
        run_target('pystubs',
                   depends: pycamera,
                   env: {'PYTHONPATH': meson.project_build_root() / 'src' / 'py'},
                   command: [stubgen, '--no-setup-py', '-o', meson.project_build_root() / 'src' / 'py', 'libcamera'])
    endif
endif
