#!/usr/bin/env python3
import time
import logging
import traceback

import torch
import numpy as np

from nano_llm import Plugin
from nano_llm.utils import cuda_image

from jetson_utils import videoSource, videoOutput, cudaDeviceSynchronize, cudaToNumpy


class VideoSource(Plugin):
    """
    Captures or loads a video/camera stream or sequence of images
    https://github.com/dusty-nv/jetson-inference/blob/master/docs/aux-streaming.md
    """
    def __init__(self, video_input : str = '/dev/video0', 
                 video_input_width : int = None, video_input_height : int = None, 
                 video_input_codec : str = None, video_input_framerate : float = None, 
                 video_input_save : str = None, return_tensors : str = 'cuda', **kwargs):
        """
        Creates a video input source from MIPI CSI or V4L2 camera, RTP/RTSP/WebRTC stream, or video file.
        
        Args:
          video_input (str): Path to video file, directory of images, or stream URL.
          video_input_width (int): The disired width in pixels (by default, uses the stream's native resolution)
          video_input_height (int): The disired height in pixels (by default, uses the stream's native resolution)
          video_input_codec (str): Force a particular codec ('h264', 'h265', 'vp8', 'vp9', 'mjpeg', ect)
          return_tensors (str): The object datatype of the image to output ('np', 'pt', 'cuda')
        """
        super().__init__(input_channels=0, **kwargs)
        
        options = {}
        
        if video_input_width:
            options['width'] = video_input_width
            
        if video_input_height:
            options['height'] = video_input_height
            
        if video_input_codec:
            options['codec'] = video_input_codec
 
        if video_input_framerate:
            options['framerate'] = video_input_framerate
            
        if video_input_save:
            options['save'] = video_input_save
        
        self.stream = videoSource(video_input, options=options)
        self.file = (self.stream.GetOptions()['resource']['protocol'] == 'file')
        self.options = options
        self.resource = video_input  # self.stream.GetOptions().resource['string']
        self.return_tensors = return_tensors

    def capture(self, timeout=2500, retries=8, return_tensors=None):
        """
        Capture images from the video source as long as it's streaming
        """
        if not return_tensors:
            return_tensors = self.return_tensors
            
        retry = 0
        
        while retry < retries:
            image = self.stream.Capture(format='rgb8', timeout=timeout)

            if image is None:
                if self.file:
                    break
                logging.warning(f"video source {self.resource} timed out during capture, re-trying...")
                retry = retry + 1
                continue
   
            if return_tensors == 'pt':
                image = torch.as_tensor(image, device='cuda')
            elif return_tensors == 'np':
                image = cudaToNumpy(image)
                cudaDeviceSynchronize()
            elif return_tensors != 'cuda':
                raise ValueError(f"return_tensors should be 'np', 'pt', or 'cuda' (was '{return_tensors}')")
                
            self.output(image)
            return image
    
        return None
        
    def reconnect(self):
        """
        Attempt to re-open the stream if the connection fails
        """
        while True:
            try:
                if self.stream is not None:
                    self.stream.Close()
                    self.stream = None        
            except Exception as error:
                logging.error(f"Exception occurred closing video source \"{self.resource}\"\n\n{traceback.format_exc()}")

            try:
                self.stream = videoSource(self.resource, options=self.options)
                return
            except Exception as error:
                logging.error(f"Failed to create video source \"{self.resource}\"\n\n{traceback.format_exc()}")
                time.sleep(2.5)
            
    def run(self):
        """
        Run capture continuously and attempt to handle disconnections
        """
        while True:
            try:
                img = self.capture()
            except Exception as error:
                logging.error(f"Exception occurred during video source capture of \"{self.resource}\"\n\n{traceback.format_exc()}")
                img = None

            if img is None:
                if self.file:
                    return
                logging.error(f"Re-initializing video source \"{self.resource}\"")
                self.reconnect()

    @property
    def streaming(self):
        """
        Returns true if the stream is currently open, false if closed or EOS.
        """
        return self.stream.IsStreaming()
     
    @property
    def eos(self):
        """
        Returns true if the stream is currently closed (EOS has been reached)
        """
        return not self.streaming
        
class VideoOutput(Plugin):
    """
    Saves images to a compressed video or directory of individual images, the display, or a network stream.
    https://github.com/dusty-nv/jetson-inference/blob/master/docs/aux-streaming.md
    """
    def __init__(self, video_output : str = "webrtc://@:8554/output", 
                 video_output_codec : str = None, video_output_bitrate : int = None, 
                 video_output_save : str = None, **kwargs):
        """
        Output video to a network stream (RTP/RTSP/WebRTC), video file, or display.
        
        Args:
          video_output (str): Stream URL, path to video file, directory of images.
          video_output_codec (str): Force a particular codec ('h264', 'h265', 'vp8', 'vp9', 'mjpeg', ect)
          video_output_bitrate (int): The desired bitrate in bits per second (default is 4 Mbps)
        """
        super().__init__(output_channels=0, **kwargs)
        
        options = {}

        if video_output_codec:
            options['codec'] = video_output_codec
            
        if video_output_bitrate:
            options['bitrate'] = video_output_bitrate

        if video_output_save:
            options['save'] = video_output_save
            
        if video_output is None:
            video_output = ''
            
        args = None if 'display://' in video_output else ['--headless']
        
        self.stream = videoOutput(video_output, options=options, argv=args)
        self.resource = video_output
        
    def process(self, input, **kwargs):
        """
        Input should be a jetson_utils.cudaImage, np.ndarray, torch.Tensor, or have __cuda_array_interface__
        """
        self.stream.Render(cuda_image(input))
            
