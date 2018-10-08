import os
import re
import sys
import random

from Queue import Queue
from files import write_file
from struct import pack
from struct import unpack
from pexpect import spawn
from datetime import datetime
from threading import Thread


def compile_gpp(code, temp_dir):
    """Compile C++ source file and return path to binary.."""

    datetime_str = datetime.utcnow().strftime(r"run-%Y%m%d-%H%M-")
    random_str = "".join(random.sample("0123456789", 6))

    subdirs = [temp_dir, "psim", datetime_str + random_str]
    sim_dir = os.path.join(*subdirs)

    source_file = os.path.join(sim_dir, 'psim.cpp')
    output_file = os.path.join(sim_dir, 'psim.exe')

    flags = "-std=c++11 -fdiagnostics-color=always"
    gpp_cmd = "g++ %s -o %s %s" % (flags, output_file, source_file)

    # Create simulation directory (plus parents, if necessary).
    if not os.path.isdir(sim_dir):
         os.makedirs(sim_dir)

    # Write source file and compile.
    write_file(source_file, code)
    gpp = spawn(gpp_cmd)
    gpp.wait()

    if gpp.exitstatus != 0:
        raise Exception("Compilation failed (%s)" % source_file)

    # Return path to compiled binary.
    return output_file


def print_line(line):

    if line.startswith("msg: "):
        msg_bytes = line[5:]
        msg = unpack("<II", msg_bytes[:8])
        print "Got message, bytes =", list(bytearray(msg_bytes))
        print "Decoded message = %s" % repr(msg)

    else:
        print line

    sys.stdout.flush()


def create_line_parser(log, states, metrics):

    def parse_field_str(field_str):
        fields = {}
        for item in field_str.split(', '):
            key, val = item.split(' = ')
            fields[key] = int(val)
        return fields

    def parse_app_line(device_name, log_level, msg):
        entry = device_name, int(log_level), msg
        log.append(entry)

    def parse_state_line(device_name, field_str):
        states[device_name] = parse_field_str(field_str)

    def parse_metric_line(metric_name, value):
        if metric_name == "Delivered messages":
            old_count = metrics.get(metric_name, 0)
            metrics[metric_name] = old_count + int(value)
        else:
            metrics[metric_name] = int(value)

    preprocessors = [
        (r"^App \[(.+), (\d+)]: (.+)", parse_app_line),
        (r"^State \[(.+)\]: (.+)", parse_state_line),
        (r"^Metric \[(.+)\]: (.+)", parse_metric_line)
    ]

    pats = [re.compile(reg) for reg, _ in preprocessors]

    def parse_line(line):
        for pat, (_, line_parser) in zip(pats, preprocessors):
            for item in pat.findall(line):
                line_parser(*item)

    return parse_line


def run_worker(queue, index, cmd):
    """Run simulation worker."""

    engine = spawn(cmd, echo=False, timeout=None)

    while True:
        line = engine.readline()
        queue.put((index, line.strip()))
        if not line:
            break

    queue.put((index, None))


def simulate(code, quiet, nworkers=1, temp_dir="/tmp"):
    """Run distributed simulation."""

    engine_file = compile_gpp(code, temp_dir)

    cmd_sing = "%s %d"
    cmd_dist = 'socat exec:"%s %d",fdout=3 tcp:localhost:6379'
    cmd = cmd_dist if nworkers>1 else cmd_sing

    queue = Queue()

    def create_worker(index):
        args = (queue, index, cmd % (engine_file, index))
        return Thread(target=run_worker, args=args)

    workers = map(create_worker, range(nworkers))

    for worker in workers:
        worker.setDaemon(True)
        worker.start()

    log = []
    states = {}
    metrics = {}
    done = {index: False for index in range(nworkers)}

    parse_line = create_line_parser(log, states, metrics)

    while True:

        index, payload = queue.get()

        queue.task_done()

        if type(payload) is str:
            line = payload
            if not quiet:
                print "%s -> %s" % (index, line)
            parse_line(line.strip())
            continue

        done[index] = True

        if all(done.values()):
            break

    return {"log": log, "states": states, "metrics": metrics}
