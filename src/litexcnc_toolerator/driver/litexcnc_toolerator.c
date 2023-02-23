/********************************************************************
* Description:  litexcnc_toolerator.c
*               Turret style tool changer driven by stepper motor
*
* Author: Peter van Tol <petertgvantol@gmail.com>
* License: GPL Version 2
*    
* Copyright (c) 2023 All rights reserved.
*
********************************************************************/

/** This program is free software; you can redistribute it and/or
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
*/
#include <inttypes.h>
#include <math.h>

#include "hal.h"
#include "rtapi.h"
#include "rtapi_app.h"
#include "rtapi_string.h"

#include "litexcnc_toolerator.h"

/** 
 * An array holding all instance for the module. As each boarf normally have a 
 * single instance of a type, this number coincides with the number of boards
 * which are supported by LitexCNC
 */
static litexcnc_toolerator_t *instances[MAX_INSTANCES];
static int num_instances = 0;

/**
 * Parameter which contains the registration of this module woth LitexCNC 
 */
static litexcnc_module_registration_t *registration;


/*******************************************************************************
 * Function which registers this module on LitexCNC. This function is exported
 * to the outside world, so LitexCNC can find it.
 ******************************************************************************/
int register_toolerator_module(void) {
    registration = (litexcnc_module_registration_t *)hal_malloc(sizeof(litexcnc_module_registration_t));
    registration->id = 0x4e32796a;
    rtapi_snprintf(registration->name, sizeof(registration->name), "toolerator");
    registration->initialize = &litexcnc_toolerator_init;
    registration->required_config_buffer = &required_config_buffer;
    registration->required_write_buffer  = &required_write_buffer;
    registration->required_read_buffer   = &required_read_buffer;
    return litexcnc_register_module(registration);
}
EXPORT_SYMBOL_GPL(register_toolerator_module);


int rtapi_app_main(void) {
    // Show some information on the module being loaded
    LITEXCNC_PRINT_NO_DEVICE(
        "Loading Litex toolerator module driver version %u.%u.%u\n", 
        LITEXCNC_TOOLERATOR_VERSION_MAJOR, 
        LITEXCNC_TOOLERATOR_VERSION_MINOR, 
        LITEXCNC_TOOLERATOR_VERSION_PATCH
    );

    // Initialize the module
    comp_id = hal_init(LITEXCNC_TOOLERATOR_NAME);
    if(comp_id < 0) return comp_id;

    // Register the module with LitexCNC (NOTE: LitexCNC should be loaded first)
    int result = register_toolerator_module();
    if (result<0) return result;

    // Report GPIO is ready to be used
    hal_ready(comp_id);

    return 0;
}


void rtapi_app_exit(void) {
    hal_exit(comp_id);
    LITEXCNC_PRINT_NO_DEVICE("LitexCNC toolerator module driver unloaded \n");
}


size_t required_config_buffer(void *module) {
    static litexcnc_toolerator_t *toolerator_module;
    toolerator_module = (litexcnc_toolerator_t *) module;
    // Safeguard for empty modules
    if (toolerator_module->num_instances == 0) {
        return 0;
    }
    return sizeof(litexcnc_toolerator_config_data_t);
}


size_t required_write_buffer(void *module) {
    static litexcnc_toolerator_t *toolerator_module;
    toolerator_module = (litexcnc_toolerator_t *) module;
    return toolerator_module->num_instances * sizeof(litexcnc_toolerator_instance_write_data_t);
}


size_t required_read_buffer(void *module) {
    static litexcnc_toolerator_t *toolerator_module;
    toolerator_module = (litexcnc_toolerator_t *) module;
    return toolerator_module->num_instances * sizeof(litexcnc_toolerator_instance_read_data_t);
}


size_t litexcnc_toolerator_init(litexcnc_module_instance_t **module, litexcnc_t *litexcnc, uint8_t **config) {

    int r;
    char base_name[HAL_NAME_LEN + 1];   // i.e. <board_name>.<board_index>.pwm.<pwm_index>
    char name[HAL_NAME_LEN + 1];        // i.e. <base_name>.<pin_name>

    // Store where the config data starts
    uint8_t *config_start = *config;

    // Create structure in memory
    (*module) = (litexcnc_module_instance_t *)hal_malloc(sizeof(litexcnc_module_instance_t));
    (*module)->prepare_write    = &litexcnc_toolerator_prepare_write;
    (*module)->process_read     = &litexcnc_toolerator_process_read;
    (*module)->configure_module = &litexcnc_toolerator_config;
    (*module)->instance_data = hal_malloc(sizeof(litexcnc_toolerator_t));
        
    // Cast from void to correct type and store it
    litexcnc_toolerator_t *toolerator = (litexcnc_toolerator_t *) (*module)->instance_data;
    instances[num_instances] = toolerator;
    num_instances++;

    // Store the amount of toolerator instances on this board and allocate HAL shared memory
    toolerator->num_instances = *(*config);
    toolerator->instances = (litexcnc_toolerator_instance_t *)hal_malloc(toolerator->num_instances * sizeof(litexcnc_toolerator_instance_t));
    if (toolerator->instances == NULL) {
        LITEXCNC_ERR_NO_DEVICE("Out of memory!\n");
        return -ENOMEM;
    }
    (*config) += 1;

    // Create the pins and params in the HAL
    for (size_t i=0; i<toolerator->num_instances; i++) {
        litexcnc_toolerator_instance_t *instance = &(toolerator->instances[i]);
        
        // Store the amount of tools in the toolchanger
        instance->hal.param.tool_count = *(*config);
        (*config) += 1;
        
        // Create the basename
        LITEXCNC_CREATE_BASENAME("toolerator", i);

        // Create the params
        // Param types: float, bit, u32, s32
        // Param directions: HAL_RO, HAL_RW
        LITEXCNC_CREATE_HAL_PARAM("tool_count", u32, HAL_RO, &(instance->hal.param.tool_count));

        // Create the pins
        // Pin types: float, bit, u32, s32
        // Pin directions: HAL_IN, HAL_OUT, HAL_IO
        LITEXCNC_CREATE_HAL_PIN("status", u32, HAL_OUT, &(instance->hal.pin.status));
        LITEXCNC_CREATE_HAL_PIN("error", bit, HAL_OUT, &(instance->hal.pin.error));
        LITEXCNC_CREATE_HAL_PIN("homing", bit, HAL_OUT, &(instance->hal.pin.homing));
        LITEXCNC_CREATE_HAL_PIN("homed", bit, HAL_OUT, &(instance->hal.pin.homed));
        LITEXCNC_CREATE_HAL_PIN("tool-change", bit, HAL_IN, &(instance->hal.pin.tool_change));
        LITEXCNC_CREATE_HAL_PIN("tool-changed", bit, HAL_OUT, &(instance->hal.pin.tool_changed));
        LITEXCNC_CREATE_HAL_PIN("tool-number", u32, HAL_IN, &(instance->hal.pin.tool_number));
        LITEXCNC_CREATE_HAL_PIN("current-tool", u32, HAL_OUT, &(instance->hal.pin.current_tool));
    }

    // Move correct amount of bytes for the next module
    *config = config_start + 4;

    return 0;
}



int litexcnc_toolerator_config(void *module, uint8_t **data, int period) {

    // NOT USED
    
    // Return success
    return 0;
}



int litexcnc_toolerator_prepare_write(void *module, uint8_t **data, int period) {
    
    // Store where the data starts
    static uint8_t *data_start;
    data_start = *data;
    
    // Convert the module to an instance of toolerator
    static litexcnc_toolerator_t *toolerator;
    toolerator = (litexcnc_toolerator_t *) module;

    // Add any code which prepares data to be written to the FPGA here!
    // - module level
    
    // - instance level
    for (size_t i=0; i<toolerator->num_instances; i++) {
        // Get toolerator to the stepgen instance
        static litexcnc_toolerator_instance_t *instance;
        instance = &(toolerator->instances[i]);

        // Create an instance of the data to be copied to the FPGA
        litexcnc_toolerator_instance_write_data_t instance_data;
        instance_data.enable = *(instance->hal.pin.enable) ? 1 : 0;
        instance_data.tool_change = *(instance->hal.pin.tool_change) ? 1 : 0;
        instance_data.tool_number = *(instance->hal.pin.tool_number) % instance->hal.param.tool_count;

        // Write the data to the FPGA
        memcpy(*data, &instance_data, sizeof(litexcnc_toolerator_instance_write_data_t));
        *data += sizeof(litexcnc_toolerator_instance_write_data_t);
    }

    // Move the pointer to the end of the configuration data. This aims at preventing
    // any mis-alignment of data.
    *data = data_start + required_write_buffer(module);

    // Return success
    return 0;
}


int litexcnc_toolerator_process_read(void *module, uint8_t **data, int period) {
    
    // Store where the data starts
    static uint8_t *data_start;
    data_start = *data;
    
    // Convert the module to an instance of toolerator
    static litexcnc_toolerator_t *toolerator;
    toolerator = (litexcnc_toolerator_t *) module;

    // Add any code which processes the read data from the FPGA
    for (size_t i=0; i<toolerator->num_instances; i++) {
        // Get toolerator to the stepgen instance
        static litexcnc_toolerator_instance_t *instance;
        instance = &(toolerator->instances[i]);

        // Read the data and store it on the instance
        static litexcnc_toolerator_instance_read_data_t instance_data;
        memcpy(&instance_data, *data, sizeof(litexcnc_toolerator_instance_read_data_t));
        *data += sizeof(litexcnc_toolerator_instance_read_data_t);

        // Convert data to HAL-structure
        *(instance->hal.pin.status) = instance_data.status;
        switch(instance_data.status) {
            case 0x02:  // HOME_SEARCHING
            case 0x03:  // HOME_BACK_OFF
            case 0x04:  // HOME_LATCHING
            case 0x05:  // HOME_MOVE_TO_ZERO
                *(instance->hal.pin.homing) = true;
                *(instance->hal.pin.tool_changed) = false;
                break;
            case 0x06:  // MOVING FORWARD
            case 0x07:  // MOVING BACKWARD
                *(instance->hal.pin.tool_changed) = false;
                break;
            case 0x08:  // READY
                // This indicates the toolerator is ready for a new command. When the `toolchange` is
                // TRUE, this will set `toolchanged` HIGH as well to indicate the toolchange has been
                // finished.
                *(instance->hal.pin.tool_changed) = *(instance->hal.pin.tool_change);
                break;
            case 0x09:  // ERROR
                *(instance->hal.pin.tool_changed) = false;
                *(instance->hal.pin.error) = true;
        }
        *(instance->hal.pin.homed) = instance_data.homed;
        *(instance->hal.pin.current_tool) = instance_data.tool_number;
    }

    // Move the pointer to the end of the configuration data. This aims at preventing
    // any mis-alignment of data.
    *data = data_start + required_read_buffer(module);

    // Return success
    return 0;
}

