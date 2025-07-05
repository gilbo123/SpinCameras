from __future__ import annotations

from datetime import datetime
from os.path import isdir
from queue import Queue
from time import sleep
from typing import Any, Callable, Optional
from dataclasses import dataclass
from toml import load as toml_load 

import PySpin
from PyspinCameras.CamEventHandler import CamImageEventHandler
from PyspinCameras.CamReset import CamReset

# __version__ = toml_load("pyproject.toml")["project"]["version"]

@dataclass
class Camera:
    """Camera object to control a Flir camera."""

    _cams: PySpin.CameraList
    _cam_index: int

    def __post_init__(self) -> PySpin.CameraPtr:
        """
        Post initialisation function to get the camera based on the index.

        :return: Camera object
        :rtype: PySpin.CameraPtr
        """

        # callback function flag
        self.callback_set: bool = False

        # get the camera based on index
        self.cam: PySpin.CameraPtr = self._cams.GetByIndex(self._cam_index)

        # initialise the camera
        self.initialise()
        
        # get the device serial number
        self.device_serial_number: str = self.cam.DeviceSerialNumber.GetValue()

        # get the device model name
        self.device_model_name: str = self.cam.DeviceModelName.GetValue()

        # get the device vendor name
        self.device_vendor_name: str = self.cam.DeviceVendorName.GetValue()

        # height and width
        self.height: int = self.cam.Height.GetValue()
        self.width: int = self.cam.Width.GetValue()
        # resolution
        self.resolution: str = f"{(self.width*self.height)/1000000:.2f}MP"
        self.pixel_format: str = self.cam.PixelFormat.GetCurrentEntry().GetName().split("PixelFormat_")[1]



        # get the device ip address
        # check if the device is GigE or USB
        # GigE
        if "-PGE-" in self.device_model_name:
            self.device_ip_address: str = self.convert_ip_to_str(self.cam.GevCurrentIPAddress.GetValue())
        # USB
        elif "-U3-" in self.device_model_name:
            self.device_ip_address: str = None
        # Unknown
        else:
            raise ValueError(f"Unknown device model name: {self.device_model_name}")

        # get the device version
        self.device_version: str = self.cam.DeviceVersion.GetValue()
        self.device_user_id: str = self.cam.DeviceUserID.GetValue()
        self.cam.DeInit()

        return self.cam
    
    
    def __repr__(self) -> str:
        """
        Return the camera serial number and model name.

        :return: Camera serial number and model name.
        :rtype: str
        """

        return (
            "\nCamera(\n"
            f"  Model: {self.device_model_name} (Serial: {self.device_serial_number})\n"
            f"  Index: {self._cam_index + 1} (out of {len(self._cams)} cameras)\n"
            f"  Local IP Address: {self.device_ip_address}\n"
            f"  Height: {self.height}\n"
            f"  Width: {self.width}\n"
            f"  Resolution: {self.resolution}\n"
            f"  Pixel Format: {self.pixel_format}\n"
            f"  Temperature: {self.device_temperature:.2f}\u2103\n"
            f"  Initialised: {self.is_initialised()}\n"
            f"  Streaming: {self.is_streaming()}\n"
            f"  Callback set: {self.callback_set}\n"
            ")\n"
        )


    ###################
    ### TEMPERATURE ###
    ###################

    @property
    def device_temperature(self) -> float:
        """
        Return the temperature of the device.

        :return: Temperature of the device.
        :rtype: float
        """

        if not self.is_initialised():
            print("Unable to access device. Please use `initialise_cameras()` before setting parameters.")
            return -1.0
        
        try:
            # set the device temp after capture
            temp = PySpin.CFloatPtr(
                self.cam.GetNodeMap().GetNode("DeviceTemperature")
            ).GetValue()
            return temp

        except PySpin.SpinnakerException as ex:
            print("Error: %s" % ex)
            return -1.0

    #########################
    ### CONVERT_IP_TO_STR ###
    #########################

    def convert_ip_to_str(self, ip: int) -> str:
        """
        Convert the ip address to a string.

        :param ip: Ip address
        :type ip: PySpin.GenICam.IpAddress
        :return: Ip address as a string
        :rtype: str
        """

        return f"{ip >> 24 & 0xFF}.{ip >> 16 & 0xFF}.{ip >> 8 & 0xFF}.{ip & 0xFF}"

    ######################
    ### IS_INITIALISED ###
    ######################

    def is_initialised(self) -> bool:
        """
        Check if the camera is initialised.

        :return: True if initialised, False otherwise
        :rtype: bool
        """

        return self.cam.IsInitialized()

    ####################
    ### IS_STREAMING ###
    ####################

    def is_streaming(self) -> bool:
        """
        Check if the camera is streaming.

        :return: True if streaming, False otherwise
        :rtype: bool
        """

        return self.cam.IsStreaming()

    ########################
    ### INITIALISATION ###
    ########################

    def initialise(self) -> bool:
        """
        Initialise the camera.

        :return: True if successful, False otherwise
        :rtype: bool
        """

        if not self.cam.IsInitialized():
            self.cam.Init()
        return True

    ########################
    ### DEINITIALISATION ###
    ########################

    def deinitialise(self) -> bool:
        """
        Deinitialise the camera. Resets a callback function if required.

        :return: True if successful, False otherwise
        :rtype: bool
        """

        try:
            if self.cam.IsInitialized():
                # check image event registers
                if self.callback_set:
                    self.cam.UnregisterEventHandler(self.event_handler)
                
                # ready to deinit
                self.cam.DeInit()
                return True
            return False

        except PySpin.SpinnakerException as ex:
            print("Error: %s" % ex)
            return False

    #########################
    ### START_ACQUISITION ###
    #########################

    def start_acquisition(self) -> bool:
        """
        Start the acquisition of images.

        :return: True if successful, False otherwise
        :rtype: bool
        """
        try:
            if not self.cam.IsStreaming():
                self.cam.BeginAcquisition()
            else:
                print("Camera already streaming.")
                return False

            return True

        except PySpin.SpinnakerException as ex:
            print("Error: %s" % ex)
            return False

    ########################
    ### STOP_ACQUISITION ###
    ########################

    def stop_acquisition(self) -> bool:
        """
        Stop the acquisition of images.

        :return: True if successful, False otherwise
        :rtype: bool
        """

        try:
            if self.cam.IsStreaming():
                self.cam.EndAcquisition()
                return True
            return False

        except PySpin.SpinnakerException as ex:
            print("Error: %s" % ex)
            return False

    ##############################
    ### GRAB AND CONVERT IMAGE ###
    ##############################

    def get_next_image(self) -> PySpin.ImagePtr | None:
        """
        Grab an image and convert it to RGB24 format.

        :return: ImagePtr if successful, None otherwise
        :rtype: PySpin.ImagePtr
        """

        if not self.is_initialised():
            print("Unable to access device. Please use `initialise_cameras()` before setting parameters.")
            return False

        try:
            # Retrieve next received image
            image_result: PySpin.ImagePtr = self.cam.GetNextImage()

            # Ensure image completion
            if image_result.IsIncomplete():
                print(
                    "Image incomplete with image status %d..."
                    % image_result.GetImageStatus()
                )
                return None

            return image_result

        except PySpin.SpinnakerException as ex:
            print("Error: %s" % ex)
            return None

    #########################
    ### CALLBACK_FUNCTION ###
    #########################

    def set_callback_function(self, func: Callable) -> bool:
        """
        Set the callback function for the camera.

        :param func: Callback function to set.
        :type func: Callable
        :return: True if successful, False otherwise
        :rtype: bool
        """

        # set the image callback function, if required
        # TODO - check parameters match. Protocol??
        if not callable(func):
            print("Callback function not callable.")
            return False

        if not self.is_initialised():
            print("Unable to access device. Please use `initialise_cameras()` before setting parameters.")
            return False
        
        try:

            # create the event handler - with the defined function
            self.event_handler: CamImageEventHandler = CamImageEventHandler(
                cam=self.cam, callback=func
            )

            # register the event handler
            self.cam.RegisterEventHandler(self.event_handler)

            # register the event handler
            # res, self.image_event_handler = self.event_handler.configure_image_events(
            #     self.cam
            # )
            # set flag
            self.callback_set = True

            # success
            return True

        except PySpin.SpinnakerException as ex:
            print("Error: %s" % ex)
            return False

        # return res

    ################################
    ### EXECUTE SOFTWARE TRIGGER ###
    ################################

    def execute_software_trigger(self) -> bool:
        """
        Send a software trigger to the camera using asyncio.
        Delay before trigger in seconds.

        :return: True if successful, False otherwise
        :rtype: bool
        """
        
        if not self.is_initialised():
            print("Unable to access device. Please use `initialise_cameras()` before setting parameters.")
            return False
        
        try:
            # Trigger the camera
            self.cam.TriggerSoftware.Execute()
            print("Software trigger executed.")
            return True

        except PySpin.SpinnakerException as ex:
            print("Error: %s" % ex)
            return False

        # success
        return True

    ########################
    ### ACQUISITION_MODE ###
    ########################

    def set_acquisition_mode(self, acq_mode: str) -> bool:
        """
        Set the acquisition mode. `continuous`, `single`, or `multiple`.

        :param acq_mode: Acquisition mode to set. Use '`continuous`', '`single`', or '`multiple`'.
        :type acq_mode: str
        :return: True if successful, False otherwise
        :rtype: bool
        """

        if not self.is_initialised():
            print("Unable to access device. Please use `initialise_cameras()` before setting parameters.")
            return False
        
        try:
            if acq_mode == "continuous":
                # Set acquisition mode to continuous
                if self.cam.AcquisitionMode.GetAccessMode() != PySpin.RW:
                    print("Unable to set acquisition mode to continuous. Aborting...")
                    return False
                self.cam.AcquisitionMode.SetValue(PySpin.AcquisitionMode_Continuous)
            elif acq_mode == "single":
                # Set acquisition mode to single frame
                if self.cam.AcquisitionMode.GetAccessMode() != PySpin.RW:
                    print("Unable to set acquisition mode to single frame. Aborting...")
                    return False
                self.cam.AcquisitionMode.SetValue(PySpin.AcquisitionMode_SingleFrame)

            elif acq_mode == "multiple":
                # Set acquisition mode to single frame
                if self.cam.AcquisitionMode.GetAccessMode() != PySpin.RW:
                    print("Unable to set acquisition mode to single frame. Aborting...")
                    return False
                self.cam.AcquisitionMode.SetValue(PySpin.AcquisitionMode_MultiFrame)
            else:
                print(
                    "Acquisition mode not recognised. Use `'continuous'`, `'single'`, or `'multiple'`"
                )

            # success
            return True

        except PySpin.SpinnakerException as ex:
            print("Error: %s" % ex)
            return False

    #############################
    ### AQUISITION FRAME RATE ###
    #############################

    def set_frame_rate(self, frame_rate: float) -> bool:
        """
        Set the frame rate for the camera.

        :param frame_rate: Frame rate to set.
        :type frame_rate: float
        :return: True if successful, False otherwise
        :rtype: bool
        """

        if not self.is_initialised():
            print("Unable to access device. Please use `initialise_cameras()` before setting parameters.")
            return False
        
        try:
            # check to ensure frame rate enable is off
            if self.cam.AcquisitionFrameRateEnable.GetAccessMode() != PySpin.RW:
                print("Unable to set frame rate enable. Aborting...")
                return False

            # set frame rate enable
            self.cam.AcquisitionFrameRateEnable.SetValue(True)

            # Check to ensure the node is available
            if self.cam.AcquisitionFrameRate.GetAccessMode() != PySpin.RW:
                print("Unable to set frame rate value. Aborting...")
                return False

            # Set the frame rate
            self.cam.AcquisitionFrameRate.SetValue(frame_rate)

            # success
            return True

        except PySpin.SpinnakerException as ex:
            print("Error: %s" % ex)
            return False

    ################
    ### EXPOSURE ###
    ################

    def set_exposure(self, exp_mode: str = "continuous", exp_time: float = 0.0) -> bool:
        """
        Set the exposure time. Sets `exp_time` in microseconds if `exp_mode="continuous"`.
        Otherwise `once` for once, `off` for off.

        :param exp_mode: Exposure mode to set. Use '`continuous`', '`once`', or '`off`'.
        :type exp_mode: str
        :param exp_time: Exposure time to set.
        :type exp_time: float
        :return: True if successful, False otherwise
        :rtype: bool
        """

        if not self.is_initialised():
            print("Unable to access device. Please use `initialise_cameras()` before setting parameters.")
            return False
        
        try:
            if self.cam.ExposureAuto.GetAccessMode() != PySpin.RW:
                print("Unable to update automatic exposure. Aborting...")
                return False

            if exp_mode == "continuous":
                self.cam.ExposureAuto.SetValue(PySpin.ExposureAuto_Continuous)
            elif exp_mode == "once":
                self.cam.ExposureAuto.SetValue(PySpin.ExposureAuto_Once)
            elif exp_mode == "off":
                self.cam.ExposureAuto.SetValue(PySpin.ExposureAuto_Off)
            else:
                print(
                    f"Exposure mode {exp_mode} not recognised. Use `'continuous'`, `'once'`, or `'off'`."
                )
                return False

            # set expose time if required
            if exp_mode == "off" and exp_time > 0:
                if self.cam.ExposureTime.GetAccessMode() != PySpin.RW:
                    print("Unable to set exposure time. Aborting...")
                    return False

                # Ensure desired exposure time does not exceed the maximum
                exposure_time_to_set = float(exp_time)
                exposure_time_to_set = min(
                    self.cam.ExposureTime.GetMax(), exposure_time_to_set
                )
                self.cam.ExposureTime.SetValue(exposure_time_to_set)
            elif exp_mode == "off" and exp_time == 0:
                print(
                    f"Not setting exposure time {exp_time} with auto mode: {exp_mode}."
                )
                return False
            else:
                # all other modes
                pass

            # success
            return True

        except PySpin.SpinnakerException as ex:
            print("Error: %s" % ex)
            return False

    #####################
    ### WHITE BALANCE ###
    #####################

    def set_white_balance(
        self,
        bal_mode: str = "continuous",
        red_selector: float = 0,
        blue_selector: float = 0,
    ) -> bool:
        """
        Set the white balance mode and balance selector values.
        Sets red and blue selector values if  if `bal_mode="continuous"`.
        Otherwise `once` for once, `off` for off.

        :param bal_mode: White balance mode to set. Use '`continuous`', '`once`', or '`off`'.
        :type bal_mode: str
        :param red_selector: Red balance selector value to set.
        :type red_selector: float
        :param blue_selector: Blue balance selector value to set.
        :type blue_selector: float
        :return: True if successful, False otherwise
        :rtype: bool
        """

        if not self.is_initialised():
            print("Unable to access device. Please use `initialise_cameras()` before setting parameters.")
            return False
        
        try:
            if bal_mode == "continuous":
                self.cam.BalanceWhiteAuto.SetValue(PySpin.BalanceWhiteAuto_Continuous)
            elif bal_mode == "once":
                self.cam.BalanceWhiteAuto.SetValue(PySpin.BalanceWhiteAuto_Once)
            elif bal_mode == "off":
                self.cam.BalanceWhiteAuto.SetValue(PySpin.BalanceWhiteAuto_Off)
            else:
                print(
                    f"white balance mode {bal_mode} not found.  Use `'continuous'`, `'once'`, or `'off'`."
                )
                return False

            if bal_mode == "off" and red_selector > 0 and blue_selector > 0:
                if self.cam.BalanceRatioSelector.GetAccessMode() != PySpin.RW:
                    print("Unable to set balance ratio. Aborting...")
                    return False

                self.cam.BalanceRatioSelector.SetValue(PySpin.BalanceRatioSelector_Red)
                self.cam.BalanceRatio.SetValue(red_selector)

                self.cam.BalanceRatioSelector.SetValue(PySpin.BalanceRatioSelector_Blue)
                self.cam.BalanceRatio.SetValue(blue_selector)
            else:
                print(
                    f"Not setting white balance selectors {[red_selector, blue_selector]} using white balance mode: {bal_mode}"
                )
                return True

            # success
            return True

        except PySpin.SpinnakerException as ex:
            print("Error: %s" % ex)
            return False

    ############
    ### GAIN ###
    ############
    def set_gain(self, gain_mode: str = "continuous", gain: float = 0.0) -> bool:
        """
        Set the gain mode and value if needed.
        Sets `gain` in dB (float value0) if `gain_mode="continuous"`.
        Otherwise `once` for once, `off` for off.

        :param gain_mode: Gain mode to set. Use '`continuous`', '`once`', or '`off`'.
        :type gain_mode: str
        :param gain: Gain value to set.
        :type gain: float
        :return: True if successful, False otherwise
        :rtype: bool
        """

        if not self.is_initialised():
            print("Unable to access device. Please use `initialise_cameras()` before setting parameters.")
            return False
        
        try:
            if gain_mode == "continuous":
                self.cam.GainAuto.SetValue(PySpin.GainAuto_Continuous)
            elif gain_mode == "once":
                self.cam.GainAuto.SetValue(PySpin.GainAuto_Once)
            elif gain_mode == "off":
                self.cam.GainAuto.SetValue(PySpin.GainAuto_Off)
            else:
                print(
                    f"Gain mode {gain_mode} not recognised. Use `'continuous'`, `'once'`, or `'off'`."
                )
                return False

            if self.cam.Gain.GetAccessMode() != PySpin.RW:
                print("Unable to set gain. Aborting...")
                return False

            if gain_mode == "off" and gain > 0.0:
                gain_to_set = gain
                gain_to_set = min(self.cam.Gain.GetMax(), gain_to_set)
                self.cam.Gain.SetValue(gain_to_set)
            else:
                print(f"Not setting gain value {gain} using gain mode: {gain_mode}")
                return False

            # success
            return True

        except PySpin.SpinnakerException as ex:
            print("Error: %s" % ex)
            return False

    #############
    ### GAMMA ###
    #############

    def set_gamma(self, gamma_enable: bool = False, gamma: float = 0.0) -> bool:
        """
        Set the gain mode and value if needed.
        Sets `gamma` in dB (float value0) if `gamma_mode="continuous"`.
        Otherwise `once` for once, `off` for off.

        :param gamma_enable: Enable gamma correction.
        :type gamma_enable: bool
        :param gamma: Gamma value to set.
        :type gamma: float
        :return: True if successful, False otherwise
        :rtype: bool
        """

        if not self.is_initialised():
            print("Unable to access device. Please use `initialise_cameras()` before setting parameters.")
            return False
        
        try:
            if gamma_enable:
                self.cam.GammaEnable.SetValue(True)
            else:
                self.cam.GammaEnable.SetValue(False)

            if self.cam.Gamma.GetAccessMode() != PySpin.RW:
                print("Unable to set gamma. Aborting...")
                return False

            # set the gamma
            if gamma_enable and gamma > 0.0:
                gamma_to_set = gamma
                gamma_to_set = min(self.cam.Gamma.GetMax(), gamma_to_set)
                self.cam.Gamma.SetValue(gamma_to_set)
            else:
                print(
                    f"Not setting gamma value {gamma} using gain enable: {gamma_enable}"
                )
                return False

            # success
            return True

        except PySpin.SpinnakerException as ex:
            print("Error: %s" % ex)
            return False

    #####################
    ### STREAM_BUFFER ###
    #####################

    def set_stream_buffer_mode(self, buffer_mode: str = "newest-only") -> bool:
        """
        Set the stream buffer mode.
        Sets `buffer_mode` to '`newest-only`', '`newest-first`', '`oldest-first`', or '`oldest-overwrite`'.

        :param buffer_mode: Buffer mode to set. Use '`newest-only`', '`newest-first`', '`oldest-first`', or '`oldest-overwrite`'.
        :type buffer_mode: str
        :return: True if successful, False otherwise
        :rtype: bool
        """

        if not self.is_initialised():
            print("Unable to access device. Please use `initialise_cameras()` before setting parameters.")
            return False
        
        try:
            stream: PySpin.INodeMap = self.cam.GetTLStreamNodeMap()
            if stream is None:
                print("Unable to get stream node map. Aborting...")
                return False

            # Set the buffer handling mode to newest only
            tlnode: PySpin.CNodePtr = stream.GetNode("StreamBufferHandlingMode")
            if tlnode.GetAccessMode() != PySpin.RW:
                print("Unable to set buffer handling mode. Aborting...")
                return False

            tlnode_ptr: PySpin.CEnumerationPtr = PySpin.CEnumerationPtr(tlnode)
            # check node is valid
            if tlnode_ptr.IsValid() and tlnode_ptr.GetAccessMode() == PySpin.RW:
                if buffer_mode == "newest-only":
                    # set the value for newest only
                    tlnode_ptr.SetIntValue(PySpin.StreamBufferHandlingMode_NewestOnly)
                elif buffer_mode == "newest-first":
                    # set the value for newest only
                    tlnode_ptr.SetIntValue(PySpin.StreamBufferHandlingMode_NewestFirst)
                elif buffer_mode == "oldest-first":
                    # set the value for newest only
                    tlnode_ptr.SetIntValue(PySpin.StreamBufferHandlingMode_OldestFirst)
                elif buffer_mode == "oldest-overwrite":
                    # set the value for newest only
                    tlnode_ptr.SetIntValue(
                        PySpin.StreamBufferHandlingMode_OldestFirstOverwrite
                    )
                else:
                    print(
                        f"Buffer mode {buffer_mode} not recognised. Use '`newest-only`', "
                        "'`newest-first`', '`oldest-first`', or '`oldest-overwrite`'."
                    )

                # success
                return True

            else:
                print("unable to access Stream Buffer Handling node.")
                return False

        except PySpin.SpinnakerException as ex:
            print("Error: %s" % ex)
            return False

    ################
    ### TRIGGER ####
    ################

    def set_trigger_mode(
        self, trigger_mode: str = "off", source: str = "hardware", line: int = -1
    ) -> bool:
        """
        Set the stream trigger mode.
        Sets trigger on `line` if `trigger_mode` = "on", or software trigger if `source` = "software", otherwise sets off.

        :param trigger_mode: Trigger mode to set. Use '`off`' or '`on`'.
        :type trigger_mode: str
        :param source: Trigger source to set. Use '`hardware`' or '`software`'.
        :type source: str
        :param line: Line to set the trigger. Use 0, 1, 2, or 3.
        :type line: int
        :return: True if successful, False otherwise
        :rtype: bool
        """

        if not self.is_initialised():
            print("Unable to access device. Please use `initialise_cameras()` before setting parameters.")
            return False
        
        try:
            # Ensure trigger mode off in order to update
            if self.cam.TriggerMode.GetAccessMode() != PySpin.RW:
                print("Unable to disable trigger mode (node retrieval). Aborting...")
                return False

            # disable trigger to set it
            self.cam.TriggerMode.SetValue(PySpin.TriggerMode_Off)

            # if trigger mode required to be off, return
            if trigger_mode == "off":
                return True

            # logic checks
            if trigger_mode != "on":
                print(
                    f"Trigger mode {trigger_mode} not recognised. Use '`off`' or '`on`'"
                )
                return False

            if source == "hardware" and line == -1:
                print(f"Hardware line must be set for hardware trigger.")
                return False

            # Frame start is the default for most cameras.
            if self.cam.TriggerSelector.GetAccessMode() != PySpin.RW:
                print("Unable to get trigger selector (node retrieval). Aborting...")
                return False
            self.cam.TriggerSource.SetValue(PySpin.TriggerSelector_FrameStart)

            # Select trigger source
            if self.cam.TriggerSource.GetAccessMode() != PySpin.RW:
                print("Unable to get trigger source (node retrieval). Aborting...")
                return False

            # hardware trigger
            if source == "hardware":
                # set correct line
                if line == 0:
                    self.cam.TriggerSource.SetValue(PySpin.TriggerSource_Line0)
                elif line == 1:
                    self.cam.TriggerSource.SetValue(PySpin.TriggerSource_Line1)
                elif line == 2:
                    self.cam.TriggerSource.SetValue(PySpin.TriggerSource_Line2)
                elif line == 3:
                    self.cam.TriggerSource.SetValue(PySpin.TriggerSource_Line3)
                else:
                    print(f"Trigger source {line} not recognised.")
                    return False
                print(f"Hardware trigger set on line {line}.")

            # set the software trigger
            elif source == "software":
                self.cam.TriggerSource.SetValue(PySpin.TriggerSource_Software)
                print("Software trigger set.")
            else:
                print(
                    f"Trigger source {source} not recognised. use '`hardware`' or '`software`'."
                )
                return False

            # Turn trigger mode back on
            # Once the appropriate trigger source has been set, turn trigger mode
            # on in order to retrieve images using the trigger.
            self.cam.TriggerMode.SetValue(PySpin.TriggerMode_On)

            # success
            return True

        except PySpin.SpinnakerException as ex:
            print("Error: %s" % ex)
            return False

    ###################
    ### PACKET SIZE ###
    ###################

    def set_packet_size(self, packet_size: int = 9000) -> bool:
        """
        Set the packet size for the camera.

        :param packet_size: Packet size to set.
        :type packet_size: int
        :return: True if successful, False otherwise
        :rtype: bool
        """
        
        if not self.is_initialised():
            print("Unable to access device. Please use `initialise_cameras()` before setting parameters.")
            return False

        try:
            if self.cam.GevSCPSPacketSize.GetAccessMode() != PySpin.RW:
                print("Unable to set packet size. Aborting...")
                return False

            # Set the value of the packet size
            self.cam.GevSCPSPacketSize.SetValue(packet_size)

            # success
            return True

        except PySpin.SpinnakerException as ex:
            print("Error: %s" % ex)
            return False

    ###############################
    ### DEVICE THROUGHPUT LIMIT ###
    ###############################

    def set_device_throughput_limit(self, limit: int = 150000000) -> bool:
        """
        Set the device throughput limit for the camera.

        :param limit: Throughput limit to set.
        :type limit: int
        :return: True if successful, False otherwise
        :rtype: bool
        """

        if not self.is_initialised():
            print("Unable to access device. Please use `initialise_cameras()` before setting parameters.")
            return False
        
        try:
            if self.cam.DeviceLinkThroughputLimit.GetAccessMode() != PySpin.RW:
                print("Unable to set device throughput limit. Aborting...")
                return False

            # Set the value of the device throughput limit
            self.cam.DeviceLinkThroughputLimit.SetValue(limit)

            # success
            return True

        except PySpin.SpinnakerException as ex:
            print("Error: %s" % ex)
            return False

    ####################
    ### PIXEL FORMAT ###
    ####################

    def set_pixel_format(
        self,
        pixel_format: PySpin.IEnumerationT_PixelFormatEnums = PySpin.PixelFormat_BayerRG8,
    ) -> bool:
        """
        Set the pixel format for the camera.

        :param pixel_format: Pixel format to set.
        :type pixel_format: PySpin.IEnumerationT_PixelFormatEnums (e.g. PySpin.PixelFormat_Mono8, PySpin.PixelFormat_RGB8, etc.)
        :return: True if successful, False otherwise
        :rtype: bool
        """
        # check if camera is initialised
        if not self.is_initialised():
            print("Unable to access device. Please use `initialise_cameras()` before setting parameters.")
            return False
        
        try:
            if self.cam.PixelFormat.GetAccessMode() != PySpin.RW:
                print("Unable to set pixel format. Aborting...")
                return False

            ### Check to see if the desired pixel format is supported ###
            # Get all entries
            entries = self.cam.PixelFormat.GetEntries()

            # check the pixel format is less than the number of entries
            if pixel_format >= len(entries):
                print(f"Pixel format 'ID:{pixel_format}' not available.")
                return False

            # check if pixe_format is in entries
            if PySpin.IsAvailable(entries[pixel_format]):
                # Write the pixel format to the camera
                self.cam.PixelFormat.SetValue(pixel_format)
                return True
            else:
                available_pixel_formats = []
                for entry in entries:
                    if PySpin.IsAvailable(entry):
                        available_pixel_formats.append(entry.GetDisplayName())

                print(
                    f"Pixel format {entries[pixel_format].GetDisplayName()} not available."
                )
                print(f"Available pixel formats are: {available_pixel_formats}")

                return False

        except PySpin.SpinnakerException as ex:
            print("Error: %s" % ex)
            return False

    ###############
    ### __DEL__ ###
    ###############

    def __del__(self) -> None:
        """
        Destructor to delete the camera object.

        :return: None
        """
        try:
            self.stop_acquisition()
        except PySpin.SpinnakerException:
            pass
        try:
            self.deinitialise()
        except PySpin.SpinnakerException:
            pass
        try:
            del self.cam
        except PySpin.SpinnakerException:
            pass


@dataclass
class Cameras:

    system: PySpin.System
    save_folder: Optional[str] = None
    queue: Optional[Queue[dict[str, PySpin.ImagePtr | str]]] = None
    grab_timeout: int = 5000
    verbose: bool = False

    def __post_init__(self) -> list[Camera]:
        """
        Gets all the cameras attached and returns a list of Cameras, otherwise an empty list.

        :return: List of Camera objects
        :rtype: list[Camera]
        """

        # set the library version
        spin_version: PySpin.LibraryVersion = self.system.GetLibraryVersion()
        self.spinnaker_version: str = (
            f"{spin_version.major}."
            f"{spin_version.minor}."
            f"{spin_version.type}."
            f"{spin_version.build}"
        )

        # pyspin errors
        self.pyspin_errors: dict[str, str] = {
            "Camera is on a wrong subnet.": "ip",
            "GenICam::OutOfRangeException=": "range",
            "Please try reconnecting the device.": "range",
        }

        # camera reset module
        self.cam_reset: CamReset = CamReset(system=self.system)

        # initialise iterations counter for zero cameras
        self.__iter_counter: int = 0
        self.__iter_end: int = 0

         # check folder
        if self.save_folder is not None:
            if not isdir(self.save_folder):
                print(f"Save folder {self.save_folder} not found. Exiting.")
                exit()

        # set up the cameras and correct any errors
        self.set_up_cams_and_correct_errors()

        # Create ImageProcessor instance for post processing images
        self.processor = PySpin.ImageProcessor()

        # Set default image processor color processing method
        self.processor.SetColorProcessing(
            PySpin.SPINNAKER_COLOR_PROCESSING_ALGORITHM_HQ_LINEAR
        )

        # update iteration counter
        self.__iter_end: int = len(self.camera_list)

        # acquiring flag
        self.acquiring: bool = False

        return self.camera_list

    def __repr__(self) -> str:
        """
        Return the number of cameras detected.

        :return: Number of cameras and their breif details.
        :rtype: str
        """

        # make a string wi the model and serial of each camera detected
        camera_details: str = ""
        for i, cam in enumerate(self.camera_list):
            camera_details += f"\n      Camera {i + 1} of {len(self.camera_list)} - Model: {cam.device_model_name} ({cam.device_serial_number})"

        return (
            "\nCameras(\n"
            f"  Spinnaker version: {self.spinnaker_version}\n"
            f"  Number of cameras detected: {len(self.camera_list)}\n"
            f"  Save folder: {self.save_folder}\n"
            f"  Queue size: [{self.queue.qsize() if self.queue is not None else 0}]\n"
            f"  Camera details: {camera_details}\n"
            ")\n"
        )

    # define iterable object
    def __iter__(self):
        return self

    def __next__(self):
        if self.__iter_end == 0:
            raise StopIteration
        if self.__iter_counter >= self.__iter_end:
            raise StopIteration
        else:
            self.__iter_counter += 1
            return self.camera_list[self.__iter_counter - 1]

    def __len__(self) -> int:
        return len(self.camera_list)

    def __getitem__(self, index: int) -> Camera:
        return self.camera_list[index]

    @property
    def version_info(self) -> str:
        """
        Return the version of Spinnaker and the application.

        :return: Version of Spinnaker and the application
        :rtype: str
        """
        toml_file = toml_load("pyproject.toml")
        return f"SpinCameras v{toml_file['project']['version']} - Spinnaker v{self.spinnaker_version}"

    @property
    def camera_info(self) -> str:
        """
        Return the information of each camera.

        :return: Information of each camera
        :rtype: str
        """
        camera_info: dict[str, str] = {}
        for cam in self.camera_list:
            camera_info[cam.device_serial_number] = {
                "Model": cam.device_model_name,
                "Serial": cam.device_serial_number,
                "Vendor": cam.device_vendor_name,
                "Firmware Version": cam.device_version,
                "User ID": cam.device_user_id,
            }
        return camera_info

    def set_up_cams_and_correct_errors(self) -> None:
        """
        Set up the cameras and correct any errors.
        """
        # the list of cameras to return
        self.camera_list: list[Camera] = []

        # Retrieve list of cameras from the system
        self._cams: PySpin.CameraList = self.system.GetCameras()

        num_cameras = self._cams.GetSize()
        if self.verbose:
            print(f"Number of cameras detected: {num_cameras}")

        # Finish if there are no cameras
        if num_cameras == 0:

            # Clear camera list before releasing system
            self._cams.Clear()

            # Release system instance
            self.system.ReleaseInstance()

            print("Not enough cameras!")
            exit()

        # connect to cameras
        # correct any errors
        # e.g. wrong subnet, out of range, etc.
        # need to send all cameras to the camera object
        cam: PySpin.Camera
        for i, cam in enumerate(self._cams):
            try:
                # Create camera object for each camera
                cam_obj: Camera = Camera(_cams=self._cams, _cam_index=i)
                if self.verbose:
                    print(f"Camera {i + 1} of {len(self._cams)} connected.")

            # if error, correct it and try again
            except PySpin.SpinnakerException as ex:
                if self.verbose:
                    print(f"Error: {ex}")
                # check which error
                e_type: str = ""
                for err, t in self.pyspin_errors.items():
                    if err in str(ex).split("Spinnaker: ")[1]:
                        e_type = t

                # if not expected, pass?
                if e_type == "":
                    pass

                # if value error (out of range), reset cam
                if e_type == "range":
                    err_str: str = f"Error: {ex}.\n"
                    print(err_str)
                    self.cam_reset.reset_cam(cam=cam)

                # ip subnet wrong
                if e_type == "ip":
                    err_str: str = f"Error: {ex}.\n"
                    print(err_str)
                    self.cam_reset.force_ip_by_cam(cam=cam)

                # clear the camera list
                self.camera_list = []
                self._cams.Clear()

                # wait for camera
                sleep(20)

                # try again
                self.set_up_cams_and_correct_errors()

            # if no error, add to camera list
            else:
                self.camera_list.append(cam_obj)

    def get_camera_by_serial(self, serial: str) -> Optional[Camera]:
        """
        Get the camera object by serial number.

        :param serial: Serial number of the camera.
        :type serial: str
        :return: Camera object if found, None otherwise
        :rtype: Optional[Camera]
        """

        for cam in self.camera_list:
            if cam.device_serial_number == serial:
                return cam

        return None

    def initialise_cameras(self) -> None:
        """
        Initialise each camera in the list.

        :return: None
        :rtype: None
        """

        # Initialize each camera
        for cam in self.camera_list:
            # Initialize camera
            cam.initialise()

    def deinitialise_cameras(self) -> None:
        """
        Deinitialise each camera in the list.

        :return: None
        :rtype: None
        """

        # Initialize each camera
        for cam in self.camera_list:
            # Initialize camera
            cam.deinitialise()

    def _begin_capture(self) -> None:
        """
        Begin the acquisition for each camera and start capture.
        :return: None
        :rtype: None
        """

        # begin acquisition for each camera
        for cam in self.camera_list:
            # start the camera
            cam.start_acquisition()

        # acquiring flag
        self.acquiring: bool = True

    def _stop_capture(self) -> None:
        """
        Stop the acquisition for each camera.

        :return: None
        :rtype: None
        """

        # begin acquisition for each camera
        for cam in self.camera_list:
            # start the camera
            cam.stop_acquisition()

        # acquiring flag
        self.acquiring: bool = False

    def release_all_cameras(self) -> None:
        """
        Release the cameras and clear the camera list.

        :return: None
        :rtype: None
        """

        # Clear camera list before releasing system
        if self._cams:
            self._cams.Clear()
        self.camera_list = []

    def acquire_images(self, num_images: int = -1) -> None:
        """
        This function acquires and saves images from each device.
        Acquires num_images from each camera if specified.

        :param num_images: Number of images to acquire. Default is -1 (continuous).
        :type num_images: int
        :return: None
        :rtype: None
        """

        try:
            # check if cameras exist
            if len(self.camera_list) == 0:
                print("No cameras detected. Exiting.")
                return

            # Prepare each camera to acquire images
            self._begin_capture()

            #######################################################

            ## LOOP
            _iter: int = -1
            while self.acquiring:
                # got images from all camers
                _iter += 1

                # check if we have enough images
                if num_images != -1 and num_images == _iter:
                    self.acquiring = False
                    if self.verbose:
                        print(
                            f"Acquired {num_images} images from {len(self.camera_list)} cameras."
                        )
                    break

                for i, cam in enumerate(self.camera_list):
                    # check if cam has a callback function
                    if self.camera_list[i].callback_set:
                        # check number of images
                        if (
                            self.camera_list[i].event_handler.get_image_count()
                            == num_images
                        ):
                            self.acquiring = False
                            if self.verbose:
                                print(
                                    f"HANDLER acquired {num_images} images from {len(self.camera_list)} cameras."
                                )
                            break
                        # wait for callback to be called
                        sleep(0.1)
                        continue

                    # get the handle to the raw camera for quick access
                    cam: PySpin.CameraPtr = self.camera_list[i].cam

                    # Retrieve next received image and ensure image completion
                    image_result: PySpin.ImagePtr = cam.GetNextImage()

                    if image_result.IsIncomplete():
                        print(
                            "Image incomplete with image status %d ... \n"
                            % image_result.GetImageStatus()
                        )
                    else:
                        # Print image information
                        if self.verbose:
                            width = image_result.GetWidth()
                            height = image_result.GetHeight()
                            print(
                                "Camera %d grabbed image %d, width = %d, height = %d"
                                % (i, _iter, width, height)
                            )

                        # Retrieve device serial number for filename
                        device_serial_number: str = self.camera_list[
                            i
                        ].device_serial_number

                        # Convert image to mono 8
                        image_converted: PySpin.ImagePtr = self.processor.Convert(
                            image_result, PySpin.PixelFormat_RGB8
                        )

                        # Create a unique filename
                        dt: str = datetime.now().strftime("%Y-%m-%dT%H:%M:%S:%f")
                        filename = f"cam-{device_serial_number}_img-{_iter}_{dt}.jpg"

                        # save if save folder
                        if self.save_folder is not None:
                            # Save image
                            filename = f"{self.save_folder}/{filename}"
                            image_converted.Save(filename)

                        # Queue set
                        if self.queue is not None:
                            # save to queue
                            self.queue.put(
                                {"image": image_converted, "filename": filename}
                            )

                        # print filename if nothing else
                        if self.verbose:
                            print("Image grabbed at: %s" % filename)

                    # Release image
                    image_result.Release()

                    if self.verbose:
                        print()

        except PySpin.SpinnakerException as ex:
            print("Error: %s" % ex)

        except KeyboardInterrupt:
            print("Keyboard interrupt detected.")
            self.acquiring = False

    def __del__(self) -> None:
        """
        Destructor to delete all cameras and clear the camera list.

        :return: None
        :rtype: None
        """

        # self.release_all_cameras()
        for camera in self.camera_list:
            del camera
        self.release_all_cameras()
