=========
SlimVLC
=========

Requirements
---------------

    - VLC (obtainable via ``brew install --cask vlc``)
    - Python 3.12 (obtainable via ``brew install python@3.12``)


Installation
----------------

Create a ``python/`` venv

.. code-block:: console

    $ python3.12 -m venv python


Development
^^^^^^^^^^^^^

.. code-block:: console

    $ ./python/bin/python -m pip install -e .


Production
^^^^^^^^^^^^

.. code-block:: console

    $ ./python/bin/python -m pip install git+https://github.com/autumnjolitz/slimvlc.git



Running
------------

.. code-block:: console

    $ ./python/bin/python -m slimvlc --help
    $ ./python/bin/python -m slimvlc /path/to/movie.mp4


Verbose
^^^^^^^^^

.. code-block:: console

    $ ./python/bin/python -m slimvlc -v /path/to/movie.mp4

OSD
^^^^^

.. code-block:: console

    $ ./python/bin/python -m slimvlc -osd /path/to/movie.mp4
