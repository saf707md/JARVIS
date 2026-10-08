import datetime
import platform

import psutil


def get_system_info() -> str:
    """Get information about the user's computer: name, Windows version,
    memory (RAM), disk space and battery level.

    Use this when the user asks about their PC, system, RAM, storage or battery.
    """
    memory = psutil.virtual_memory()
    disk = psutil.disk_usage("C:\\")
    gb = 1024 ** 3

    lines = [
        f"Computer name: {platform.node()}",
        f"Operating system: {platform.system()} {platform.release()}",
        f"Processor cores: {psutil.cpu_count(logical=True)}",
        f"RAM: {memory.used / gb:.1f} GB used of {memory.total / gb:.1f} GB ({memory.percent}%)",
        f"Disk C: {disk.free / gb:.0f} GB free of {disk.total / gb:.0f} GB",
    ]

    battery = psutil.sensors_battery()
    if battery is not None:
        state = "charging" if battery.power_plugged else "on battery"
        lines.append(f"Battery: {battery.percent:.0f}% ({state})")

    return "\n".join(lines)


def get_current_datetime() -> str:
    """Get the current date and time on the user's computer.

    Use this whenever the user asks for the time, date or day of the week.
    """
    now = datetime.datetime.now()
    return now.strftime("%A, %d %B %Y, %I:%M %p")
