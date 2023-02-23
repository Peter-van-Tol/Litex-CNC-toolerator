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
from enum import IntEnum, auto

# Imports for creating a LiteX/Migen module
from litex.soc.interconnect.csr import *
from migen import *
from migen.fhdl.structure import Cat, Constant
from litex.soc.integration.soc import SoC
from litex.soc.integration.doc import AutoDoc, ModuleDoc
from litex.build.generic_platform import *

# Local imports
from litexcnc_toolerator.config.toolerator import TooleratorInstanceConfig
from litexcnc_toolerator.firmware.stepgen import StepgenModule, create_routine


class TooleratorStates(IntEnum):
    """Different states of the Toolerator. One could use the Migen FSM module, however
    this statement is rendered as combinatorial. This poses issues with the stepgen, where
    any change in target_position takes a clock-cycle to be effective. With combinatorial
    statements parts are skipped when the states are changed.
    """
    START = auto()
    HOME_SEARCHING = auto()
    HOME_BACK_OFF = auto()
    HOME_LATCHING = auto()
    HOME_MOVE_TO_ZERO = auto()
    MOVING_FORWARD = auto()
    MOVING_BACKWARD = auto()
    READY = auto()
    ERROR = auto()


class TooleratorModule(Module, AutoDoc):

    pads_layout = [("step", 1), ("dir", 1), ("home", 1)]

    def __init__(self, config: 'TooleratorInstanceConfig',  pick_off, clock_frequency, pads=None) -> None:

        # AutoDoc implementation
        self.intro = ModuleDoc(self.__class__.__doc__)
        
        # Require to test working with Verilog, basically creates extra signals not
        # connected to any pads.
        if pads is None:
            pads = Record(self.pads_layout)
        self.pads = pads

        # Create a stepgen instance
        self.step_generator = StepgenModule(
            pads=pads, 
            pick_off=pick_off, 
            soft_stop=True,
            create_routine=create_routine
        )
        self.submodules += self.step_generator

        # Store the configuration on the stepgen
        self.comb += [
            self.step_generator.max_acceleration.eq(int((config.stepgen.speed.max_acc * (1 << 48)) / clock_frequency**2)),
            self.step_generator.max_speed.eq(int((config.stepgen.speed.max_vel * (1 << 40)) / clock_frequency)),
            self.step_generator.steplen.eq(int(config.stepgen.timings.steplen * 1e9 / clock_frequency)),
            self.step_generator.dir_hold_time.eq(int(config.stepgen.timings.dir_hold_time * 1e9 / clock_frequency)),
            self.step_generator.dir_setup_time.eq(int(config.stepgen.timings.dir_setup_time * 1e9 / clock_frequency)),
        ]
        
        # Feed the step generator with information on the tools
        self.enable         = Signal(1)
        self.current_tool   = Signal(8)
        self.moving_to_tool = Signal(8)
        self.commanded_tool = Signal(8)
        self.home           = Signal(1)
        self.home_triggered = Signal(1)
        self.home_position  = Signal((64 + (self.step_generator.pick_off_vel - self.step_generator.pick_off_pos), True))
        
        # Pass the enabled signal to the stepgenerator
        self.comb += self.step_generator.enable.eq(self.enable)

        # Tie in the homing signal
        if config.homing:
            self.homed = Signal(1)
            # Connect the pad to the homing triggered
            if config.homing.invert_home:
                self.home_triggered.eq(~self.pads.home)
            else:
                self.home_triggered.eq(self.pads.home)
        else:
            self.homed = Signal(1, reset=1)

        # Create a finite state machine
        self.state = Signal(4, reset=TooleratorStates.START)
        self.sync += If(
            self.state == TooleratorStates.START,
            If(
                self.homed == 1,
                self.step_generator.position_mode.eq(1),
                self.state.eq(TooleratorStates.READY)
            ),
            If(
                self.home == 1 | ((self.current_tool != self.commanded_tool) & ~self.homed),
                # Start homing sequence, start turning the tool changer at full speed
                self.step_generator.position_mode.eq(0),
                self.home_position.eq(self.step_generator.position),
                self.step_generator.speed_target.eq(self.step_generator.max_speed),
                self.state.eq(TooleratorStates.HOME_SEARCHING)
            )
        ).Elif(
            self.state == TooleratorStates.MOVING_FORWARD,
            If(
                self.step_generator.stopped,
                self.step_generator.position_target.eq(
                    self.step_generator.position_target 
                        - int((config.ppr << self.step_generator.pick_off_pos) * (config.over_travel / 360))
                ),
                self.state.eq(TooleratorStates.MOVING_BACKWARD)
            )
        ).Elif(
            self.state == TooleratorStates.MOVING_BACKWARD,
            If(
                self.step_generator.stopped,
                self.current_tool.eq(self.moving_to_tool),
                self.state.eq(TooleratorStates.READY)
            )
        ).Elif(
            self.state == TooleratorStates.READY,
            If(
                (self.current_tool != self.commanded_tool) & self.homed,
                If(
                    self.current_tool < self.commanded_tool,
                    self.step_generator.position_target.eq(
                        self.step_generator.position_target 
                            + int((config.ppr << self.step_generator.pick_off_pos) / config.tool_count) * (self.commanded_tool - self.current_tool)
                            + int((config.ppr << self.step_generator.pick_off_pos) * (config.over_travel / 360)
                        ) 
                    ),
                ).Else(
                    self.step_generator.position_target.eq(
                        self.step_generator.position_target 
                            + int((config.ppr << self.step_generator.pick_off_pos) / config.tool_count) * (config.tool_count + self.commanded_tool - self.current_tool)
                            + int((config.ppr << self.step_generator.pick_off_pos) * (config.over_travel / 360)
                        )
                    ),
                ),
                self.moving_to_tool.eq(self.commanded_tool),
                self.state.eq(TooleratorStates.MOVING_FORWARD)
            )
        )
        if config.homing:
            self.sync += If(
                self.state == TooleratorStates.HOME_SEARCHING,
                If(
                    # Home has been triggered, stop the movement
                    self.home_triggered,
                    self.home_position.eq(self.step_generator.position),
                    self.step_generator.speed_target.eq(0),
                    self.state.eq(TooleratorStates.HOME_BACK_OFF)
                ),
                If(
                    # After a full revolution the home switch has not been found
                    self.home_position - self.step_generator.position > (config.ppr + 1),
                    self.step_generator.speed_target.eq(0),
                    self.state.eq(TooleratorStates.ERROR)
                )
            ).Elif(
                self.state == TooleratorStates.HOME_BACK_OFF,
                # Wait until the stepper motor has been stopped
                If(
                    self.step_generator.position_mode == 0 & self.step_generator.stopped,
                    self.step_generator.position_mode.eq(1),
                    self.step_generator.position_target.eq(
                        self.home_position
                            - int((config.ppr << self.step_generator.pick_off_pos) * (((config.homing.home_back_off or config.over_travel) / 360)))
                    )
                ),
                # Wait until the stepper motor has stopped again. This time the back off distance has been reached
                If(
                    self.step_generator.position_mode == 1 & self.step_generator.stopped,
                    # Switch back to velocity mode and approach the homing switch once more
                    self.home_position.eq(self.step_generator.position),
                    self.step_generator.speed_target.eq(int((config.homing.home_latch_vel << self.step_generator.pick_off_vel) / clock_frequency)),
                    self.state.eq(TooleratorStates.HOME_LATCHING)
                )
            ).Elif(
                self.state == TooleratorStates.HOME_LATCHING,
                If(
                    # Home has been triggered, stop the movement
                    self.home_triggered,
                    self.home_position.eq(self.step_generator.position),
                    self.step_generator.speed_target.eq(0),
                    self.state.eq(TooleratorStates.HOME_BACK_OFF)
                ),
                If(
                    # The home switch has not been found within two back off distances
                    self.home_position - self.step_generator.position > int((config.ppr << self.step_generator.pick_off_pos) * (((config.homing.home_back_off or config.over_travel) / 360))),
                    self.step_generator.speed_target.eq(0),
                    self.state.eq(TooleratorStates.ERROR)
                )
            ).Elif(
                self.state == TooleratorStates.HOME_MOVE_TO_ZERO,
                # Wait until the stepper motor has been stopped
                If(
                    self.step_generator.position_mode.eq(0) & self.step_generator.stopped,
                    self.step_generator.position_mode.eq(1),
                    self.step_generator.position_target.eq(
                        self.home_position
                            - int((config.ppr << self.step_generator.pick_off_pos) * ((config.homing.home_position / 360)))
                            + int((config.ppr << self.step_generator.pick_off_pos) * ((config.over_travel / 360)))
                    )
                ),
                # Wait until the stepper motor has stopped again. This time the back off distance has been reached
                If(
                    self.step_generator.position_mode.eq(1) & self.step_generator.stopped,
                    # Go to the next phase, which will lock the tool.
                    self.state.eq(TooleratorStates.MOVING_FORWARD)
                )
            )


    @classmethod
    def add_mmio_config_registers(cls, mmio, config):
        """Adds the MMIO config registers. These registers hold the data which
        is written at the first cycle to configure the FPGA. Example of data
        written to the config register is the timing data for stepgen.

        NOTE: when no config is required to be written to the FPGA, this 
        function can be left empty.

        Args:
            mmio (MMIO): The MMIO instance (memory which can be read from and 
            written to using the etherbone connection) 
            config (TooleratorModuleConfig): The configuration of
            the FPGA.
        """
        # Don't create the module when the config is empty (no toolerator 
        # defined in this case)
        if not config.instances:
            return

        # Function left empty as there is no config data written to the
        # toolerator

    
    @classmethod
    def add_mmio_write_registers(cls, mmio, config):
        """Adds the MMIO write registers. These registers hold the data which
        is every cycle written to the FPGA.

        NOTE: when no data is required to be written to the FPGA, this function
        can be left empty.

        Args:
            mmio (MMIO): The MMIO instance (memory which can be read from and 
            written to using the etherbone connection) 
            config (tooleratorModuleConfig): The configuration of
            the FPGA.
        """
        # Don't create the module when the config is empty (no toolerator 
        # defined in this case)
        if not config.instances:
            return

        for index in range(len(config.instances)):
            setattr(
                mmio,
                f'toolerator_{index}_data',
                CSRStatus(
                    fields=[
                        CSRField("tool_number", size=8, offset=0, description="The requested tool."),
                        CSRField("tool_change", size=1, offset=8, description="Indication that tool change is requested."),
                        CSRField("enabled", size=1, offset=16, description="Indication that toolchanger is enabled."),

                    ],
                    name=f'toolerator_{index}_data',
                    description="Toolerator write data"
                    f"Toolchange data for toolerator {index}."
                )
            )

    @classmethod
    def add_mmio_read_registers(cls, mmio, config):
        """Adds the MMIO read registers. These registers hold the data which
        is every cycle read by LinuxCNC / HAL.

        NOTE: when no data is required to be read from the FPGA, this function
        can be left empty.

        Args:
            mmio (MMIO): The MMIO instance (memory which can be read from and 
            written to using the etherbone connection) 
            config (TooleratorModuleConfig): The configuration of
            the FPGA.
        """
        # Don't create the module when the config is empty (no toolerator 
        # defined in this case)
        if not config.instances:
            return

        for index in range(len(config.instances)):
            setattr(
                mmio,
                f'toolerator_{index}_status',
                CSRStatus(
                    fields=[
                        CSRField("status", size=4, offset=0, description="Tool changer status."),
                        CSRField("homed", size=1, offset=8, description="Tool changer has been homed."),
                        CSRField("tool_number", size=8, offset=16, description="The current selected tool."),
                    ],
                    name=f'toolerator_{index}_status',
                    description="toolerator instance status"
                    f"Status of the toolerator {index}."
                )
            )

    @classmethod
    def create_from_config(cls, soc: SoC, watchdog, config: 'TooleratorModuleConfig'):
        """
        Adds the module as defined in the configuration to the SoC.
        NOTE: the configuration must be a list and should contain all the module at
        once. Otherwise naming conflicts will occur.
        """
        # Don't create the module when the config is empty (no toolerator 
        # defined in this case)
        if not config.instances:
            return

        # Determine the pick-off for the velocity. This one is based on the clock-frequency
        # and the step frequency to be obtained
        shift = 0
        while (soc.clock_frequency / (1 << shift) > 400e3):
            shift += 1

        # Create the generators
        for index, instance_config in enumerate(config.instances):
            # Add the io to the FPGA
            if instance_config.homing:
                pins = (
                    Subsignal("step", Pins(instance_config.stepgen.pins.step_pin), IOStandard(instance_config.io_standard)),
                    Subsignal("dir",  Pins(instance_config.stepgen.pins.dir_pin),  IOStandard(instance_config.io_standard)),
                    Subsignal("home", Pins(instance_config.homing.home_pin), IOStandard(instance_config.io_standard))
                )
            else:
                pins = (
                    Subsignal("step", Pins(instance_config.stepgen.pins.step_pin), IOStandard(instance_config.io_standard)),
                    Subsignal("dir",  Pins(instance_config.stepgen.pins.dir_pin),  IOStandard(instance_config.io_standard))
                )
            soc.platform.add_extension([("toolerator", index, *pins)])
            # Create the toolerator
            pads = soc.platform.request("toolerator", index)
            toolerator = TooleratorModule(
                instance_config, 
                pick_off=(32, 32 + shift, 32 + shift + 8),
                clock_frequency=soc.clock_frequency,
                pads=pads)
            soc.submodules += toolerator
            # Connect the module to the MMIO
            soc.comb += [
                # Fields written to toolerator
                toolerator.enable.eq(getattr(soc.MMIO_inst, f'toolerator_{index}_data').fields.enabled & ~watchdog.has_bitten),
                toolerator.commanded_tool.eq(getattr(soc.MMIO_inst, f'toolerator_{index}_data').fields.tool_number),
                # Fiekds read from toolerator
                getattr(soc.MMIO_inst, f'toolerator_{index}_status').fields.status.eq(toolerator.state),
                getattr(soc.MMIO_inst, f'toolerator_{index}_status').fields.homed.eq(toolerator.homed),
                getattr(soc.MMIO_inst, f'toolerator_{index}_status').fields.tool_number.eq(toolerator.current_tool),
            ]


if __name__ == "__main__":
    from migen import *
    from migen.fhdl import *

    def test_toolerator(toolerator):
        i = 0
        # Setup the stepgen
        yield(toolerator.enable.eq(1))
        yield(toolerator.commanded_tool.eq(1))


        with open('test.csv', 'w') as csv_file:
            while(1):
                # if i == 390:
                #     yield(stepgen.speed_target.eq(0x80000000 + int(2**28 / 128)))
                position = (yield toolerator.step_generator.position)
                step = (yield toolerator.step_generator.step)
                dir = (yield toolerator.step_generator.dir)
                speed = (yield toolerator.step_generator.speed)
                speed_target = (yield toolerator.step_generator.speed_target)
                dtg = (yield toolerator.step_generator.dtg)
                acc_dist = (yield toolerator.step_generator.acc_distance)
                if True: #step != step_prev:
                    print(f"{i}, {speed_target/ (1 << 40)}, {speed/ (1 << 40)}, {position / (1 << 32)}, {dtg / (1 << 32)}, {acc_dist/ (1 << 32)}, {step}, {dir}", file=csv_file)
                    step_prev = step
                yield
                i+=1
                if i > 40000:
                    break

    config = TooleratorInstanceConfig(
        tool_count=6,
        ppr=18,
        over_travel=20,
        stepgen={
            "pins": {
                "step_pin": "not_used",
                "dir_pin" : "not_used",
            },
            "speed": {
                "max_acc": 200000,
                "max_vel": 8000,
            },
            "timings": {  # All timings in nanoseconds
                "steplen": 400,
                "dir_hold_time": 400, 
                "dir_setup_time": 800, 
            },
        },
        homing=None
    )

    toolerator = TooleratorModule(config, pick_off=(32, 40, 48), clock_frequency=40e6)
    print("\nRunning Sim...\n")
    # print(verilog.convert(toolerator))
    run_simulation(toolerator, test_toolerator(toolerator))
