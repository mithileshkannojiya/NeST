# SPDX-License-Identifier: GPL-2.0-only
# Copyright (c) 2019-2020 NITK Surathkal

"""Routing commands"""
from .. import config
from .exec import exec_subprocess


# Path to routing_suite daemon binaries
FRR_DAEMONPATH = "/usr/lib/frr/"


def run_zebra(ns_id, conf_file, pid_file):
    """
    Runs the zebra daemon

    Parameters
    ----------
    ns_id : str
        namespace of the router
    conf_file : str
        path to config file
    pid_file : str
        path to pid file
    """
    if config.get_value("routing_suite") == "frr":
        cmd = f"ip netns exec {ns_id} {FRR_DAEMONPATH}zebra --config_file {conf_file} \
                --pid_file {pid_file} --retain --daemon -N {ns_id}"
    else:
        cmd = f"ip netns exec {ns_id} zebra --config_file {conf_file} \
                --pid_file {pid_file} --retain --daemon"
    exec_subprocess(cmd)


def run_ripd(ns_id, conf_file, pid_file):
    """
    Runs the ripd daemon

    Parameters
    ----------
    ns_id : str
        namespace of the router
    conf_file : str
        path to config file
    pid_file : str
        path to pid file
    """
    if config.get_value("routing_suite") == "frr":
        cmd = f"ip netns exec {ns_id} {FRR_DAEMONPATH}ripd --config_file {conf_file} \
                --pid_file {pid_file} --daemon -N {ns_id}"
    else:
        cmd = f"ip netns exec {ns_id} ripd --config_file {conf_file} \
                --pid_file {pid_file} --retain --daemon"
    exec_subprocess(cmd)


def run_ospfd(ns_id, conf_file, pid_file):
    """
    Runs the ospfd daemon

    Parameters
    ----------
    ns_id : str
        namespace of the router
    conf_file : str
        path to config file
    pid_file : str
        path to pid file
    """
    if config.get_value("routing_suite") == "frr":
        cmd = f"ip netns exec {ns_id} {FRR_DAEMONPATH}ospfd --config_file {conf_file} \
            --pid_file {pid_file} --daemon -N {ns_id}"
    else:
        cmd = f"ip netns exec {ns_id} ospfd --config_file {conf_file} \
            --pid_file {pid_file} --daemon"
    exec_subprocess(cmd)


def run_isisd(ns_id, conf_file, pid_file):
    """
    Runs the isisd daemon

    Parameters
    ----------
    ns_id : str
        namespace of the router
    conf_file : str
        path to config file
    pid_file : str
        path to pid file
    """
    if config.get_value("routing_suite") == "frr":
        cmd = f"ip netns exec {ns_id} {FRR_DAEMONPATH}isisd --config_file {conf_file} \
            --pid_file {pid_file} --daemon -N {ns_id}"
    else:
        cmd = f"ip netns exec {ns_id} isisd --config_file {conf_file} \
            --pid_file {pid_file} --daemon"
    exec_subprocess(cmd)


def chown_to_daemon(path):
    """
    Change ownership of config directory and files to daemon userid

    Parameters
    ----------
    path : str
        path to file or directory
    """
    if config.get_value("routing_suite") == "frr":
        cmd = f"chown frr {path}"
    else:
        cmd = f"chown quagga {path}"
    exec_subprocess(cmd)
