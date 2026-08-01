main_py = configure_file(
  input : 'main.py',
  output : 'main.py',
  configuration : cdata,
)

version_py = configure_file(
  input : 'version.py',
  output : 'version.py',
  configuration : cdata,
)

py.install_sources(
  [
    '__init__.py',
    '__main__.py',
    'entry.py',
    'extractor.py',
    main_py,
    'mirrorparser3.py',
    'mirrorset.py',
    'output.py',
    version_py,
  ],
  subdir : 'mirrorselect',
)

subdir('configs')
subdir('selectors')
