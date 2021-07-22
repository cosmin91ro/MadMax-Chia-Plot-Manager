from os import listdir, remove
from os.path import isfile, join
import logging
from datetime import datetime as dt

logging.basicConfig(format='%(asctime)s [%(levelname)s]: %(message)s', datefmt='%Y-%m-%d %H:%M:%S', level=logging.DEBUG)

def create(size, memory_buffer, temporary_directory, destination_directory, threads, buckets, bitfield,
           chia_location='chia', temporary2_directory=None, farmer_public_key=None, pool_public_key=None,
           exclude_final_directory=False):
    flags = dict(
        k=size,
        b=memory_buffer,
        t=temporary_directory,
        d=destination_directory,
        r=threads,
        u=buckets,
    )
    if temporary2_directory is not None:
        flags['2'] = temporary2_directory
    if farmer_public_key is not None:
        flags['f'] = farmer_public_key
    if pool_public_key is not None:
        flags['p'] = pool_public_key
    if bitfield is False:
        flags['e'] = ''
    if exclude_final_directory:
        flags['x'] = ''

    data = [chia_location, 'plots', 'create']
    for key, value in flags.items():
        flag = f'-{key}'
        data.append(flag)
        if value == '':
            continue
        data.append(str(value))
    return data

def madmaxCreate(temporary_directory, temporary2_directory, destination_directory, threads, buckets,
           chia_location='chia_plot', farmer_public_key=None, pool_public_key=None, pool_contract_address=None):
    flags = dict(
        t=temporary_directory,
        d=destination_directory,
        r=threads,
        u=buckets,
    )
    if temporary2_directory is not None:
        flags['2'] = temporary2_directory
    if farmer_public_key is not None:
        flags['f'] = farmer_public_key
    if pool_public_key is not None:
        flags['p'] = pool_public_key
    if pool_contract_address is not None:
        flags['c'] = pool_contract_address

    data = [chia_location]
    for key, value in flags.items():
        flag = f'-{key}'
        data.append(flag)
        if value == '':
            continue
        data.append(str(value))
    return data


def removeOldestPlot(path):
    onlyfiles = [join(path, f) for f in listdir(path) if isfile(join(path, f)) and f.endswith(".plot")]
    onlyfiles.sort()
    logging.info(f"Removing {onlyfiles[0]}")
    t1 = dt.now()
    remove(onlyfiles[0])
    logging.info(f"File removed. It took {dt.now() - t1}")
