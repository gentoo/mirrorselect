project('mirrorselect',
  default_options : { 'prefix' : '/usr' },
  meson_version : '>=1.2.0',
  version : '2.7.0',
)

py = import('python').find_installation(pure : true)

confdir = get_option('prefix') / get_option('sysconfdir')

cdata = configuration_data()
cdata.set('CONFDIR', confdir)
cdata.set('VERSION', meson.project_version())

subdir('mirrorselect')
subdir('bin')

if get_option('man')
  install_man(configure_file(
    input : 'mirrorselect.1',
    output : 'mirrorselect.1',
    configuration : cdata,
  ))
endif

test('unittests', py,
  args : ['-m', 'unittest', 'discover', '-s', meson.project_source_root()],
)
