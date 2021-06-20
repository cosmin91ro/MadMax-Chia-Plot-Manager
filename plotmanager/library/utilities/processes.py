import logging
import os
import platform
import psutil
import re
import subprocess
import pathlib

from copy import deepcopy
from datetime import datetime

from plotmanager.library.utilities.objects import Work
from plotmanager.library.utilities.instrumentation import set_plots_running


def _contains_in_list(string, lst, case_insensitive=False):
    if case_insensitive:
        string = string.lower()
    for item in lst:
        if case_insensitive:
            item = item.lower()
        if string not in item:
            continue
        return True
    return False


def get_manager_processes():
    processes = []
    for process in psutil.process_iter():
        try:
            if not re.search(r'^pythonw?(?:\d+\.\d+|\d+)?(?:\.exe)?$', process.name(), flags=re.I):
                continue
            if not _contains_in_list('python', process.cmdline(), case_insensitive=True) or \
                    not _contains_in_list('stateless-manager.py', process.cmdline()):
                continue
            processes.append(process)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    return processes


def check_chia_dashboard_process():
    logging.info("Checking for chia-dashboard-satellite process ...")
    dashboard_process = None
    for process in psutil.process_iter():
        try:
            if process.cmdline() and "/chia-dashboard-satellite" in process.cmdline()[-1]:
                dashboard_process = process
                break
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    if dashboard_process is None:
        logging.info("No chia-dashboard-satellite process found, starting one ...")
        directory = pathlib.Path().resolve()
        dashboard_log_file_path = os.path.join(directory, 'chia-dashboard-satellite.log')
        dashboard_log_file = open(dashboard_log_file_path, 'a')
        if start_process(["chia-dashboard-satellite"], log_file=dashboard_log_file):
            logging.info("chia-dashboard-satellite started")
    else:
        logging.info("chia-dashboard-satellite already running")



def is_windows():
    return platform.system() == 'Windows'


def get_chia_executable_name():
    # return f'chia{".exe" if is_windows() else ""}'
    return f'chia_plot{".exe" if is_windows() else ""}'



def get_plot_k_size(commands):
    try:
        k_index = commands.index('-k') + 1
    except ValueError:
        return None
    return commands[k_index]


def get_plot_directories(commands):
    try:
        temporary_index = commands.index('-t') + 1
    except ValueError:
        return None, None, None
    try:
        destination_index = commands.index('-d') + 1
    except ValueError:
        destination_index = temporary_index
    try:
        temporary2_index = commands.index('-2') + 1
    except ValueError:
        temporary2_index = temporary_index
    temporary_directory = commands[temporary_index]
    destination_directory = commands[destination_index]
    temporary2_directory = None
    if temporary2_index:
        temporary2_directory = commands[temporary2_index]
    return temporary_directory, temporary2_directory, destination_directory


def get_plot_drives(commands, drives=None):
    if not drives:
        drives = get_system_drives()
    temporary_directory, temporary2_directory, destination_directory = get_plot_directories(commands=commands)
    temporary_drive = identify_drive(file_path=temporary_directory, drives=drives)
    destination_drive = identify_drive(file_path=destination_directory, drives=drives)
    temporary2_drive = None
    if temporary2_directory:
        temporary2_drive = identify_drive(file_path=temporary2_directory, drives=drives)
    return temporary_drive, temporary2_drive, destination_drive


def get_chia_drives():
    drive_stats = {'temp': {}, 'temp2': {}, 'dest': {}}
    chia_executable_name = get_chia_executable_name()
    for process in psutil.process_iter():
        try:
            if chia_executable_name not in process.name() and 'python' not in process.name().lower():
                continue
        except (psutil.AccessDenied, psutil.NoSuchProcess):
            continue
        try:
            if 'plots' not in process.cmdline() or 'create' not in process.cmdline():
                continue
        except (psutil.ZombieProcess, psutil.NoSuchProcess):
            continue
        commands = process.cmdline()
        temporary_drive, temporary2_drive, destination_drive = get_plot_drives(commands=commands)
        if not temporary_drive and not destination_drive:
            continue

        if temporary_drive not in drive_stats['temp']:
            drive_stats['temp'][temporary_drive] = 0
        drive_stats['temp'][temporary_drive] += 1
        if destination_drive not in drive_stats['dest']:
            drive_stats['dest'][destination_drive] = 0
        drive_stats['dest'][destination_drive] += 1
        if temporary2_drive:
            if temporary2_drive not in drive_stats['temp2']:
                drive_stats['temp2'][temporary2_drive] = 0
            drive_stats['temp2'][temporary2_drive] += 1

    return drive_stats


def get_system_drives():
    drives = []
    for disk in psutil.disk_partitions(all=True):
        drive = disk.mountpoint
        if is_windows():
            drive = os.path.splitdrive(drive)[0]
        drives.append(drive)
    drives.sort(reverse=True)
    return drives


def identify_drive(file_path, drives):
    if not file_path:
        return None
    for drive in drives:
        if drive not in file_path:
            continue
        return drive
    return None


def get_plot_id(file_path=None, contents=None):
    if not contents:
        f = open(file_path, 'r')
        contents = f.read()
        f.close()

    match = re.search(r'^Plot Name: plot-k32-\d{4}-\d{2}-\d{2}-\d{2}-\d{2}-(.*?)$', contents, flags=re.M)
    if match:
        return match.groups()[0]
    return None


def get_temp_size(plot_id, temporary_directory, temporary2_directory):
    if not plot_id:
        return 0
    temp_size = 0
    directories = []
    if temporary_directory:
        directories += [os.path.join(temporary_directory, file) for file in os.listdir(temporary_directory) if file]
    if temporary2_directory:
        directories += [os.path.join(temporary2_directory, file) for file in os.listdir(temporary2_directory) if file]
    for file_path in directories:
        if plot_id not in file_path:
            continue
        try:
            temp_size += os.path.getsize(file_path)
        except FileNotFoundError:
            pass
    return temp_size


def get_running_plots(jobs, running_work, instrumentation_settings):
    chia_processes = []
    logging.info(f'Getting running plots')
    chia_executable_name = get_chia_executable_name()
    for process in psutil.process_iter():
        # logging.debug(f"Checking process {process.name()}")
        try:
            if chia_executable_name not in process.name():  # and 'python' not in process.name().lower():
                continue
        except (psutil.AccessDenied, psutil.NoSuchProcess):
            continue
        logging.info(f'Found chia plotting process: {process.pid}')
        datetime_start = datetime.fromtimestamp(process.create_time())
        chia_processes.append([datetime_start, process])
    chia_processes.sort(key=lambda x: (x[0]))

    for datetime_start, process in chia_processes:
        logging.info(f'Finding log file for process: {process.pid}')
        log_file_path = None
        commands = []
        try:
            commands = process.cmdline()
            for file in process.open_files():
                if '.mui' == file.path[-4:]:
                    continue
                if file.path[-4:] not in ['.log', '.txt']:
                    continue
                if file.path[-9:] == 'debug.log':
                    continue
                log_file_path = file.path
                logging.info(f'Found log file: {log_file_path}')
                break
        except (psutil.AccessDenied, RuntimeError):
            logging.info(f'Failed to find log file: {process.pid}')
        except psutil.NoSuchProcess:
            continue

        assumed_job = None
        logging.info(f'Finding associated job')

        temporary_directory, temporary2_directory, destination_directory = get_plot_directories(commands=commands)
        for job in jobs:
            if isinstance(job.temporary_directory, list) and temporary_directory not in job.temporary_directory:
                continue
            if not isinstance(job.temporary_directory, list) and temporary_directory != job.temporary_directory:
                continue
            logging.info(f'Found job: {job.name}')
            assumed_job = job
            break

        plot_id = None
        if log_file_path:
            plot_id = get_plot_id(file_path=log_file_path)

        temp_file_size = get_temp_size(plot_id=plot_id, temporary_directory=temporary_directory,
                                       temporary2_directory=temporary2_directory)

        temporary_drive, temporary2_drive, destination_drive = get_plot_drives(commands=commands)
        k_size = get_plot_k_size(commands=commands)
        work = deepcopy(Work())
        work.job = assumed_job
        work.log_file = log_file_path
        work.datetime_start = datetime_start
        work.pid = process.pid
        work.plot_id = plot_id
        work.work_id = '?'
        if assumed_job:
            work.work_id = assumed_job.current_work_id
            assumed_job.current_work_id += 1
            assumed_job.total_running += 1
            set_plots_running(total_running_plots=assumed_job.total_running, job_name=assumed_job.name,
                              instrumentation_settings=instrumentation_settings)
            assumed_job.running_work = assumed_job.running_work + [process.pid]
        work.temporary_drive = temporary_drive
        work.temporary2_drive = temporary2_drive
        work.destination_drive = destination_drive
        work.temp_file_size = temp_file_size
        work.k_size = k_size

        running_work[work.pid] = work
    logging.info(f'Finished finding running plots')

    return jobs, running_work


def start_process(args, log_file):
    kwargs = {}
    if is_windows():
        flags = 0
        flags |= 0x00000008
        kwargs = {
            'creationflags': flags,
        }
    process = subprocess.Popen(
        args=args,
        stdout=log_file,
        stderr=log_file,
        shell=False,
        **kwargs,
    )
    return process
