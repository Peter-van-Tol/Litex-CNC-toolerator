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

Installation
============

Litex-CNC can be installed using pip:

.. code-block:: shell

    pip install litexcnc_toolerator


After installation of the module, one can use the module in the firmware and driver.


Configuration of the FPGA
=========================

The code-block belows gives an example for the configuration of ``toolerator``.

.. code-block:: json

  ...
  "modules": [
    ...,
    {
      "module_type": "toolerator",
      "instances": [
        {
          ADD CONFIG HERE
        },
        {
          ADD CONFIG HERE,
          "name": "optional_name_input"
        },
        ...,
        {ADD CONFIG HERE}
      ]
    },
    ...
  ]
  ...

Defining the pin is required in the configuration. Optionally one can give the pin a name which
will be used as an alias in HAL. When no name is given, no entry in the file containnig the
aliases will be generated. 

.. warning::
  When *inserting* new pins in the list and the firmware is re-compiled, this will lead to a renumbering
  of the HAL-pins. When using numbers, it is therefore **strongly** recommended only to append pins to 
  prevent a complete overhaul of the HAL.

HAL
===

.. note::
    The input and output pins are seen from the module. I.e. the GPIO In module will take an
    value from the machine and will put this on its respective _output_ pins. While the GPIO
    Out module will read the value from it input pins and put the value on the physical pins.
    This might feel counter intuitive at first glance.

Input pins
----------

<board-name>.toolerator.<n>.<pin_name> (<pin type, i.e. HAL_BIT, etc>)
    <Pin description>.

Output pins
----------

<board-name>.toolerator.<n>.<pin_name> (<pin type, i.e. HAL_BIT, etc>)
    <Pin description>.

Parameters
----------

<board-name>.toolerator.<n>.<param_name> (<pin type, i.e. HAL_BIT, etc>)
    <Parameter description>.

Example
-------

<Provide an example on how to use the module>

.. code-block::

    loadrt threads name1=servo-thread period1=10000000
    loadrt litexcnc
    loadrt litexcnc_eth config_file="<path-to-configuration.json>"
    
    # Add the functions to the HAL
    addf <board-name>.read test-thread
    ...
    addf <board-name>.write test-thread

    # Add your example below
    <example>

Break-out boards
================

<Add the break-out boards which can be used with this module>
