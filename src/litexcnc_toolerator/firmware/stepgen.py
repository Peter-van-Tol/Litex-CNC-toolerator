from typing import Iterable

# Imports for creating a LiteX/Migen module
from litex.soc.interconnect.csr import *
from migen import *
from migen.fhdl.structure import Cat, Constant
from litex.soc.integration.soc import SoC
from litex.soc.integration.doc import AutoDoc, ModuleDoc
from litex.build.generic_platform import *


def create_pads(generator, pads):
        """Links the step and dir pins to the pads."""
        # Require to test working with Verilog, basically creates extra signals not
        # connected to any pads.
        if pads is None:
            pads = Record([("step", 1), ("dir", 1)])

        generator.comb += [
            pads.step.eq(generator.step),
            pads.dir.eq(generator.dir),
        ]


def create_routine(generator, pads):
        """
        Creates the routine for a step-dir stepper. The connection to the pads
        should be made in sub-classes
        """
        # Output parameters
        generator.step_prev = Signal()
        generator.step = Signal()
        generator.dir = Signal(reset=True)

        # Link step and dir
        create_pads(generator, pads)
        
        # - source which stores the value of the counters
        generator.steplen = Signal(10)
        generator.dir_hold_time = Signal(10)
        generator.dir_setup_time = Signal(12)
        # - counters
        generator.steplen_counter = StepgenCounter(10)
        generator.dir_hold_counter = StepgenCounter(11)
        generator.dir_setup_counter = StepgenCounter(13)
        generator.submodules += [
            generator.steplen_counter,
            generator.dir_hold_counter,
            generator.dir_setup_counter
        ]
        generator.hold_dds = Signal()

        # Translate the position to steps by looking at the n'th bit (pick-off)
        # NOTE: to be able to simply add the velocity to the position for every timestep, the position
        # registered is widened from the default 64-buit width to 64-bit + difference in pick-off for
        # position and velocity. This meands that the bit we have to watch is also shifted by the
        # same amount. This means that although we are watching the position, we have to use the pick-off
        # for velocity
        generator.sync += If(
            generator.position[generator.pick_off_pos] != generator.step_prev,
            # Corner-case: The machine is at rest and starts to move in the opposite
            # direction. Wait with stepping the machine until the dir setup time has
            # passed.
            If(
                ~generator.hold_dds,
                # The relevant bit has toggled, make a step to the next position by
                # resetting the counters
                generator.step_prev.eq(generator.position[generator.pick_off_pos]),
                generator.steplen_counter.counter.eq(generator.steplen),
                generator.dir_hold_counter.counter.eq(generator.steplen + generator.dir_hold_time),
                generator.dir_setup_counter.counter.eq(generator.steplen + generator.dir_hold_time + generator.dir_setup_time),
                generator.wait.eq(False)
            ).Else(
                generator.wait.eq(True)
            )
        )
        # Reset the DDS flag when dir_setup_counter has lapsed
        generator.sync += If(
            generator.dir_setup_counter.counter == 0,
            generator.hold_dds.eq(0)
        )

        # Convert the parameters to output of step and dir
        # - step
        generator.sync += If(
            generator.steplen_counter.counter > 0,
            generator.step.eq(1)
        ).Else(
            generator.step.eq(0)
        )
        # - dir
        generator.sync += If(
            generator.dir != (generator.speed[32 + (generator.pick_off_acc - generator.pick_off_vel) - 1]),
            # Enable the Hold DDS, but wait with changing the dir pin until the
            # dir_hold_counter has been elapsed
            generator.hold_dds.eq(1),
            # Corner-case: The machine is at rest and starts to move in the opposite
            # direction. In this case the dir pin is toggled, while a step can follow
            # suite. We wait in this case the minimum dir_setup_time
            If(
                generator.dir_setup_counter.counter == 0,
                generator.dir_setup_counter.counter.eq(generator.dir_setup_time)
            ),
            If(
                generator.dir_hold_counter.counter == 0,
                generator.dir.eq(generator.speed[32 + (generator.pick_off_acc - generator.pick_off_vel) - 1])
            )
        )

        # Create the outputs
        generator.ios = {generator.step, generator.dir}


class StepgenCounter(Module, AutoDoc):

    def __init__(self, size=32) -> None:

        self.intro = ModuleDoc("""
        Simple counter which counts down as soon as the Signal
        `counter` has a value larger then 0. Designed for the
        several timing components of the StepgenModule.
        """)

        # Create a 32 bit counter which counts down
        self.counter = Signal(size)
        self.sync += If(
            self.counter > 0,
            self.counter.eq(self.counter - 1)
        )


class StepgenModule(Module, AutoDoc):

    def __init__(self, pads, pick_off, soft_stop, create_routine) -> None:
        """
        
        NOTE: pickoff should be a three-tuple. A different pick-off for position, speed
        and acceleration is supported. When pick-off is a integer, all the pick offs will
        be the same.
        """

        self.intro = ModuleDoc("""
        Timing parameters:
        There are five timing parameters which control the output waveform.
        No step type uses all five, and only those which will be used are
        exported to HAL.  The values of these parameters are in nano-seconds,
        so no recalculation is needed when changing thread periods.  In
        the timing diagrams that follow, they are identfied by the
        following numbers:
        (1): 'steplen' = length of the step pulse
        (2): 'stepspace' = minimum space between step pulses, space is dependent
        on the commanded speed. The check whether the minimum step space is obeyed
        is done in the driver
        (3): 'dirhold_time' = minimum delay after a step pulse before a direction
        change - may be longer
        (4): 'dir_setup_time' = minimum delay after a direction change and before
        the next step - may be longer
                   _____         _____               _____
        STEP  ____/     \_______/     \_____________/     \______
                  |     |       |     |             |     |
        Time      |-(1)-|--(2)--|-(1)-|--(3)--|-(4)-|-(1)-|
                                              |__________________
        DIR   ________________________________/
        Improvements on LinuxCNC stepgen.c:
        - When the machine is at rest and starts a commanded move, it can be moved
          the opposite way. This means that the dir-signal is toggled and thus a wait
          time is applied before the step-pin is toggled.
        - When changing direction between two steps, it is not necessary to wait. That's
          why there are signals for DDS (1+3+4) and for wait. Only when a step is
          commanded during the DDS period, the stepgen is temporarily paused by setting
          the wait-Signal HIGH.
        """
        )
        # Store the pick-off (to prevent magic numbers later in the code)
        if isinstance(pick_off, int):
            self.pick_off_pos = pick_off
            self.pick_off_vel = pick_off
            self.pick_off_acc = pick_off
        elif isinstance(pick_off, Iterable) and not isinstance(pick_off, str):
            if len(pick_off) <  3:
                raise ValueError(f"Not enough values for `pick_off` ({len(pick_off)}), minimum length is 3.")
            self.pick_off_pos = pick_off[0]
            self.pick_off_vel = max(self.pick_off_pos, pick_off[1])
            self.pick_off_acc = max(self.pick_off_vel, pick_off[2])
        else:
            raise ValueError("`pick_off` must be either a list of pick_offs or a single integer value." )

        # Values which determine the spacing of the step. These
        # are used to reset the counters.
        # - signals
        self.wait  = Signal()
        self.reset = Signal()

        # Main parameters for position, speed and acceleration
        self.enable           = Signal()
        self.position_mode    = Signal()
        self.accelerating     = Signal()
        self.stopped          = Signal()
        self.position         = Signal((64 + (self.pick_off_vel - self.pick_off_pos), True))
        self.position_target  = Signal((64 + (self.pick_off_vel - self.pick_off_pos), True))
        self.dtg              = Signal((64 + (self.pick_off_vel - self.pick_off_pos), True)) # The distance to move
        self.acc_distance     = Signal((64 + (self.pick_off_vel - self.pick_off_pos), True)) # The distance required to stop
        self.speed            = Signal((32 + (self.pick_off_acc - self.pick_off_vel), True))
        self.speed_target     = Signal((32 + (self.pick_off_acc - self.pick_off_vel), True))
        self.max_speed        = Signal((32 + (self.pick_off_acc - self.pick_off_vel), True))
        self.max_acceleration = Signal(32)

        # Calculate the distance to go
        self.comb += self.dtg.eq(self.position_target - self.position)

        # Optionally, use a different clock domain
        sync = self.sync

        # Determine the next speed, while taking into account acceleration limits if
        # applied. The speed is not updated when the direction has changed and we are
        # still waiting for the dir_setup to time out.
        sync += If(
            ~self.reset & ~self.wait,
            # When the machine is not enabled, the speed is clamped to 0. This results in a
            # deceleration when the machine is disabled while the machine is running,
            # preventing possible damage.
            If(
                ~self.enable,
                self.speed_target.eq(0)
            ),
            If(
                self.max_acceleration == 0,
                # Case: no maximum acceleration defined, directly apply the requested speed
                self.speed.eq(self.speed_target)
            ).Else(
                # Case: obey the maximum acceleration / deceleration
                If(
                    # Accelerate, difference between actual speed and target speed is too
                    # large to bridge within one clock-cycle
                    self.speed_target >= (self.speed + self.max_acceleration),
                    # The counters are again a fixed point arithmetric. Every loop we keep
                    # the fraction and add the integer part to the speed. The fraction is
                    # used as a starting point for the next loop.
                    # - Calculate the distance we have been accelarating
                    If(
                        self.speed >= 0,
                        self.acc_distance.eq(self.acc_distance + ((self.speed + (self.max_acceleration >> 1)) >> (self.pick_off_acc - self.pick_off_vel))),
                    ).Else(
                        self.acc_distance.eq(self.acc_distance - ((self.speed + (self.max_acceleration >> 1)) >> (self.pick_off_acc - self.pick_off_vel)))
                    ),
                    # - Determine the new speed
                    self.speed.eq(self.speed + self.max_acceleration),
                    # - Set acceleration flag
                    self.accelerating.eq(1)
                ).Elif(
                    # Decelerate, difference between actual speed and target speed is too
                    # large to bridge within one clock-cycle
                    self.speed_target <= (self.speed - self.max_acceleration),
                    # The counters are again a fixed point arithmetric. Every loop we keep
                    # the fraction and add the integer part to the speed. However, we have
                    # keep in mind we are subtracting now every loop
                    # - Calculate the distance we have been accelarating
                    If(
                        self.speed > 0,
                        self.acc_distance.eq(self.acc_distance - ((self.speed - (self.max_acceleration >> 1)) >> (self.pick_off_acc - self.pick_off_vel)))
                    ).Else(
                        self.acc_distance.eq(self.acc_distance + ((self.speed - (self.max_acceleration >> 1)) >> (self.pick_off_acc - self.pick_off_vel))),
                    ),
                    # - Determine the new speed
                    self.speed.eq(self.speed - self.max_acceleration),
                    # - Set acceleration flag
                    self.accelerating.eq(1)
                ).Else(
                    # Small difference between speed and target speed, gap can be bridged within
                    # one clock cycle.
                    # - Determine the new speed and set the flag we are done accelerating
                    If(
                        (self.position_mode != 1) | (self.speed_target == 0),
                        self.speed.eq(self.speed_target),
                        If(self.speed != self.speed_target,
                            If(
                                self.speed >= 0,
                                self.acc_distance.eq(self.acc_distance + ((self.speed + self.speed_target) >> (self.pick_off_acc - self.pick_off_vel + 1))),
                            ).Else(
                                self.acc_distance.eq(self.acc_distance - ((self.speed + self.speed_target) >> (self.pick_off_acc - self.pick_off_vel + 1)))
                            )
                        )  
                    ),
                    self.accelerating.eq(0),
                    # - Reset acceleration distance if motor has stopped to prevent accumul;ation of errors
                    If(
                        self.speed_target == 0,
                        self.acc_distance.eq(0)
                    )
                )
            )
        )

        self.comb += self.stopped.eq(
            (self.dtg < ((5 * self.max_acceleration) >> (self.pick_off_acc - self.pick_off_vel))) &
            (self.dtg > ((-5 * self.max_acceleration) >> (self.pick_off_acc - self.pick_off_vel))) &
            (self.speed == 0),
        )

        # Position algorithm
        sync += If(
            (self.acc_distance == 0) & (self.position_mode),
            # Most straight forward case
            If(
                (self.dtg > ((5 * self.max_acceleration) >> (self.pick_off_acc - self.pick_off_vel))),
                self.speed_target.eq(self.max_speed),
            ).Elif(
                (self.dtg < ((-5 * self.max_acceleration) >> (self.pick_off_acc - self.pick_off_vel))),
                self.speed_target.eq(-1*self.max_speed),
            )
        ).Elif(
            (self.acc_distance > 0) & (self.position_mode),
            If(
                (self.dtg - (((5 + 4 * self.accelerating) * self.speed + (4 + 4) * self.accelerating * self.max_acceleration) >> (self.pick_off_acc - self.pick_off_vel + 1))) > self.acc_distance,
                self.speed_target.eq(self.max_speed)
            ).Else(
                self.speed_target.eq(0)
            )
        ).Elif(
            (self.acc_distance < 0) & (self.position_mode),
            If(
                (self.dtg - (((5 + 4 * self.accelerating) * self.speed - (4 + 4) * self.accelerating * self.max_acceleration) >> (self.pick_off_acc - self.pick_off_vel + 1))) < self.acc_distance,
                self.speed_target.eq(-1*self.max_speed)
            ).Else(
                self.speed_target.eq(0)
            )
        )

        # Reset algorithm.
        # NOTE: RESETTING the stepgen will not adhere the speed limit and will bring the stepgen
        # to an abrupt standstill
        sync += If(
            self.reset,
            # Prevent updating MMIO registers to prevent restart
            # Reset speed and position to 0
            self.speed_target.eq(0),
            self.speed.eq(0),
            self.max_acceleration.eq(0),
            self.position.eq(0),
        )

        # Update the position
        if soft_stop:
            sync += If(
                # Only check we are not waiting for the dir_setup. When the system is disabled, the
                # speed is set to 0 (with respect to acceleration limits) and the machine will be
                # stopped when disabled.
                ~self.reset & ~self.wait,
                self.position.eq(self.position + (self.speed >> (self.pick_off_acc - self.pick_off_vel))),
            )
        else:
            sync += If(
                # Check whether the system is enabled and we are not waiting for the dir_setup
                ~self.reset & self.enable & ~self.wait,
                self.position.eq(self.position + (self.speed >> (self.pick_off_acc - self.pick_off_vel))),
            )

        # Create the routine which actually handles the steps
        create_routine(self, pads)


if __name__ == "__main__":
    from migen import *
    from migen.fhdl import *

    def test_stepgen(stepgen):
        i = 0
        # Setup the stepgen
        yield(stepgen.enable.eq(1))
        yield(stepgen.position_mode.eq(1))
        yield(stepgen.max_acceleration.eq(int((200000 << 48) / 40e6**2)))
        yield(stepgen.max_speed.eq(int((8000 << 40) / 40e6)))
        yield(stepgen.steplen.eq(16))
        yield(stepgen.dir_hold_time.eq(16))
        yield(stepgen.dir_setup_time.eq(32))

        yield(stepgen.position_target.eq(4 << 32))
        step_prev = None

        with open('test.csv', 'w') as csv_file:
            while(1):
                # if i == 390:
                #     yield(stepgen.speed_target.eq(0x80000000 + int(2**28 / 128)))
                position = (yield stepgen.position)
                step = (yield stepgen.step)
                dir = (yield stepgen.dir)
                speed = (yield stepgen.speed)
                speed_target = (yield stepgen.speed_target)
                dtg = (yield stepgen.dtg)
                acc_dist = (yield stepgen.acc_distance)
                if True: #step != step_prev:
                    print(f"{i}, {speed_target/ (1 << 40)}, {speed/ (1 << 40)}, {position / (1 << 32)}, {dtg / (1 << 32)}, {acc_dist/ (1 << 32)}, {step}, {dir}", file=csv_file)
                    step_prev = step
                yield
                i+=1
                if i > 40000:
                    break

    stepgen = StepgenModule(pads=None, pick_off=(32, 40, 48), soft_stop=True, create_routine=create_routine)
    print("\nRunning Sim...\n")
    run_simulation(stepgen, test_stepgen(stepgen))
