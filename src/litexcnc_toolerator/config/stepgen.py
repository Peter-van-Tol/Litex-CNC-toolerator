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
from pydantic import BaseModel, Field

class StepgenPins(BaseModel):
    step_pin: str = Field(
        ...,
        description="The pin on the FPGA-card for the step signal."
    )
    dir_pin: str = Field(
        ...,
        description="The pin on the FPGA-card for the dir signal."
    )


class StepgenTimings(BaseModel):
    steplen: int = Field(
        ...
    )
    dir_hold_time: int = Field(
        ...
    )
    dir_setup_time: int = Field(
        ...
    )


class StepgenSpeed(BaseModel):
    max_vel: float = Field(
        ...,
        description="The maximum speed of the tool changer."
    )
    max_acc: float = Field(
        ...,
        description="The maximum acceleration of the tool changer."
    )


class StepgenConfig(BaseModel):

    pins: StepgenPins = Field(
        ...
    )
    speed: StepgenSpeed = Field(
        ...
    )
    timings: StepgenTimings = Field(
        ...
    )
