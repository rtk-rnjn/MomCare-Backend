from __future__ import annotations

import asyncio
import json
import subprocess
from typing import Any

import psutil


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

    def get_memory_usage(self) -> dict[str, Any]:
        """Get current memory usage statistics."""
        memory = psutil.virtual_memory()
        memory_percent = memory.percent
        self.memory_percent_history.append(memory_percent)
        if len(self.memory_percent_history) > self.max_history_length:
            self.memory_percent_history.pop(0)

        return {
            "total_gb": round(memory.total / (1024**3), 2),
            "available_gb": round(memory.available / (1024**3), 2),
            "used_gb": round(memory.used / (1024**3), 2),
            "percent": memory_percent,
        }

    def get_disk_usage(self) -> dict[str, Any]:
        """Get disk usage statistics."""
        disk = psutil.disk_usage("/")
        return {
            "total_gb": round(disk.total / (1024**3), 2),
            "used_gb": round(disk.used / (1024**3), 2),
            "free_gb": round(disk.free / (1024**3), 2),
            "percent": disk.percent,
        }

    def get_network_stats(self) -> dict[str, Any]:
        """Get network I/O statistics."""
        net_io = psutil.net_io_counters()
        return {
            "bytes_sent_mb": round(net_io.bytes_sent / (1024**2), 2),
            "bytes_recv_mb": round(net_io.bytes_recv / (1024**2), 2),
            "packets_sent": net_io.packets_sent,
            "packets_recv": net_io.packets_recv,
        }

    def get_cpu_info(self) -> dict[str, Any]:
        """Get CPU information."""
        return {
            "physical_cores": psutil.cpu_count(logical=False),
            "logical_cores": psutil.cpu_count(logical=True),
            "cpu_freq_mhz": round(psutil.cpu_freq().current, 2) if psutil.cpu_freq() else "N/A",
            "per_cpu_percent": psutil.cpu_percent(interval=1, percpu=True),
        }

    async def get_pm2_processes(self) -> list[dict[str, Any]]:
        """Get PM2 process information if available."""
        if not self.pm2_available:
            return []

        try:
            result = await asyncio.create_subprocess_exec(
                "pm2", "jlist", stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
            )
            stdout, _ = await result.communicate()

            if result.returncode == 0:
                processes = json.loads(stdout.decode())
                return [
                    {
                        "name": proc.get("name", "Unknown"),
                        "pid": proc.get("pid", 0),
                        "status": proc.get("pm2_env", {}).get("status", "unknown"),
                        "cpu": proc.get("monit", {}).get("cpu", 0),
                        "memory_mb": round(proc.get("monit", {}).get("memory", 0) / (1024**2), 2),
                        "restarts": proc.get("pm2_env", {}).get("restart_time", 0),
                        "uptime_ms": proc.get("pm2_env", {}).get("pm_uptime", 0),
                    }
                    for proc in processes
                ]
        except Exception:
            pass

        return []

    def get_process_info(self) -> dict[str, Any]:
        """Get current process information."""
        process = psutil.Process()
        return {
            "cpu_percent": process.cpu_percent(),
            "memory_mb": round(process.memory_info().rss / (1024**2), 2),
            "num_threads": process.num_threads(),
            "num_fds": process.num_fds() if hasattr(process, "num_fds") else "N/A",
        }

    async def get_all_stats(self) -> dict[str, Any]:
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
