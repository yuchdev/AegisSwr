from enum import Enum


class FaultClass(str, Enum):
    """
    Represents various types of software faults that can occur during program execution.

    This enum class categorizes different classes of faults often associated with software
    bugs or erroneous conditions. It can be used to classify and handle exceptions or
    unexpected behaviors programmatically.

    :cvar MEMORY_ACCESS_VIOLATION: Fault caused by invalid memory access.
    :cvar NULL_POINTER_DEREFERENCE: Fault caused by dereferencing a null pointer.
    :cvar USE_AFTER_FREE: Fault caused by accessing memory after it has been freed.
    :cvar STACK_OVERFLOW: Fault caused by exceeding the stack size.
    :cvar INTEGER_DIVIDE_BY_ZERO: Fault caused by dividing an integer by zero.
    :cvar DEADLOCK: Fault caused by deadlock in concurrent programming.
    :cvar ASSERTION_FAILURE: Fault caused by a failed assert statement.
    :cvar UNHANDLED_EXCEPTION: Fault caused by an exception that is not caught.
    :cvar RESOURCE_EXHAUSTION: Fault caused by depletion of system resources.
    :cvar UNKNOWN: General fallback for an unidentified fault.
    """
    MEMORY_ACCESS_VIOLATION = "memory_access_violation"
    NULL_POINTER_DEREFERENCE = "null_pointer_dereference"
    USE_AFTER_FREE = "use_after_free"
    STACK_OVERFLOW = "stack_overflow"
    INTEGER_DIVIDE_BY_ZERO = "integer_divide_by_zero"
    DEADLOCK = "deadlock"
    ASSERTION_FAILURE = "assertion_failure"
    UNHANDLED_EXCEPTION = "unhandled_exception"
    RESOURCE_EXHAUSTION = "resource_exhaustion"
    UNKNOWN = "unknown"


"""Windows NTSTATUS / HRESULT codes → FaultClass"""
_NTSTATUS_MAP: dict[str, FaultClass] = {
    "0xc0000005": FaultClass.MEMORY_ACCESS_VIOLATION,
    "0xc0000374": FaultClass.MEMORY_ACCESS_VIOLATION,  # heap corruption
    "0xc0000409": FaultClass.MEMORY_ACCESS_VIOLATION,  # stack buffer overrun
    "0xc00000fd": FaultClass.STACK_OVERFLOW,
    "0xc0000094": FaultClass.INTEGER_DIVIDE_BY_ZERO,
    "0xc0000095": FaultClass.INTEGER_DIVIDE_BY_ZERO,   # integer overflow
    "0xc0000017": FaultClass.RESOURCE_EXHAUSTION,      # no memory
    "0xc000007b": FaultClass.UNHANDLED_EXCEPTION,      # invalid image format
    "0xc0000096": FaultClass.UNHANDLED_EXCEPTION,      # privileged instruction
    "0xc000001d": FaultClass.UNHANDLED_EXCEPTION,      # illegal instruction
    "0x80000003": FaultClass.ASSERTION_FAILURE,        # breakpoint
    "0x80000004": FaultClass.ASSERTION_FAILURE,        # single step
    "0xc0000008": FaultClass.UNHANDLED_EXCEPTION,      # invalid handle
}

"""Linux POSIX signals → FaultClass"""
_SIGNAL_MAP: dict[int, FaultClass] = {
    4: FaultClass.UNHANDLED_EXCEPTION,   # SIGILL
    6: FaultClass.ASSERTION_FAILURE,     # SIGABRT
    7: FaultClass.MEMORY_ACCESS_VIOLATION,  # SIGBUS
    8: FaultClass.INTEGER_DIVIDE_BY_ZERO,   # SIGFPE
    11: FaultClass.MEMORY_ACCESS_VIOLATION, # SIGSEGV
    16: FaultClass.RESOURCE_EXHAUSTION,     # SIGSTKFLT (stack fault)
    31: FaultClass.MEMORY_ACCESS_VIOLATION, # SIGSYS
}

"""macOS Mach exception types → FaultClass"""
_MACOS_EXCEPTION_MAP: dict[int, FaultClass] = {
    1: FaultClass.MEMORY_ACCESS_VIOLATION,  # EXC_BAD_ACCESS
    2: FaultClass.UNHANDLED_EXCEPTION,      # EXC_BAD_INSTRUCTION
    3: FaultClass.INTEGER_DIVIDE_BY_ZERO,   # EXC_ARITHMETIC
    4: FaultClass.UNHANDLED_EXCEPTION,      # EXC_EMULATION
    5: FaultClass.UNHANDLED_EXCEPTION,      # EXC_SOFTWARE
    6: FaultClass.ASSERTION_FAILURE,        # EXC_BREAKPOINT
    10: FaultClass.RESOURCE_EXHAUSTION,     # EXC_RESOURCE
    11: FaultClass.UNHANDLED_EXCEPTION,     # EXC_GUARD
}


def map_windows_ntstatus(code: str) -> FaultClass:
    """Map a Windows NTSTATUS/HRESULT hex string to FaultClass"""
    return _NTSTATUS_MAP.get(code.lower(), FaultClass.UNKNOWN)


def map_linux_signal(signal: int) -> FaultClass:
    """Map a Linux signal number to FaultClass"""
    return _SIGNAL_MAP.get(signal, FaultClass.UNKNOWN)


def map_macos_exception(code: int) -> FaultClass:
    """Map a macOS Mach exception type to FaultClass"""
    return _MACOS_EXCEPTION_MAP.get(code, FaultClass.UNKNOWN)
