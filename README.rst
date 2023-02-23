===============================
Welcome to LiteX-CNC toolerator
===============================

Turret style tool changer driven by stepper motor

.. info::
   The Litex-CNC project aims to make a generic CNC firmware and driver for FPGA cards which are
   supported by Litex. Configuration of the board and driver is done using json-files. The supported
   boards are the Colorlight boards 5A-75B and 5A-75E, as these are fully supported with the open
   source toolchain. The Litex-CNC project can be extended by custom modules, tailored to the need
   of the users.

   See the `documentation <https://litex-cnc.readthedocs.io/en/latest/>` for a full description of
   Litex-CNC and its capabilities.

Quick start
===========

Litex-CNC toolerator can be installed using pip:

.. code-block:: shell

    pip install litexcnc_toolerator


After installation of the module, one can use the module in the firmware and driver.

For a full description on the generation, please refer to the relevant documentation:
- Litex-CNC: https://litex-cnc.readthedocs.io/en/latest/
- toolerator: ...

Developing
==========

Litex-CNC toolerator uses `Poetry <>`_ for packaging and dependecny
management. To start with the development of the module, one can install the required
dependencies with:

.. code-block:: shell

    poetry install

This will install module in edit mode, including the required dependencies such as
Litex-CNC.

Firmware
--------

The firmware is located in the file ``.\src\litexcnc\firmware\toolerator.py``. 
The folder cannot be renamed, because this would prevent the detection of the module
by the Litex-CNC.

The firmare, including the newly created module, can be created based with the following command:

.. code-block:: shell

    litexcnc build_firmware "<path-to-your-configuration>" --build 

Type ``litexcnc build_firmware --help`` for more options. 

Driver
------
The driver is located in the folder ``.\src\litexcnc\driver\``. This folder must contain 
the following files:

- header file: litexcnc_toolerator.h;
- source file: litexcnc_toolerator.c;

The folder cannot be renamed, because this would prevent the detection of the module
by the Litex-CNC. Both files must start with ``litexcnc_`` in order to be picked up
by the command to compile all modules. The name of the module can be changed and also
additional files can be created.

The driver, including the newly created module, can be installed with the following command:

.. code-block:: shell

    litexcnc install_driver

.. info::
    When ``sudo`` is required to install the driver, it might be required to pass the environment variables
    to the command:

    .. code-block:: shell

        sudo -E env PATH=$PATH litexcnc install_driver

