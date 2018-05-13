import sys
from codecs import open  # To use a consistent encoding
from os import path

# Always prefer setuptools over distutils
from setuptools import (setup, find_packages)

here = path.abspath(path.dirname(__file__))
install_requirements = [
    'PySide2>=5.9.0a1.dev0',
    'python-vlc',
]

# The following are meant to avoid accidental upload/registration of this
# package in the Python Package Index (PyPi)
pypi_operations = frozenset(['register', 'upload']) & frozenset([x.lower() for x in sys.argv])
if pypi_operations:
    raise ValueError('Command(s) {} disabled in this example.'.format(', '.join(pypi_operations)))

with open(path.join(here, 'README.rst'), encoding='utf-8') as fh:
    long_description = fh.read()


__version__ = None
exec(open('slimvlc/about.py').read())
if __version__ is None:
    raise IOError('about.py in project lacks __version__!')

setup(name='slimvlc', version=__version__,
      author='Ben Jolitz',
      description='Thin vlc client',
      long_description=long_description,
      license='BSD',
      packages=find_packages(exclude=['contrib', 'docs', 'tests*']),
      include_package_data=True,
      dependency_links=[
          'http://download.qt.io/snapshots/ci/pyside/5.9/latest/pyside2#egg=PySide2'
      ],
      install_requires=install_requirements,
      keywords=['vlc', 'minimal'],
      url="https://github.com/benjolitz/slimvlc.git",
      classifiers=[
      ])
