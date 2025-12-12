from __future__ import annotations

import asyncio
import json
import subprocess
from typing import Any, TypedDict

import psutil


class PM2ProcessInfo(TypedDict):
    name: str
    pid: int
    status: str
    cpu: float
    memory_mb: float
    restarts: int


class MemoryUsage(TypedDict):
    total_gb: float
    available_gb: float
    used_gb: float
    percent: float


class DiskUsage(TypedDict):
    total_gb: float
    used_gb: float
    free_gb: float
    percent: float


class NetworkStats(TypedDict):
    bytes_sent_mb: float
    bytes_recv_mb: float
    packets_sent: int
    packets_recv: int


class CPUInfo(TypedDict):
    physical_cores: int | None
    logical_cores: int | None
    cpu_freq_mhz: float | str
    per_cpu_percent: list[float]


class ProcessInfo(TypedDict):
    cpu_percent: float
    memory_mb: float
    num_threads: int
    num_fds: int | str


class SystemStats(TypedDict):
    cpu: dict[str, Any]
    memory: dict[str, Any]
    disk: DiskUsage
    network: NetworkStats
    process: ProcessInfo
    pm2: dict[str, Any]


class SystemMonitor:
    def __init__(self):
        self.cpu_percent_history: list[float] = []
        self.memory_percent_history: list[float] = []
        self.max_history_length = 60  # Keep last 60 data points

        self.pm2_available = self._check_pm2_availability()

    def _check_pm2_availability(self) -> bool:
        """Check if PM2 is available on the system."""
        try:
            result = subprocess.run(["pm2", "--version"], capture_output=True, text=True, timeout=5)
            return result.returncode == 0
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False

    def get_cpu_usage(self) -> float:
        """Get current CPU usage percentage."""
        cpu_percent = psutil.cpu_percent(interval=1)
        self.cpu_percent_history.append(cpu_percent)
        if len(self.cpu_percent_history) > self.max_history_length:
            self.cpu_percent_history.pop(0)
        return cpu_percent

    def get_memory_usage(self) -> MemoryUsage:
        """Get current memory usage statistics."""
        memory = psutil.virtual_memory()
        memory_percent = memory.percent
        self.memory_percent_history.append(memory_percent)
        if len(self.memory_percent_history) > self.max_history_length:
            self.memory_percent_history.pop(0)

        return MemoryUsage(
            total_gb=round(memory.total / (1024**3), 2),
            available_gb=round(memory.available / (1024**3), 2),
            used_gb=round(memory.used / (1024**3), 2),
            percent=memory_percent,
        )

    def get_disk_usage(self) -> DiskUsage:
        """Get disk usage statistics."""
        disk = psutil.disk_usage("/")
        return DiskUsage(
            total_gb=round(disk.total / (1024**3), 2),
            used_gb=round(disk.used / (1024**3), 2),
            free_gb=round(disk.free / (1024**3), 2),
            percent=disk.percent,
        )

    def get_network_stats(self) -> NetworkStats:
        """Get network I/O statistics."""
        net_io = psutil.net_io_counters()
        return NetworkStats(
            bytes_sent_mb=round(net_io.bytes_sent / (1024**2), 2),
            bytes_recv_mb=round(net_io.bytes_recv / (1024**2), 2),
            packets_sent=net_io.packets_sent,
            packets_recv=net_io.packets_recv,
        )

    def get_cpu_info(self) -> CPUInfo:
        """Get CPU information."""
        return CPUInfo(
            physical_cores=psutil.cpu_count(logical=False),
            logical_cores=psutil.cpu_count(logical=True),
            cpu_freq_mhz=round(psutil.cpu_freq().current, 2) if psutil.cpu_freq() else "N/A",
            per_cpu_percent=psutil.cpu_percent(interval=1, percpu=True),
        )

    async def get_pm2_processes(self) -> list[PM2ProcessInfo]:
        """Get PM2 process information if available."""
        if not self.pm2_available:
            return []

        result = await asyncio.create_subprocess_exec("pm2", "jlist", stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        stdout, _ = await result.communicate()

        if result.returncode == 0:
            processes = json.loads(stdout.decode())
            return [
                PM2ProcessInfo(
                    name=proc["name"],
                    pid=proc["pid"],
                    status=proc["pm2_env"]["status"],
                    cpu=proc["monit"]["cpu"],
                    memory_mb=round(proc["monit"]["memory"] / (1024**2), 2),
                    restarts=proc["pm2_env"]["restart_time"],
                )
                for proc in processes
            ]

        return []

    def get_process_info(self) -> ProcessInfo:
        """Get current process information."""
        process = psutil.Process()
        return {
            "cpu_percent": process.cpu_percent(),
            "memory_mb": round(process.memory_info().rss / (1024**2), 2),
            "num_threads": process.num_threads(),
            "num_fds": process.num_fds() if hasattr(process, "num_fds") else "N/A",
        }

    async def get_all_stats(self) -> SystemStats:
        """Get all system statistics."""
        cpu_usage = self.get_cpu_usage()
        memory_usage = self.get_memory_usage()
        disk_usage = self.get_disk_usage()
        network_stats = self.get_network_stats()
        cpu_info = self.get_cpu_info()
        process_info = self.get_process_info()
        pm2_processes = await self.get_pm2_processes()

        return {
            "cpu": {
                "current_percent": cpu_usage,
                "history": self.cpu_percent_history,
                "info": cpu_info,
            },
            "memory": {
                "current": memory_usage,
                "history": self.memory_percent_history,
            },
            "disk": disk_usage,
            "network": network_stats,
            "process": process_info,
            "pm2": {
                "available": self.pm2_available,
                "processes": pm2_processes,
            },
        }
