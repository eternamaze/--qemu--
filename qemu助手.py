#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
QEMU Assistant (Portable Edition)
=================================
A single-file, portable Python script to manage and run QEMU virtual machines.
Focuses on ease of use, portability, and clean management of VM resources.

Author: GitHub Copilot (Refactored)
Date: 2025-12-27
"""

# ==============================================================================
# MODULE: IMPORTS & GLOBAL CONFIGURATION
# ==============================================================================
import os
import sys
import glob
import json
import time
import shutil
import readline
import subprocess
from typing import List, Dict, Optional, Tuple, Any

# --- Constants ---
SCRIPT_PATH = os.path.abspath(__file__)
SCRIPT_DIR = os.path.dirname(SCRIPT_PATH)
SCRIPT_NAME = os.path.splitext(os.path.basename(SCRIPT_PATH))[0]
SAVE_ROOT = os.path.join(SCRIPT_DIR, f"{SCRIPT_NAME}_save")

OVMF_CODE_PATHS = [
    "/usr/share/OVMF/OVMF_CODE_4M.fd",
    "/usr/share/OVMF/OVMF_CODE.fd",
    "/usr/share/edk2/ovmf/OVMF_CODE.fd",
    "/usr/share/ovmf/x64/OVMF_CODE.fd",
    "/usr/share/qemu/ovmf-x86_64-code.bin",
    "/usr/share/qemu/OVMF.fd",
    "/usr/share/ovmf/OVMF.fd"
]

OVMF_VARS_CANDIDATES = [
    "OVMF_VARS.fd",
    "OVMF_VARS_4M.fd",
    "OVMF_VARS.4m.fd",
    "ovmf-x86_64-vars.bin"
]

# ==============================================================================
# MODULE: UTILITIES (UI & FILESYSTEM)
# ==============================================================================

class Colors:
    """ANSI Color codes for terminal output."""
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'

class UI:
    """Static utility class for User Interface operations."""

    @staticmethod
    def clear_screen() -> None:
        """Clears the terminal screen."""
        os.system('cls' if os.name == 'nt' else 'clear')

    @staticmethod
    def print_header() -> None:
        """Prints the application banner."""
        print(f"{Colors.HEADER}===================================================={Colors.ENDC}")
        print(f"{Colors.HEADER}      QEMU 智能助手 (Python Edition){Colors.ENDC}")
        print(f"{Colors.HEADER}===================================================={Colors.ENDC}")

    @staticmethod
    def get_input(prompt: str, default: str = "") -> str:
        """
        Gets user input with a default value pre-filled in the prompt.
        Uses readline to allow editing the default value.
        """
        def hook():
            readline.insert_text(default)
            readline.redisplay()
        
        if default:
            readline.set_pre_input_hook(hook)
        
        try:
            user_input = input(f"{prompt}: ").strip()
        finally:
            readline.set_pre_input_hook(None)
            
        return user_input if user_input else default

    @staticmethod
    def path_completer(text: str, state: int) -> Optional[str]:
        """Readline completer for file paths."""
        text = os.path.expanduser(text)
        matches = glob.glob(text + '*')
        matches.sort()
        
        results: List[str] = []
        for m in matches:
            if os.path.isdir(m):
                results.append(m + "/")
            else:
                results.append(m)
                
        if state < len(results):
            return results[state]
        else:
            return None

class FS:
    """Static utility class for File System operations."""

    @staticmethod
    def expand_path(path: str) -> str:
        """Expands user (~) and absolute paths."""
        if not path: return ""
        return os.path.abspath(os.path.expanduser(path))

    @staticmethod
    def init_environment() -> None:
        """Initializes the global environment (directories, readline)."""
        os.makedirs(SAVE_ROOT, exist_ok=True)
        readline.parse_and_bind("tab: complete")
        readline.set_completer(UI.path_completer)
        readline.set_completer_delims(' \t\n;')

    @staticmethod
    def detect_ovmf() -> Tuple[Optional[str], Optional[str]]:
        """Detects OVMF firmware and VARS template paths."""
        code_path = None
        for path in OVMF_CODE_PATHS:
            if os.path.exists(path):
                code_path = path
                break
        
        if not code_path:
            return None, None

        ovmf_dir = os.path.dirname(code_path)
        vars_path = None
        for candidate in OVMF_VARS_CANDIDATES:
            p = os.path.join(ovmf_dir, candidate)
            if os.path.exists(p):
                vars_path = p
                break
                
        return code_path, vars_path

# ==============================================================================
# MODULE: CORE LOGIC (QEMU RUNNER)
# ==============================================================================

class QEMURunner:
    """Handles the construction and execution of the QEMU command."""

    def __init__(self, session: 'Session', ovmf_code: str):
        self.session = session
        self.ovmf_code = ovmf_code

    def build_command(self) -> List[str]:
        """Constructs the QEMU command line arguments."""
        config = self.session.config
        
        cmd = [
            "qemu-system-x86_64",
            "-name", config.get("VM_NAME", "unknown"),
            "-machine", "q35", "-accel", "kvm",
            # Performance Optimizations
            "-object", "iothread,id=io0",
            "-cpu", "host,hv_relaxed,hv_spinlocks=0x1fff,hv_vapic,hv_time,hv_synic,hv_stimer,hv_reset,hv_vpindex,hv_runtime,hv_frequencies",
            "-m", config.get("MEM_SIZE", "4G"),
            "-smp", config.get("CPU_CORES", "2"),
            # Firmware
            "-drive", f"if=pflash,format=raw,readonly=on,file={self.ovmf_code}",
            "-drive", f"if=pflash,format=raw,file={self.session.vars_file}",
            # VirtIO Devices
            "-device", "virtio-balloon-pci",
            "-device", "virtio-rng-pci",
            "-device", "virtio-serial-pci",
            "-device", "virtio-keyboard-pci",
            "-device", "virtio-tablet-pci",
            # USB
            "-device", "qemu-xhci,id=usb",
            "-device", "usb-tablet",
            "-device", "usb-kbd",
            # Graphics & Audio
            "-device", "virtio-vga-gl", "-display", "gtk,gl=on,zoom-to-fit=on",
            "-device", "intel-hda", "-device", "hda-duplex",
            # Network
            "-device", "virtio-net-pci,netdev=net0,mq=on", "-netdev", "user,id=net0"
        ]

        # Disks
        for i, disk in enumerate(self.session.disks):
            disk_path = os.path.join(self.session.disk_dir, disk)
            if os.path.exists(disk_path):
                drive_id = f"drive_disk_{i}"
                serial = f"DISK_{i}"
                cmd.extend([
                    "-drive", f"file={disk_path},format=qcow2,if=none,id={drive_id},cache=writeback",
                    "-device", f"virtio-blk-pci,drive={drive_id},serial={serial},bootindex={i+1},iothread=io0"
                ])
            else:
                print(f"{Colors.WARNING}⚠️  警告: 磁盘文件丢失: {disk}{Colors.ENDC}")

        # ISOs
        for i, iso in enumerate(self.session.isos):
            iso_path = os.path.join(self.session.iso_dir, iso)
            if os.path.exists(iso_path):
                cmd.extend(["-drive", f"file={iso_path},media=cdrom,readonly=on"])
            else:
                print(f"{Colors.WARNING}⚠️  警告: ISO 文件丢失: {iso}{Colors.ENDC}")

        # Extra Mounts (USB Storage)
        # 1. Default Shared Folder
        cmd.extend([
            "-drive", f"file=fat:ro:{self.session.shared_dir},format=raw,if=none,id=drive_shared,readonly=on",
            "-device", "usb-storage,drive=drive_shared,serial=SHARED_AUTO,removable=on"
        ])

        # 2. Transient Mounts
        for i, path in enumerate(self.session.transient_mounts):
            drive_id = f"drive_trans_{i}"
            serial = f"TRANS_{i}"
            
            if os.path.isdir(path):
                cmd.extend([
                    "-drive", f"file=fat:ro:{path},format=raw,if=none,id={drive_id},readonly=on",
                    "-device", f"usb-storage,drive={drive_id},serial={serial},removable=on"
                ])
            elif os.path.isfile(path):
                cmd.extend([
                    "-drive", f"file={path},format=raw,if=none,id={drive_id},readonly=on",
                    "-device", f"usb-storage,drive={drive_id},serial={serial},removable=on"
                ])
            else:
                print(f"{Colors.WARNING}>> 忽略无效路径: {path}{Colors.ENDC}")

        return cmd

    def run(self) -> None:
        """Executes the VM."""
        cmd = self.build_command()
        print(f"\n{Colors.GREEN}>> 虚拟机正在启动...{Colors.ENDC}")
        print(f"{Colors.WARNING}⚠️  注意: 额外挂载的资源将显示为 USB 移动存储设备。{Colors.ENDC}")
        time.sleep(2)
        
        try:
            subprocess.run(cmd)
        except KeyboardInterrupt:
            print("\n>> 用户中止。")

# ==============================================================================
# MODULE: SESSION MANAGEMENT
# ==============================================================================

class Session:
    """
    Manages the lifecycle, configuration, and resources of a VM session.
    Acts as the central controller for the application logic.
    """

    def __init__(self, name: str):
        self.name = name
        self.dir = os.path.join(SAVE_ROOT, name)
        
        # Paths
        self.config_file = os.path.join(self.dir, "config.conf")
        self.vars_file = os.path.join(self.dir, "OVMF_VARS.fd")
        self.shared_dir = os.path.join(self.dir, "shared")
        self.iso_dir = os.path.join(self.dir, "isos")
        self.disk_dir = os.path.join(self.dir, "disks")
        
        # State
        self.config: Dict[str, str] = {}
        self.disks: List[str] = []
        self.isos: List[str] = []
        self.transient_mounts: List[str] = []

    # --- Lifecycle & Config ---

    def exists(self) -> bool:
        return os.path.exists(self.config_file)

    def create_structure(self) -> None:
        """Creates the directory structure for the session."""
        os.makedirs(self.dir, exist_ok=True)
        os.makedirs(self.shared_dir, exist_ok=True)
        os.makedirs(self.iso_dir, exist_ok=True)
        os.makedirs(self.disk_dir, exist_ok=True)

    def load(self) -> bool:
        """Loads configuration from disk."""
        if not self.exists(): return False
        self.config = {}
        self.disks = []
        self.isos = []
        
        disk_map: Dict[int, str] = {}
        iso_map: Dict[int, str] = {}
        
        try:
            with open(self.config_file, 'r') as f:
                for line in f:
                    if '=' in line:
                        key, val = line.strip().split('=', 1)
                        val = val.strip('"').strip("'")
                        
                        if key.startswith("DISK_"):
                            try: idx = int(key.split("_")[1])
                            except: continue
                            disk_map[idx] = val
                        elif key.startswith("ISO_"):
                            try: idx = int(key.split("_")[1])
                            except: continue
                            iso_map[idx] = val
                        else:
                            self.config[key] = val
                            
            self.disks = [disk_map[i] for i in sorted(disk_map.keys())]
            self.isos = [iso_map[i] for i in sorted(iso_map.keys())]
            return True
        except Exception as e:
            print(f"{Colors.FAIL}加载配置出错: {e}{Colors.ENDC}")
            return False

    def save(self) -> None:
        """Saves configuration to disk."""
        self.create_structure()
        with open(self.config_file, 'w') as f:
            for key, val in self.config.items():
                f.write(f'{key}="{val}"\n')
            for i, disk in enumerate(self.disks):
                f.write(f'DISK_{i}="{disk}"\n')
            for i, iso in enumerate(self.isos):
                f.write(f'ISO_{i}="{iso}"\n')

    def delete(self) -> None:
        """Deletes the entire session directory."""
        if os.path.exists(self.dir):
            shutil.rmtree(self.dir)

    def configure_basic(self, is_new: bool = False) -> None:
        """Interactive basic hardware configuration."""
        print(f"\n{Colors.CYAN}--- 基础配置 ({self.name}) ---{Colors.ENDC}")
        
        defaults = {
            "MEM_SIZE": "8G",
            "CPU_CORES": "4"
        }
        if not is_new:
            defaults.update(self.config)

        self.config["VM_NAME"] = self.name
        self.config["MEM_SIZE"] = UI.get_input("1. 内存大小", defaults["MEM_SIZE"])
        self.config["CPU_CORES"] = UI.get_input("2. CPU 核心数", defaults["CPU_CORES"])
        
        self.save()
        print(f"{Colors.GREEN}>> 基础配置已保存。{Colors.ENDC}")
        time.sleep(1)

    def ensure_vars(self, template_path: str) -> None:
        """Ensures the UEFI VARS file exists."""
        if not os.path.exists(self.vars_file):
            print(f"{Colors.GREEN}>> 初始化 UEFI 变量存储...{Colors.ENDC}")
            shutil.copy(template_path, self.vars_file)
            os.chmod(self.vars_file, 0o644)

    # --- Resource Management ---

    def import_resource(self, src_path: str, target_dir: str, res_type_name: str) -> Optional[str]:
        """Generic resource import logic."""
        if not src_path: return None
        
        src_path = FS.expand_path(src_path)
        if not os.path.exists(src_path):
            print(f"{Colors.FAIL}>> 错误: 文件不存在: {src_path}{Colors.ENDC}")
            return None
            
        filename = os.path.basename(src_path)
        dest_path = os.path.join(target_dir, filename)
        
        if os.path.exists(dest_path):
            confirm = UI.get_input(f"{Colors.WARNING}>> 文件 '{filename}' 已存在于存档中，是否覆盖? (y/N){Colors.ENDC}", "N")
            if confirm.lower() != 'y':
                return filename

        print(f"{Colors.GREEN}>> 正在导入 {res_type_name} (复制中...)...{Colors.ENDC}")
        try:
            shutil.copy2(src_path, dest_path)
            print(f"{Colors.GREEN}>> 导入成功。{Colors.ENDC}")
            return filename
        except Exception as e:
            print(f"{Colors.FAIL}>> 导入失败: {e}{Colors.ENDC}")
            return None

    def file_manager(self, target_dir: str, file_type_desc: str) -> None:
        """Interactive file manager for physical file deletion."""
        while True:
            UI.clear_screen()
            print(f"{Colors.CYAN}--- {file_type_desc}文件清理 ---{Colors.ENDC}")
            print(f"目录: {target_dir}")
            print("此处列出存档目录下的所有物理文件。")
            print("-" * 40)
            
            if not os.path.exists(target_dir):
                print("  (目录不存在)")
                files = []
            else:
                files = sorted(os.listdir(target_dir))
            
            if not files:
                print("  (目录为空)")
            else:
                for i, f in enumerate(files):
                    path = os.path.join(target_dir, f)
                    if os.path.isfile(path):
                        size = os.path.getsize(path)
                        size_str = f"{size / 1024 / 1024:.1f} MB"
                    else:
                        size_str = "DIR"
                    
                    # Check usage status
                    status = ""
                    if target_dir == self.disk_dir and f in self.disks:
                        status = f"{Colors.GREEN}*[使用中]*{Colors.ENDC}"
                    elif target_dir == self.iso_dir and f in self.isos:
                        status = f"{Colors.GREEN}*[使用中]*{Colors.ENDC}"
                    
                    print(f"  [{i+1}] {f} ({size_str}) {status}")
            
            print("-" * 40)
            print("  [D] 删除文件 (Delete)")
            print("  [B] 返回 (Back)")
            
            choice = input("请选择: ").strip().lower()
            if choice == 'b': break
            elif choice == 'd':
                idx_str = UI.get_input("请输入要删除的文件序号", "")
                if idx_str.isdigit():
                    idx = int(idx_str) - 1
                    if 0 <= idx < len(files):
                        fname = files[idx]
                        fpath = os.path.join(target_dir, fname)
                        
                        # Safety check
                        is_used = False
                        if target_dir == self.disk_dir and fname in self.disks: is_used = True
                        if target_dir == self.iso_dir and fname in self.isos: is_used = True
                        
                        warn_msg = ""
                        if is_used:
                            warn_msg = f"{Colors.FAIL}警告: 该文件正在被当前配置使用！删除将导致虚拟机无法启动！{Colors.ENDC}\n"
                        
                        confirm = UI.get_input(f"{warn_msg}确认永久物理删除文件 '{fname}'? (y/N)", "N")
                        if confirm.lower() == 'y':
                            try:
                                if os.path.isdir(fpath):
                                    shutil.rmtree(fpath)
                                else:
                                    os.remove(fpath)
                                print(f"{Colors.GREEN}>> 文件已删除。{Colors.ENDC}")
                                
                                # Remove from config if used
                                if is_used:
                                    if target_dir == self.disk_dir:
                                        self.disks.remove(fname)
                                    elif target_dir == self.iso_dir:
                                        self.isos.remove(fname)
                                    self.save()
                            except Exception as e:
                                print(f"{Colors.FAIL}>> 删除失败: {e}{Colors.ENDC}")
                            time.sleep(1)

    # --- Disk Operations ---

    def get_disk_info(self, disk_name: str) -> Optional[Dict[str, Any]]:
        """Retrieves QEMU disk info as JSON."""
        path = os.path.join(self.disk_dir, disk_name)
        if not os.path.exists(path): return None
        try:
            res = subprocess.run(["qemu-img", "info", "--output=json", path], 
                                 capture_output=True, text=True, check=True)
            return json.loads(res.stdout)
        except:
            return None

    def manage_disk(self) -> None:
        """Interactive Disk Management Menu."""
        while True:
            UI.clear_screen()
            print(f"{Colors.CYAN}--- 磁盘管理 ---{Colors.ENDC}")
            if not self.disks:
                print("  (无磁盘)")
            else:
                for i, disk in enumerate(self.disks):
                    info = self.get_disk_info(disk)
                    status = ""
                    if info and 'backing-filename' in info:
                        status = f"{Colors.CYAN}[快照]{Colors.ENDC}"
                    else:
                        status = f"{Colors.BLUE}[基础]{Colors.ENDC}"
                    print(f"  [{i+1}] {disk} {status}")
            
            print("-" * 40)
            print("  [A] 添加新磁盘 (Add/Create)")
            print("  [I] 导入磁盘 (Import)")
            print("  [S] 快照管理 (Snapshots)")
            print("  [D] 卸载磁盘 (Detach)")
            print("  [F] 文件清理 (File Manager)")
            print("  [B] 返回 (Back)")
            
            choice = input("请选择: ").strip().lower()
            
            if choice == 'b': break
            elif choice == 's':
                self.manage_snapshots()
            elif choice == 'f':
                self.file_manager(self.disk_dir, "磁盘")
            elif choice == 'a':
                name = UI.get_input("请输入磁盘文件名 (如 system.qcow2)", "system.qcow2")
                size = UI.get_input("请输入大小 (如 60G)", "60G")
                dest_path = os.path.join(self.disk_dir, name)
                
                if os.path.exists(dest_path):
                    print(f"{Colors.FAIL}>> 错误: 文件已存在。{Colors.ENDC}")
                    time.sleep(1)
                    continue
                    
                print(f"{Colors.GREEN}>> 创建磁盘镜像...{Colors.ENDC}")
                subprocess.run(["qemu-img", "create", "-f", "qcow2", dest_path, size])
                self.disks.append(name)
                self.save()
                
            elif choice == 'i':
                path = UI.get_input("请输入源磁盘文件路径", "")
                imported_name = self.import_resource(path, self.disk_dir, "磁盘镜像")
                if imported_name:
                    self.disks.append(imported_name)
                    self.save()
            
            elif choice == 'd':
                idx_str = UI.get_input("请输入要卸载的磁盘序号", "")
                if idx_str.isdigit():
                    idx = int(idx_str) - 1
                    if 0 <= idx < len(self.disks):
                        disk_name = self.disks[idx]
                        confirm = UI.get_input(f"{Colors.WARNING}确认从配置中移除 '{disk_name}'? (文件保留) (y/N){Colors.ENDC}", "N")
                        if confirm.lower() == 'y':
                            del self.disks[idx]
                            self.save()
                            print(">> 磁盘已卸载。")

    def manage_snapshots(self) -> None:
        """Interactive Snapshot Management Menu."""
        while True:
            UI.clear_screen()
            print(f"{Colors.CYAN}--- 快照/覆盖层管理 (Snapshot/Overlay) ---{Colors.ENDC}")
            print("利用 QEMU 的 backing file 机制实现高性能快照。")
            print("基础镜像 (Base) -> 只读，作为模板")
            print("覆盖层 (Overlay) -> 读写，存储差异数据")
            print("-" * 40)
            
            if not self.disks:
                print("  (无磁盘)")
                time.sleep(1)
                break

            disk_infos: Dict[int, Optional[Dict[str, Any]]] = {}
            for i, disk in enumerate(self.disks):
                info = self.get_disk_info(disk)
                disk_infos[i] = info
                
                status = f"{Colors.GREEN}[基础镜像]{Colors.ENDC}"
                if info and 'backing-filename' in info:
                    backing = os.path.basename(info['backing-filename'])
                    status = f"{Colors.CYAN}[快照模式]{Colors.ENDC} -> {backing}"
                
                print(f"  [{i+1}] {disk}  {status}")

            print("-" * 40)
            print("  [B] 返回 (Back)")
            
            choice = input("请选择磁盘序号进行操作: ").strip().lower()
            if choice == 'b': break
            
            if choice.isdigit():
                idx = int(choice) - 1
                if 0 <= idx < len(self.disks):
                    self.snapshot_ops(idx, self.disks[idx], disk_infos[idx])

    def snapshot_ops(self, idx: int, disk_name: str, info: Optional[Dict[str, Any]]) -> None:
        """Operations for a specific disk (Snapshot/Reset/Commit)."""
        if not info:
            print(f"{Colors.FAIL}无法获取磁盘信息。{Colors.ENDC}")
            time.sleep(1)
            return

        is_overlay = 'backing-filename' in info
        disk_path = os.path.join(self.disk_dir, disk_name)

        print(f"\n选中磁盘: {Colors.BOLD}{disk_name}{Colors.ENDC}")
        if is_overlay:
            print(f"当前状态: {Colors.CYAN}覆盖层 (Overlay){Colors.ENDC}")
            print(f"基础镜像: {info['backing-filename']}")
            print("-" * 20)
            print("  [R] 重置 (Reset)   - 清空所有更改，恢复到基础镜像状态")
            print("  [C] 合并 (Commit)  - 将更改写入基础镜像 (慎用)")
            print("  [D] 丢弃 (Discard) - 删除快照，切回基础镜像")
            print("  [B] 返回")
            
            op = input("请选择: ").strip().lower()
            if op == 'r':
                if UI.get_input(f"{Colors.WARNING}确认重置? 所有未保存数据将丢失 (y/N){Colors.ENDC}", "N").lower() == 'y':
                    backing = info['backing-filename']
                    try:
                        os.remove(disk_path)
                        subprocess.run(["qemu-img", "create", "-f", "qcow2", 
                                      "-b", backing, "-F", "qcow2", disk_name], 
                                      cwd=self.disk_dir, check=True)
                        print(f"{Colors.GREEN}>> 重置成功。{Colors.ENDC}")
                    except Exception as e:
                        print(f"{Colors.FAIL}>> 操作失败: {e}{Colors.ENDC}")
                    time.sleep(1)
            
            elif op == 'c':
                print(f"{Colors.WARNING}警告: 这将把快照中的更改永久写入基础镜像。{Colors.ENDC}")
                if UI.get_input("确认合并? (y/N)", "N").lower() == 'y':
                    try:
                        subprocess.run(["qemu-img", "commit", disk_path], check=True)
                        print(f"{Colors.GREEN}>> 合并成功。{Colors.ENDC}")
                    except Exception as e:
                        print(f"{Colors.FAIL}>> 操作失败: {e}{Colors.ENDC}")
                    time.sleep(1)

            elif op == 'd':
                if UI.get_input(f"{Colors.WARNING}确认丢弃快照并切回基础镜像? (y/N){Colors.ENDC}", "N").lower() == 'y':
                    backing = info['backing-filename']
                    if not os.path.exists(os.path.join(self.disk_dir, backing)):
                        print(f"{Colors.FAIL}错误: 基础镜像文件 {backing} 不存在!{Colors.ENDC}")
                    else:
                        self.disks[idx] = backing
                        self.save()
                        try:
                            os.remove(disk_path)
                            print(f"{Colors.GREEN}>> 快照已删除，已切回基础镜像。{Colors.ENDC}")
                        except:
                            print(f"{Colors.WARNING}>> 配置已更新，但删除文件失败。{Colors.ENDC}")
                    time.sleep(1)

        else:
            print(f"当前状态: {Colors.GREEN}基础镜像 (Base){Colors.ENDC}")
            print("-" * 20)
            print("  [C] 创建快照 (Create Overlay) - 切换到快照模式")
            print("  [B] 返回")
            
            op = input("请选择: ").strip().lower()
            if op == 'c':
                overlay_name = f"{os.path.splitext(disk_name)[0]}.snap.qcow2"
                overlay_path = os.path.join(self.disk_dir, overlay_name)
                
                if os.path.exists(overlay_path):
                    print(f"{Colors.FAIL}错误: 目标文件 {overlay_name} 已存在。{Colors.ENDC}")
                else:
                    try:
                        subprocess.run(["qemu-img", "create", "-f", "qcow2", 
                                      "-b", disk_name, "-F", "qcow2", overlay_name], 
                                      cwd=self.disk_dir, check=True)
                        self.disks[idx] = overlay_name
                        self.save()
                        print(f"{Colors.GREEN}>> 快照创建成功，已切换到快照模式。{Colors.ENDC}")
                    except Exception as e:
                        print(f"{Colors.FAIL}>> 创建失败: {e}{Colors.ENDC}")
                time.sleep(1)

    # --- ISO & Mount Operations ---

    def manage_cdrom(self) -> None:
        """Interactive CDROM/ISO Management Menu."""
        while True:
            UI.clear_screen()
            print(f"{Colors.CYAN}--- 光驱/ISO 管理 ---{Colors.ENDC}")
            if not self.isos:
                print("  (无 ISO)")
            else:
                for i, iso in enumerate(self.isos):
                    print(f"  [{i+1}] {iso}")
            
            print("-" * 40)
            print("  [I] 导入 ISO 文件 (Import ISO)")
            print("  [D] 弹出/移除 ISO (Detach)")
            print("  [F] 文件清理 (File Manager)")
            print("  [B] 返回 (Back)")
            
            choice = input("请选择: ").strip().lower()
            
            if choice == 'b': break
            elif choice == 'f':
                self.file_manager(self.iso_dir, "ISO")
            elif choice == 'i':
                path = UI.get_input("请输入 ISO 文件路径", "")
                imported_name = self.import_resource(path, self.iso_dir, "ISO 镜像")
                if imported_name:
                    self.isos.append(imported_name)
                    self.save()
            elif choice == 'd':
                idx_str = UI.get_input("请输入要移除的 ISO 序号", "")
                if idx_str.isdigit():
                    idx = int(idx_str) - 1
                    if 0 <= idx < len(self.isos):
                        del self.isos[idx]
                        self.save()

    def manage_extra_mounts(self) -> None:
        """Interactive Extra Mounts (USB/VVFAT) Menu."""
        while True:
            UI.clear_screen()
            print(f"{Colors.CYAN}--- 更多挂载方式 (USB/VVFAT) ---{Colors.ENDC}")
            print("此处管理的资源将以 [USB 移动存储设备] 的形式挂载到虚拟机。")
            print(f"默认共享目录 (VVFAT/只读/500MB限制): {Colors.BLUE}{self.shared_dir}{Colors.ENDC}")
            print(f"临时挂载点数: {len(self.transient_mounts)}")
            print("-" * 40)
            print("  [I] 导入文件到默认共享目录 (Import to Default)")
            print("  [F] 管理默认共享目录文件 (File Manager)")
            print("  [A] 添加临时挂载 (Add Transient Mount)")
            print("  [C] 清空临时挂载 (Clear Transient)")
            print("  [O] 打开默认共享目录 (Open Default Folder)")
            print("  [B] 返回 (Back)")
            
            choice = input("请选择: ").strip().lower()
            
            if choice == 'b': break
            elif choice == 'f':
                self.file_manager(self.shared_dir, "共享")
            elif choice == 'i':
                path = UI.get_input("请输入要共享的文件路径", "")
                self.import_resource(path, self.shared_dir, "共享文件")
                input("按 Enter 继续...")
                
            elif choice == 'a':
                path = UI.get_input("请输入宿主机路径 (目录或镜像文件)", "")
                if not path: continue
                resolved_path = FS.expand_path(path)
                
                if not os.path.exists(resolved_path):
                    print(f"{Colors.FAIL}>> 错误: 路径不存在。{Colors.ENDC}")
                else:
                    self.transient_mounts.append(resolved_path)
                    if os.path.isdir(resolved_path):
                        print(f"{Colors.GREEN}>> 已添加目录 (VVFAT模式): {resolved_path}{Colors.ENDC}")
                    else:
                        print(f"{Colors.GREEN}>> 已添加文件 (Raw模式): {resolved_path}{Colors.ENDC}")
                time.sleep(1)
                
            elif choice == 'c':
                self.transient_mounts = []
                print(">> 已清空临时挂载。")
                time.sleep(1)
                
            elif choice == 'o':
                if sys.platform == 'linux':
                    subprocess.run(['xdg-open', self.shared_dir])
                print(">> 已尝试打开目录。")
                time.sleep(1)

# ==============================================================================
# MODULE: MAIN ENTRY POINT
# ==============================================================================

def session_loop(session_name: str, ovmf_code: str, ovmf_vars_template: str) -> None:
    """Main loop for a specific session."""
    session = Session(session_name)
    if not session.load():
        print("加载配置失败")
        time.sleep(1)
        return

    while True:
        UI.clear_screen()
        UI.print_header()
        print(f"当前会话: {Colors.GREEN}{session.name}{Colors.ENDC}")
        print(f"配置概览: {session.config.get('CPU_CORES')} Cores / {session.config.get('MEM_SIZE')} RAM")
        print(f"磁盘数量: {len(session.disks)}")
        print(f"ISO 数量: {len(session.isos)}")
        
        if session.transient_mounts:
            print(f"\n{Colors.CYAN}临时挂载:{Colors.ENDC}")
            for p in session.transient_mounts:
                print(f"  + {p}")

        print("-" * 52)
        print("  [S] 启动虚拟机 (Start)")
        print("  [H] 硬件配置 (Hardware)")
        print("  [D] 磁盘管理 (Disks)")
        print("  [C] 光驱管理 (CD/ISO)")
        print("  [M] 更多挂载 (Mounts)")
        print("  [X] 删除会话 (Delete Session)")
        print("  [B] 返回主菜单 (Back)")
        print("-" * 52)

        choice = input("请选择: ").strip().lower()

        if choice == 'b':
            break
        elif choice == 's':
            session.ensure_vars(ovmf_vars_template)
            runner = QEMURunner(session, ovmf_code)
            runner.run()
            input("\n按 Enter 返回会话菜单...")
        elif choice == 'h':
            session.configure_basic(is_new=False)
        elif choice == 'd':
            session.manage_disk()
        elif choice == 'c':
            session.manage_cdrom()
        elif choice == 'm':
            session.manage_extra_mounts()
        elif choice == 'x':
            confirm = UI.get_input(f"{Colors.FAIL}确认删除会话 '{session.name}'? (y/N){Colors.ENDC}", "N")
            if confirm.lower() == 'y':
                session.delete()
                print("会话已删除。")
                time.sleep(1)
                break

def main() -> None:
    """Application entry point."""
    FS.init_environment()
    
    # 1. Environment Check
    ovmf_code, ovmf_vars_template = FS.detect_ovmf()
    if not ovmf_code or not ovmf_vars_template:
        print(f"{Colors.FAIL}[严重错误] 未检测到 OVMF 固件或 VARS 模板。{Colors.ENDC}")
        print("请安装 ovmf (Debian/Ubuntu) 或 edk2-ovmf (Fedora/Arch)。")
        sys.exit(1)

    while True:
        UI.clear_screen()
        UI.print_header()
        print(f"存档位置: {SAVE_ROOT}")
        
        # 2. Scan Sessions
        sessions: List[str] = []
        if os.path.exists(SAVE_ROOT):
            for d in os.listdir(SAVE_ROOT):
                if os.path.isdir(os.path.join(SAVE_ROOT, d)):
                    sessions.append(d)
        sessions.sort()
        
        print(f"{Colors.BLUE}现有会话:{Colors.ENDC}")
        if not sessions:
            print("  (无)")
        else:
            for i, name in enumerate(sessions):
                print(f"  [{i+1}] {name}")
        
        print("-" * 52)
        print("  [N] 新建会话 (New Session)")
        print("  [Q] 退出 (Quit)")
        print("-" * 52)
        
        choice = input("请选择: ").strip().lower()
        
        if choice == 'q':
            sys.exit(0)
        elif choice == 'n':
            name = UI.get_input("请输入新会话名称 (唯一ID)", "")
            if not name: continue
            if name in sessions:
                print(f"{Colors.WARNING}会话已存在！{Colors.ENDC}")
                time.sleep(1)
                continue
            
            new_session = Session(name)
            new_session.create_structure()
            new_session.configure_basic(is_new=True)
            continue
            
        elif choice.isdigit():
            idx = int(choice) - 1
            if 0 <= idx < len(sessions):
                session_loop(sessions[idx], ovmf_code, ovmf_vars_template)
            else:
                print("无效选择")
                time.sleep(0.5)

if __name__ == "__main__":
    main()
