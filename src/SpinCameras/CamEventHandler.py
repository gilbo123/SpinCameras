from datetime import datetime
from typing import Callable, Optional, Tuple

import PySpin

# from numpy import ndarray


class CamImageEventHandler(PySpin.ImageEventHandler):
    """
    This class defines the properties, parameters, and the event handler itself. Take a
    moment to notice what parts of the class are mandatory, and what have been
    added for demonstration purposes. First, any class used to define image event handlers
    must inherit from ImageEventHandler. Second, the method signature of OnImageEvent()
    must also be consistent. Everything else - including the constructor,
    destructor, properties, body of OnImageEvent(), and other functions -
    is particular to the example.
    """

    def __init__(self, cam: PySpin.CameraPtr, callback: Callable) -> None:
        """
        Constructor. Retrieves serial number of given camera and sets image counter to 0.

        :param cam: Camera instance, used to get serial number for unique image filenames.
        :type cam: CameraPtr
        :rtype: None
        """
        super(CamImageEventHandler, self).__init__()

        # set the callback function
        self.callback = callback

        nodemap = cam.GetTLDeviceNodeMap()

        # Retrieve Current pixel format
        # if cam.PixelFormat.GetAccessMode() != PySpin.RW:
        #     self.pix_for = PySpin.PixelFormat_BGR8
        #     print("Unable to read pixel format, using BGR8")
        # else:
        pf = cam.PixelFormat.GetCurrentEntry()
        self.pix_for = cam.PixelFormat.GetValue()
        print(f"Event Handler - Pixel Colour Processing Format: {pf.GetSymbolic()}")

        # Retrieve device serial number
        node_device_serial_number = PySpin.CStringPtr(
            nodemap.GetNode("DeviceSerialNumber")
        )

        if PySpin.IsReadable(node_device_serial_number):
            self._device_serial_number = node_device_serial_number.GetValue()

        # Initialize image counter to 0
        self._image_count = 0

        # Release reference to camera
        # NOTE: Unlike the C++ examples, we cannot rely on pointer objects being automatically
        # cleaned up when going out of scope.
        # The usage of del is preferred to assigning the variable to None.
        del cam

        # Create ImageProcessor instance for post processing images
        self._processor = PySpin.ImageProcessor()

        # Set default image processor color processing method
        #
        # *** NOTES ***
        # By default, if no specific color processing algorithm is set, the image
        # processor will default to NEAREST_NEIGHBOR method.
        self._processor.SetColorProcessing(
            PySpin.SPINNAKER_COLOR_PROCESSING_ALGORITHM_HQ_LINEAR
        )

    def OnImageEvent(self, image: PySpin.ImagePtr) -> None:
        """
        This method defines an image event. In it, the image that triggered the
        event is converted and saved before incrementing the count. Please see
        Acquisition example for more in-depth comments on the acquisition
        of images.

        :param image: Image from event.
        :type image: ImagePtr
        :rtype: None
        """

        print("Image event occurred...")

        # Check if image is incomplete
        if image.IsIncomplete():
            print("Image incomplete with image status %i..." % image.GetImageStatus())

        else:
            # Print image info
            # print(
            #     "Grabbed image %i, width = %i, height = %i"
            #     % (self._image_count, image.GetWidth(), image.GetHeight())
            # )

            # Convert image colour format
            image_converted: PySpin.ImagePtr = self._processor.Convert(
                image, self.pix_for  # PySpin.PixelFormat_BayerRG8
            )

            # Create unique filename and save image
            dt: str = datetime.now().strftime("%Y-%m-%dT%H:%M:%S:%f")
            if self._device_serial_number:
                filename = (
                    f"cam-{self._device_serial_number}_img-{self._image_count}_{dt}.jpg"
                )

            else:  # if serial number is empty
                filename = f"img-{self._image_count}_{dt}.jpg"

            ### CALLBACK FUNCTION ###
            self.callback(image_converted, filename)
            
            # Increment image counter
            self._image_count += 1

    def get_image_count(self) -> int:
        """
        Getter for image count.

        :return: Number of images saved.
        :rtype: int
        """
        return self._image_count

    def configure_image_events(
        self, cam: PySpin.CameraPtr
    ) -> Tuple[bool, "CamImageEventHandler"]:
        """
        This function configures the example to execute image events by preparing and
        registering an image event.

        :param cam: Camera instance to configure image event.
        :return: tuple(result, image_event_handler)
            WHERE
            result is True if successful, False otherwise
            image_event_handler is the event handler
        :rtype: (bool, ImageEventHandler)
        """
        try:
            result = True

            #  Create image event handler
            #
            #  *** NOTES ***
            #  The class has been constructed to accept a camera pointer in order
            #  to allow the saving of images with the device serial number.
            image_event_handler: CamImageEventHandler = CamImageEventHandler(
                cam, self.callback
            )

            #  Register image event handler
            #
            #  *** NOTES ***
            #  Image events are registered to cameras. If there are multiple
            #  cameras, each camera must have the image events registered to it
            #  separately. Also, multiple image events may be registered to a
            #  single camera.
            #
            #  *** LATER ***
            #  Image event handlers must be unregistered manually. This must be done prior
            #  to releasing the system and while the image events are still in
            #  scope.
            cam.RegisterEventHandler(image_event_handler)

        except PySpin.SpinnakerException as ex:
            print("Error: %s" % ex)
            result = False

        return result, image_event_handler

    def reset_image_events(
        self, cam: PySpin.CameraPtr, image_event_handler: "CamImageEventHandler"
    ) -> bool:
        """
        This functions resets the example by unregistering the image event handler.

        :param cam: Camera instance.
        :param image_event_handler: Image event handler for cam.
        :type cam: CameraPtr
        :type image_event_handler: ImageEventHandler
        :return: True if successful, False otherwise.
        :rtype: bool
        """
        try:
            result = True

            #  Unregister image event handler
            #
            #  *** NOTES ***
            #  It is important to unregister all image events from all cameras they are registered to.
            #  Unlike SystemEventHandler and InterfaceEventHandler in the EnumerationEvents example,
            #  there is no need to explicitly delete the ImageEventHandler here as it does not store
            #  an instance of the camera (it gets deleted in the constructor already).
            cam.UnregisterEventHandler(image_event_handler)

            print("Image events unregistered...")

        except PySpin.SpinnakerException as ex:
            print("Error: %s" % ex)
            result = False

        return result
