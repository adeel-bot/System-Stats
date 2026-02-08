import tkinter as tk
from tkinter import ttk
import psutil
import platform
from datetime import datetime
import threading
import time
import subprocess
from typing import Tuple, Optional

# Try to import GPUtil for discrete GPUs
GPUtil = None
try:
    import GPUtil
    HAS_GPUTIL = True
except ImportError:
    HAS_GPUTIL = False

class SystemStatsWidget:
    def __init__(self, root):
        self.root = root
        self.root.title("Stats Widget")
        self.root.geometry("360x650")
        self.root.attributes("-topmost", True)
        self.root.resizable(True, True)
        self.root.configure(bg="#0B0F14")

        # ===== Color Palette =====
        self.bg = "#0B0F14"
        self.card = "#121826"
        self.border = "#1F2937"
        self.text_main = "#E5E7EB"
        self.text_muted = "#9CA3AF"

        self.cpu_color = "#6366F1"
        self.ram_color = "#EC4899"
        self.gpu_color = "#22C55E"
        self.bat_color = "#F59E0B"
        self.time_color = "#38BDF8"

        # Detect GPU type
        self.gpu_type = self.detect_gpu_type()

        # ===== Main Container Frame =====
        main_frame = tk.Frame(root, bg=self.bg)
        main_frame.pack(fill=tk.BOTH, expand=True)

        # ===== Scrollable Canvas =====
        self.canvas = tk.Canvas(main_frame, bg=self.bg, highlightthickness=0)
        self.scrollbar = ttk.Scrollbar(main_frame, orient="vertical", command=self.canvas.yview)

        self.canvas.configure(yscrollcommand=self.scrollbar.set)

        self.scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.container = tk.Frame(self.canvas, bg=self.bg)
        self.canvas_window = self.canvas.create_window((0, 0), window=self.container, anchor="nw", width=340)

        # Update scroll region and canvas width
        self.container.bind(
            "<Configure>",
            lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        )
        
        self.canvas.bind("<Configure>", self._on_canvas_configure)

        # Enable mouse wheel scrolling (Windows)
        self.canvas.bind_all("<MouseWheel>", self.on_mousewheel)

        # ===== Title =====
        title_frame = tk.Frame(self.container, bg=self.bg)
        title_frame.pack(fill=tk.X, pady=(15, 10))
        
        tk.Label(
            title_frame,
            text="System Stats",
            font=("Segoe UI Black", 20, "bold"),
            bg=self.bg,
            fg=self.text_main,
        ).pack()

        # ===== Sections =====
        self.time_label, self.date_label = self.create_time_card("TIME", self.time_color)
        self.cpu_label, self.cpu_bar = self.create_stat_card("CPU", self.cpu_color)
        self.ram_label, self.ram_bar = self.create_stat_card("MEMORY", self.ram_color, detail=True)
        
        # GPU Section - Always show if we detected any GPU
        if self.gpu_type != "none":
            self.gpu_label, self.gpu_bar = self.create_stat_card("GPU", self.gpu_color, detail=True)

        # Battery Section
        battery = psutil.sensors_battery()
        self.has_battery = battery is not None
        if self.has_battery:
            self.battery_label, self.battery_bar = self.create_stat_card("BATTERY", self.bat_color, detail=True)

        # Footer
        footer_frame = tk.Frame(self.container, bg=self.card, highlightbackground=self.border, highlightthickness=1)
        footer_frame.pack(fill=tk.X, padx=14, pady=(10, 15))
        
        tk.Label(
            footer_frame,
            text=f"Windows {platform.release()} • {platform.machine()}",
            font=("Consolas", 9),
            bg=self.card,
            fg=self.text_muted,
            pady=10
        ).pack()

        # Start thread
        self.running = True
        threading.Thread(target=self.update_stats, daemon=True).start()
        self.root.protocol("WM_DELETE_WINDOW", self.close)

    def detect_gpu_type(self) -> str:
        """Detect what type of GPU monitoring we can use"""
        # First, try discrete GPU with GPUtil
        if HAS_GPUTIL and GPUtil is not None:
            try:
                gpus = GPUtil.getGPUs()
                if gpus and len(gpus) > 0:
                    return "discrete"
            except Exception:
                pass
        
        # Check if we're on Windows for integrated GPU monitoring
        if platform.system() == "Windows":
            # Windows has GPU, we'll use performance counters or estimation
            return "integrated"
        
        return "none"

    def get_gpu_usage(self) -> Tuple[float, str]:
        """Get GPU usage based on detected GPU type"""
        if self.gpu_type == "discrete" and HAS_GPUTIL and GPUtil is not None:
            try:
                gpus = GPUtil.getGPUs()
                if gpus and len(gpus) > 0:
                    gpu = gpus[0]
                    return gpu.load * 100, gpu.name
            except Exception:
                pass
        
        elif self.gpu_type == "integrated":
            # For integrated GPU, try Windows performance counter
            try:
                # Try to get GPU usage via Windows PowerShell command
                result = subprocess.run(
                    ['powershell', '-Command', 
                     '(Get-Counter "\\GPU Engine(*engtype_3D)\\Utilization Percentage").CounterSamples | Measure-Object -Property CookedValue -Sum | Select-Object -ExpandProperty Sum'],
                    capture_output=True,
                    text=True,
                    timeout=2,
                    creationflags=subprocess.CREATE_NO_WINDOW
                )
                
                if result.returncode == 0 and result.stdout.strip():
                    usage = float(result.stdout.strip())
                    # Get GPU name from WMI
                    gpu_name = self.get_integrated_gpu_name()
                    return min(usage, 100), gpu_name
            except Exception:
                pass
            
            # Fallback: Estimate based on CPU usage (rough approximation)
            try:
                cpu_usage = psutil.cpu_percent()
                # Integrated GPUs often correlate with CPU usage
                estimated_usage = cpu_usage * 0.7  # Conservative estimate
                gpu_name = self.get_integrated_gpu_name()
                return estimated_usage, f"{gpu_name} (estimated)"
            except Exception:
                pass
        
        return 0.0, "No GPU detected"

    def get_integrated_gpu_name(self) -> str:
        """Get the name of integrated GPU on Windows"""
        try:
            result = subprocess.run(
                ['powershell', '-Command',
                 'Get-WmiObject Win32_VideoController | Select-Object -ExpandProperty Name -First 1'],
                capture_output=True,
                text=True,
                timeout=2,
                creationflags=subprocess.CREATE_NO_WINDOW
            )
            if result.returncode == 0 and result.stdout.strip():
                return result.stdout.strip()
        except Exception:
            pass
        
        return "Integrated GPU"

    def _on_canvas_configure(self, event):
        """Update the canvas window width when canvas is resized"""
        self.canvas.itemconfig(self.canvas_window, width=event.width - 20)

    # ===== Mouse Wheel =====
    def on_mousewheel(self, event):
        self.canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

    # ===== UI Helpers =====
    def create_time_card(self, title: str, accent: str) -> Tuple[tk.Label, tk.Label]:
        frame = tk.Frame(self.container, bg=self.card, highlightbackground=self.border, highlightthickness=1)
        frame.pack(fill=tk.X, padx=14, pady=6)

        tk.Label(
            frame, text=title, font=("Consolas", 10, "bold"),
            bg=self.card, fg=self.text_muted
        ).pack(anchor="w", padx=12, pady=(10, 0))

        time_value = tk.Label(
            frame, text="00:00:00",
            font=("Consolas", 32, "bold"),
            bg=self.card, fg=accent
        )
        time_value.pack(padx=12, pady=(5, 0))
        
        date_value = tk.Label(
            frame, text="",
            font=("Consolas", 10),
            bg=self.card, fg=self.text_muted
        )
        date_value.pack(padx=12, pady=(0, 12))

        return time_value, date_value

    def create_stat_card(self, title: str, color: str, detail: bool = False) -> Tuple[tk.Label, Tuple]:
        frame = tk.Frame(self.container, bg=self.card, highlightbackground=self.border, highlightthickness=1)
        frame.pack(fill=tk.X, padx=14, pady=6)

        tk.Label(
            frame, text=title, font=("Consolas", 10, "bold"),
            bg=self.card, fg=self.text_muted
        ).pack(anchor="w", padx=12, pady=(10, 0))

        value = tk.Label(
            frame, text="0%",
            font=("Consolas", 28, "bold"),
            bg=self.card, fg=color
        )
        value.pack(anchor="w", padx=12, pady=(2, 0))

        detail_label: Optional[tk.Label] = None
        if detail:
            detail_label = tk.Label(
                frame, text="",
                font=("Consolas", 9),
                bg=self.card, fg=self.text_muted
            )
            detail_label.pack(anchor="w", padx=12, pady=(0, 8))

        bar_bg = tk.Frame(frame, bg="#020617", height=8)
        bar_bg.pack(fill=tk.X, padx=12, pady=(0, 12))

        bar = tk.Frame(bar_bg, bg=color, width=0)
        bar.place(relheight=1)

        return (value, (bar, bar_bg, detail_label))

    # ===== Logic =====
    def update_stats(self):
        while self.running:
            try:
                cpu = psutil.cpu_percent(interval=1)
                ram = psutil.virtual_memory()
                
                gpu_load = 0.0
                gpu_name = ""
                if self.gpu_type != "none":
                    gpu_load, gpu_name = self.get_gpu_usage()

                self.root.after(0, self.update_ui, cpu, ram, gpu_load, gpu_name)
            except Exception as e:
                print(f"Error in update_stats: {e}")
            
            time.sleep(0.5)

    def update_ui(self, cpu: float, ram, gpu_load: float, gpu_name: str):
        try:
            # Update time and date
            now = datetime.now()
            self.time_label.config(text=now.strftime("%H:%M:%S"))
            self.date_label.config(text=now.strftime("%A, %B %d, %Y").upper())

            # Update CPU
            self.update_bar(self.cpu_label, self.cpu_bar, cpu)
            
            # Update RAM
            self.update_bar(
                self.ram_label,
                self.ram_bar,
                ram.percent,
                f"{ram.used // (1024**3)} GB / {ram.total // (1024**3)} GB used"
            )
            
            # Update GPU
            if self.gpu_type != "none":
                self.update_bar(self.gpu_label, self.gpu_bar, gpu_load, gpu_name)

            # Update Battery
            if self.has_battery:
                bat = psutil.sensors_battery()
                if bat:
                    status = "Charging" if bat.power_plugged else "On Battery"
                    self.update_bar(self.battery_label, self.battery_bar, bat.percent, status)
        except Exception as e:
            print(f"Error in update_ui: {e}")

    def update_bar(self, label: tk.Label, bar_data: Tuple, percent: float, detail: Optional[str] = None):
        try:
            bar, bg, detail_label = bar_data
            label.config(text=f"{int(percent)}%")

            width = bg.winfo_width()
            if width > 1:
                bar.config(width=int(width * percent / 100))

            if detail_label and detail:
                detail_label.config(text=detail)
        except Exception as e:
            print(f"Error in update_bar: {e}")

    def close(self):
        self.running = False
        self.root.destroy()

def main():
    root = tk.Tk()
    SystemStatsWidget(root)
    root.mainloop()

if __name__ == "__main__":
    main()
