#!/usr/bin/env python3
import sys
import threading

from termcolor import cprint

from nano_llm import Plugin
from nano_llm.web import WebServer
from nano_llm.utils import load_prompts


class UserPrompt(Plugin):
    """
    Source plugin that reads text prompts, either interactively from stdin,
    or from a .txt or .json file.  It will also forward/open any text inputs.
    Outputs a string of the prompt text (or list of strings if multiple prompts).
    """
    def __init__(self, prompt=None, interactive=False, prefix=None, **kwargs):
        """
        Parameters:
        
          prompt (str) -- optional initial prompt or path to txt/json file
          interactive (bool) -- read user input from stdin (todo file descriptors)
          prefix (str) -- when in interactive mode, the prompt for user input
        """
        super().__init__(input_channels=0, **kwargs)
        
        self.prefix = prefix
        self.interactive = interactive
        
        if self.interactive:
            self.user_thread = threading.Thread(target=self.read_user, daemon=True)
            self.user_thread.start()
           
        if prompt:
            self.input(prompt)
            
        WebServer.add_listener(self.on_websocket)
            
    def process(self, input, **kwargs):
        if isinstance(input, list):
            for x in input:
                self.process(x, **kwargs)
            return
            
        if not isinstance(input, str):
            raise TypeError(f"{type(self)} input should be of type str (was {type(input)})")
    
        if input.lower().endswith(('.txt', '.json')):
            input = load_prompts(input) #' '.join(load_prompts(input))
            
        self.output(input)
    
    def read_user(self):
        while True:
            if self.prefix:
                cprint(self.prefix, 'blue', end='', flush=True)
            self.output(sys.stdin.readline().strip())
            
    def on_websocket(self, msg, msg_type=0, **kwargs): 
        print('UserPrompt.on_websocket()', msg)
        
        if msg_type != WebServer.MESSAGE_JSON or self.name not in msg:
            return
            
        msg = msg[self.name]
        
        if 'input' in msg:
            self.input(msg['input'])
