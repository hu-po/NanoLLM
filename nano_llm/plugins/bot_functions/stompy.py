#!/usr/bin/env python3
from datetime import datetime
from nano_llm import bot_function


@bot_function
def PICK():
    """
    Pick up an object
    """
    return "You pick up the object."


@bot_function
def PLACE():
    """
    Place an object.
    """
    return "You place the object."
