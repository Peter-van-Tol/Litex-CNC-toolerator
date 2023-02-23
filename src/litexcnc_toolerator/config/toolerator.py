"""
Turret style tool changer driven by stepper motor

Author: Peter van Tol <petertgvantol@gmail.com>
License: GPL Version 2

This program is free software; you can redistribute it and/or
modify it under the terms of version 2 of the GNU General
Public License as published by the Free Software Foundation.
This library is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public
License along with this library; if not, write to the Free Software
Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.

THE AUTHORS OF THIS LIBRARY ACCEPT ABSOLUTELY NO LIABILITY FOR
ANY HARM OR LOSS RESULTING FROM ITS USE.  IT IS _EXTREMELY_ UNWISE
TO RELY ON SOFTWARE ALONE FOR SAFETY.  Any machinery capable of
harming persons must have provisions for completely removing power
from all motors, etc, before persons enter any danger area.  All
machinery must be designed to comply with local and national safety
codes, and the authors of this software can not, and do not, take
any responsibility for such compliance.

This code was written as part of the LiteX-CNC project.

Copyright (c) 2023 All rights reserved.
"""
# Imports for creating a json-definition
import os
from enum import IntEnum, auto
try:
    from typing import ClassVar, Iterable, List, Literal, Union
except ImportError:
    # Imports for Python <3.8
    from typing import ClassVar, Iterable, List, Union
    from typing_extensions import Literal
from pydantic import Field, conlist

# Import of the basemodel, required to register this module
from litexcnc.config.modules import ModuleBaseModel, ModuleInstanceBaseModel

# Local imports
from litexcnc_toolerator.config.stepgen import StepgenConfig

class TooleratorHomingConfig(ModuleInstanceBaseModel):
    home_pin: str = Field(
        None,
        description="The pin on the FPGA-card for the homing signal. This pin MUST be configured "
        "as input. When the home_pin is not defined, the turret is homed in place with the current "
        "tool assumed to be tool 1."
    )
    invert_home: bool = Field(
        None,
        description="Inverts the homing pin. When set to True, the homing pin is active LOW."
    )
    home_back_off: float = Field(
        None,
        description="The distance (in degerees) the toolchanger should back off from the switch. "
        "When not defined, the value of over-travel is used."
    )
    home_latch_vel: float = Field(
        ...,
        description="Specifies the speed and direction that LitexCNC uses when it makes its final "
        "accurate determination of the home switch (if present)."
    )
    home_position: float = Field(
        None,
        description="The position of the homing point to the first tool (in degrees). When the position is "
        "positive the tool is moved forward by this amount plus any overtravel defined (NOTE: "
        "the turret will move back again). When the position is negative over travel is NOT taken "
        "into account, as the turret is already moving backwards to it locking position."
    )


class TooleratorInstanceConfig(ModuleInstanceBaseModel):
    """
    Model describing an instance of toolerator
    """
    name: str = Field(
        None,
        description="The name of the instance as used in LinuxCNC HAL-file (optional). "
        "When not specified, no alias for the pin will be created."
    )
    io_standard: str = Field(
        "LVCMOS33",
        description="The IO Standard (voltage) to use for the pin."
    )
    tool_count: int = Field(
        ...,
        description="The maximum number of tools in the toolerator. For the EMCO 5 CNC "
        "this is 6 tools, for the EMCO 120 this number is 8 tools. The maximum number of "
        "tools is 255."
    )
    ppr: int = Field(
        ...,
        description="The number of pulses per full revolution of the resolver."
    )
    over_travel: float = Field(
        ...,
        description="The amount of rotation required by the toolpost in order for the "
        "ratchet to lock (in degrees). For every change this angle is added to the movement "
        "and afterwards the turret will be rotated this amount back."
    )
    stepgen: StepgenConfig = Field(
        ...,
        description=""
    )
    homing: TooleratorHomingConfig = Field(
        None,
        description=""
    )
    pins: ClassVar[List[str]] = Field(
        [
            ...
        ],
        description="List of names of the pins as defined in the litexcnc_toolerator.c."
        "These names are used to be able to generate the aliases for the pins when "
        "the end-user defines a name for this instance." 
    )
    params: ClassVar[List[str]] = Field(
        [
            ...
        ],
        description="List of names of the params as defined in the litexcnc_toolerator.c."
        "These names are used to be able to generate the aliases for the pins when "
        "the end-user defines a name for this instance." 
    )


class TooleratorModuleConfig(ModuleBaseModel):
    """
    Model describing the toolerator module
    """
    module_type: Literal['toolerator'] = 'toolerator'
    module_id: ClassVar[int] = 0x4e32796a  # Must be equal to litexcnc_toolerator.h
    driver_files: ClassVar[List[str]] = [
        os.path.dirname(__file__) + '/../driver/litexcnc_toolerator.c',
        os.path.dirname(__file__) + '/../driver/litexcnc_toolerator.h'
    ]
    instances: conlist(
            item_type=TooleratorInstanceConfig,
            unique_items=True,
            min_items=1,
            max_items=3
        ) = Field(
            ...,
        )

    def create_from_config(self, soc, watchdog):
        # Deferred imports to prevent importing Litex while installing the driver
        from litexcnc_toolerator.firmware import TooleratorModule
        TooleratorModule.create_from_config(soc, watchdog, self)
    
    def add_mmio_config_registers(self, mmio):
        # Deferred imports to prevent importing Litex while installing the driver
        from litexcnc_toolerator.firmware import TooleratorModule
        TooleratorModule.add_mmio_config_registers(mmio, self)

    def add_mmio_write_registers(self, mmio):
        # Deferred imports to prevent importing Litex while installing the driver
        from litexcnc_toolerator.firmware import TooleratorModule
        TooleratorModule.add_mmio_write_registers(mmio, self)

    def add_mmio_read_registers(self, mmio):
        # Deferred imports to prevent importing Litex while installing the driver
        from litexcnc_toolerator.firmware import TooleratorModule
        TooleratorModule.add_mmio_read_registers(mmio, self)

    @property
    def config_size(self):
        return 4

    def store_config(self, mmio):
        # Deferred imports to prevent importing Litex while installing the driver
        from litex.soc.interconnect.csr import CSRStatus, CSRField
        # Get the tool counts for each instance if defined
        tc0 = 0
        if len(self.instances):
            tc0 = self.instances[0].tool_count
        tc1 = 0
        if len(self.instances) > 1:
            tc1 = self.instances[1].tool_count
        tc2 = 0
        if len(self.instances) > 2:
            tc2 = self.instances[2].tool_count
        # Create the config
        mmio.toolerator_config_data =  CSRStatus(
            fields=[
                CSRField("instances", size=8, offset=0, description="The requested tool."),
                CSRField("max_tools1", size=8, offset=8, description="The requested tool - instance 0.", reset=tc0),
                CSRField("max_tools2", size=8, offset=16, description="The requested tool - instance 1.", reset=tc1),
                CSRField("max_tools3", size=8, offset=24, description="The requested tool - instance 2.", reset=tc2),
            ],
            reset=len(self.instances),
            description=f"The config of the toolerator module."
        )
