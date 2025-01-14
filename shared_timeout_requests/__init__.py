"""
shared_timeout_request
~~~~~~~~~~~~

This module provides a method to create a context that shares a total timeout between requests.

:copyright: (c) 2025 by Jiaming Cao.
:license: Apache2, see LICENSE for more details.
"""
import dis
import functools
import importlib.util
import struct
import time
import types
from typing import Any, Callable, List, TypeVar
from typing_extensions import ParamSpec, Concatenate, TypeAlias
import weakref
import requests


def create_embedded_instructions(func: Callable) -> List[dis.Instruction]:
    """create instructions from original function
    replace LOAD_GLOBAL to LOAD_FAST (first function argument)
    replace XX_FAST (n) to XX_FAST (n + 1), cause co_varnames listed all variables in function, and arguments are ahead
    
    Args:
        func: original function
    
    Return:
        list of created instructions
    """
    new_instructions: List[dis.Instruction] = []
    for instr in dis.Bytecode(func.__code__):
        if instr.opname == "LOAD_GLOBAL" and instr.argval == "requests":
            new_instructions.append(instr._replace(
                opname="LOAD_FAST",
                opcode=dis.opmap["LOAD_FAST"],
                arg=0, 
                argval="__CLONED_REQUESTS", 
                argrepr="__CLONED_REQUESTS"
            ))
        elif instr.opname in ("LOAD_FAST", "STORE_FAST", "DELETE_FAST",):
            new_instructions.append(instr._replace(arg=instr.arg + 1))
        else:
            new_instructions.append(instr)
    return new_instructions


R = TypeVar('R')
P = ParamSpec('P')

def create_embedded_function(func: Callable[P, R]) -> Callable[Concatenate[types.ModuleType, P], R]:
    """create a cloned function with "requests" module embedded point
    
    Every bytecode that used global "requests" module will be replaced to
    use first argument, and "__CLONED_REQUESTS" parameter will be added 
    to argument list
    
    Args:
        func: original function
    
    Returns:
        embedded function object: (__CLONED_REQUESTS, ...) -> R)
    """
    new_instructions = create_embedded_instructions(func)
    
    bytecode = bytearray()
    for instr in new_instructions:
        # every instruction has 2 bytes, operation code and argument
        # if argument is longer than 1 byte, EXTENDED_ARG op will be
        # set before the instruction.
        # example. 
        # EXTENDED_ARG 0b11001100
        # JUMP_IF_NOT_EXC_MATCH 0b00001111
        # the real argument is 0b11001100 00001111
        bytecode.append(instr.opcode)
        bytecode.extend(struct.pack('B', (instr.arg or 0) & 0b11111111))
    
    try:
        line_no_table = func.__code__.co_linetable
    except AttributeError:
        line_no_table = func.__code__.co_lnotab
    
    new_code = types.CodeType(
        func.__code__.co_argcount + 1,  # add new argument
        func.__code__.co_posonlyargcount,
        func.__code__.co_kwonlyargcount,
        func.__code__.co_nlocals + 1,  # argument is also a local variable
        func.__code__.co_stacksize,
        func.__code__.co_flags,
        bytes(bytecode),
        func.__code__.co_consts,
        func.__code__.co_names,
        ("__CLONED_REQUESTS",) + func.__code__.co_varnames,  # name of new argument
        func.__code__.co_filename,
        func.__code__.co_name,
        func.__code__.co_firstlineno,
        line_no_table,
        func.__code__.co_freevars,
        func.__code__.co_cellvars
    )
    embedded_function = types.FunctionType(new_code, globals(), closure=func.__closure__)
    embedded_function.__annotations__ = func.__annotations__
    embedded_function.__defaults__ = func.__defaults__
    embedded_function.__kwdefaults__ = func.__kwdefaults__
    return embedded_function

ReferenceType: TypeAlias = Callable[[], types.ModuleType]

def function_dispatch(request_module: ReferenceType, method: str) -> Callable[..., Any]:
    """create a new function to redirect original requests.<METHOD> target function
    
    Args:
        request_module: module that be redirected to
        method: dispatch method, like "get", "post", etc...
    
    Return:
        dispatch function
    """
    
    def dispatch_function(*args, **kwargs):
        _request_module = request_module()
        if not _request_module:
            raise RuntimeError("request_module has been garbage collected")
        return _request_module.request(method, *args, **kwargs)
    return dispatch_function

def _shared_timeout(func: Callable[P, R], timeout: float) -> Callable[P, R]:
    """prototype of shared_timeout decorator
    
    Args:
        func: the function to be decorated
        timeout: the total timeout of all requests.<METHOD>/request in the function
    
    Returns:
        decorated function
    """
    embedded_function = create_embedded_function(func)
    
    @functools.wraps(func)
    def arguments_catcher(*args, **kwargs):
        global requests
        spec = importlib.util.find_spec(requests.__name__)
        cloned_requests = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cloned_requests)
        
        remained_timeout = timeout
        def shared_timeout_request(*args, **kwargs):
            global requests
            nonlocal remained_timeout
            _timeout = kwargs.get("timeout")
            if not _timeout:
                _timeout = remained_timeout
            elif _timeout > remained_timeout:
                _timeout = remained_timeout
            kwargs["timeout"] = _timeout
            
            start = time.time()
            result = requests.request(*args, **kwargs)
            end = time.time()
            if end - start > timeout:
                raise requests.Timeout()
            remained_timeout -= (end - start)
            return result
        cloned_requests.request = shared_timeout_request
        
        for method in ("get", "post", "delete", "put", "patch"):
            setattr(cloned_requests, method, function_dispatch(weakref.ref(cloned_requests), method))
        
        result = embedded_function(*([cloned_requests] + list(args)), **kwargs)
        
        del cloned_requests
        return result
    
    return arguments_catcher


def shared_timeout(timeout: float):
    """shared_timeout decorator
    
    Args:
        timeout: the total timeout of all requests.<METHOD>/request in the function
    
    Returns:
        decorated function
    """
    return functools.partial(_shared_timeout, timeout=timeout)
