# SPDX-License-Identifier: GPL-2.0-only
# Copyright (c) 2019-2020 NITK Surathkal

"""Script to be run for running experiments on topology"""

from multiprocessing import Process
from collections import namedtuple, defaultdict

from ..topology_map import TopologyMap
from .. import engine
# Import results
from .results import SsResults, NetperfResults, TcResults, PingResults
# Import parsers
from .parser.ss import SsRunner
from .parser.netperf import NetperfRunner
from .parser.tc import TcRunner
from .parser.ping import PingRunner
# Import plotters
from .plotter.ss import plot_ss
from .plotter.netperf import plot_netperf
from .plotter.tc import plot_tc
from .plotter.ping import plot_ping
from ..experiment.parser.iperf import IperfRunner
from ..engine.util import is_dependency_installed


#pylint: disable=too-many-locals
def run_experiment(exp):
    """
    Run experiment

    Parameters
    -----------
    exp : Experiment
        The experiment attributes
    """

    # Could be moved to config?
    tools = ['netperf', 'ss', 'tc', 'iperf3', 'ping']
    exp_workers = []    # Processes to setup flows and statistics collection
    Runners = namedtuple('runners', tools)
    exp_runners = Runners(netperf=[], ss=[], tc=[],
                          iperf3=[], ping=[])  # Runner objects

    # Contains start time and end time to run respective command
    # from a source netns to destination addr
    ss_schedules = defaultdict(lambda: (float('inf'), float('-inf')))
    ping_schedules = defaultdict(lambda: (float('inf'), float('-inf')))

    # exp_start = float('inf')
    exp_end_t = float('-inf')

    dependencies = get_dependency_status(tools)

    # Traffic generation
    for flow in exp.flows:
        # Get flow attributes
        [src_ns, _, dst_addr, start_t, stop_t,
         _, options] = flow._get_props()  # pylint: disable=protected-access

        # exp_start = min(exp_start, start_t)
        exp_end_t = max(exp_end_t, stop_t)

        (min_start, max_stop) = ping_schedules[(src_ns, dst_addr)]
        ping_schedules[(src_ns, dst_addr)] = (
            min(min_start, start_t), max(max_stop, stop_t))

        if options['protocol'] == 'TCP':
            dependencies['netperf'], tcp_runners, tcp_workers, ss_schedules = setup_tcp_flows(
                dependencies['netperf'], flow, ss_schedules)
            exp_runners.netperf.extend(tcp_runners)
            exp_workers.extend(tcp_workers)
        elif options['protocol'] == 'UDP':
            dependencies['iperf3'], udp_runners, upd_workers = setup_udp_flows(
                dependencies['iperf3'], flow)
            exp_runners.iperf3.extend(udp_runners)
            exp_workers.extend(upd_workers)

    if dependencies['netperf'] == 1:
        ss_workers, ss_runners = setup_ss_runners(dependencies['ss'],
                                                  ss_schedules)
        exp_workers.extend(ss_workers)
        exp_runners.ss.extend(ss_runners)

        tc_workers, tc_runners = setup_tc_runners(
            dependencies['tc'], exp.qdisc_stats, exp_end_t)
        exp_workers.extend(tc_workers)
        exp_runners.ss.extend(tc_runners)

    ping_workers, ping_runners = setup_ping_runners(
        dependencies['ping'], ping_schedules)
    exp_workers.extend(ping_workers)
    exp_runners.ping.extend(ping_runners)

    # Start traffic generation and parsing
    run_workers(exp_workers)

    print('Experiment complete!')
    print("Parsing statistics...")

    # Parse the stored statistics
    run_workers(get_parser_workers(exp_runners))

    print('Output results as JSON dump')

    # Output results as JSON dumps
    dump_json_ouputs()

    print('Plotting results...')

    # Plot results and dump them as images
    run_workers(get_plotter_workers())

    print('Plotting complete!')

    cleanup()


def run_workers(workers):
    """
    Run and wait for processes to finish

    Parameters
    ----------
    workers: list[multiprocessing.Process]
        List of processes to be run
    """
    # Start workers
    for worker in workers:
        worker.start()

    # wait for all the workers to finish
    for worker in workers:
        worker.join()


def get_plotter_workers():
    """
    Setup plotting processes

    Returns
    -------
    List[multiprocessing.Process]
        plotters
    """
    plotters = []

    plotters.append(Process(target=plot_ss, args=(SsResults.get_results(),)))
    plotters.append(Process(target=plot_netperf,
                            args=(NetperfResults.get_results(),)))
    plotters.append(Process(target=plot_tc, args=(TcResults.get_results(),)))
    plotters.append(
        Process(target=plot_ping, args=(PingResults.get_results(),)))

    return plotters


def dump_json_ouputs():
    """
    Outputs experiment results as json dumps
    """
    SsResults.output_to_file()
    NetperfResults.output_to_file()
    TcResults.output_to_file()
    PingResults.output_to_file()


def get_parser_workers(runners_list):
    """
    Setup parsing processes

    Parameters
    ----------
    runners_list: collections.NamedTuple
        all(netperf, ping, ss, tc..) the runners

    Returns
    -------
    List[multiprocessing.Process]
        parsers
    """
    runners = []

    for ss_runner in runners_list.ss:
        runners.append(Process(target=ss_runner.parse))

    for netperf_runner in runners_list.netperf:
        runners.append(Process(target=netperf_runner.parse))

    for tc_runner in runners_list.tc:
        runners.append(Process(target=tc_runner.parse))

    for ping_runner in runners_list.ping:
        runners.append(Process(target=ping_runner.parse))

    return runners


def get_dependency_status(tools):
    """
    Checks for dependency

    Parameters
    ----------
    tools: List[str]
        list of tools to check for it's installation

    Returns
    -------
    dict
        contains information as to whether `tools` are installed
    """
    dependencies = {}
    for dependency in tools:
        dependencies[dependency] = int(is_dependency_installed(dependency))
    return dependencies


def setup_tcp_flows(dependency, flow, ss_schedules):
    """
    Setup netperf to run tcp flows
    Parameters
    ----------
    dependency: int
        whether netperf is installed
    flow: Flow
        Flow parameters
    ss_schedules:
        ss_schedules so far

    Returns
    -------
    dependency: int
        updated dependency incase netperf is not installed
    netperf_runners: List[NetperfRunner]
        all the netperf flows generated
    workers: List[multiprocessing.Process]
        Processes to run netperf flows
    ss_schedules: dict
        updated ss_schedules
    """
    netperf_runners = []
    workers = []
    if dependency == 0:
        print('Warning: Netperf not found. Tcp flows cannot be generated')
        # To avoid duplicate warning messages
        dependency = 2
    elif dependency == 1:
        # Get flow attributes
        [src_ns, dst_ns, dst_addr, start_t, stop_t,
         n_flows, options] = flow._get_props()  # pylint: disable=protected-access
        src_name = TopologyMap.get_namespace(src_ns)['name']

        netperf_options = {}
        NetperfRunner.run_netserver(dst_ns)
        netperf_options['testname'] = 'TCP_STREAM'
        netperf_options['cong_algo'] = options['cong_algo']

        print('Running {} netperf flows from {} to {}...'.format(
            n_flows, src_name, dst_addr))

        # Create new processes to be run simultaneously
        for _ in range(n_flows):
            runner_obj = NetperfRunner(
                src_ns, dst_addr, start_t, stop_t-start_t, **netperf_options)
            netperf_runners.append(runner_obj)
            workers.append(Process(target=runner_obj.run))

        # Find the start time and stop time to run ss command in `src_ns` to a `dst_addr`
        if (src_ns, dst_addr) not in ss_schedules:
            ss_schedules[(src_ns, dst_addr)] = (start_t, stop_t)
        else:
            (min_start, max_stop) = ss_schedules[(src_ns, dst_addr)]
            ss_schedules[(src_ns, dst_addr)] = (
                min(min_start, start_t), max(max_stop, stop_t))

    return dependency, netperf_runners, workers, ss_schedules


def setup_udp_flows(dependency, flow):
    """
    Setup iperf3 to run udp flows

    Parameters
    ----------
    dependency: int
        whether iperf3 is installed
    flow: Flow
        Flow parameters

    Returns
    -------
    depedency: int
        updated dependency incase iproute2 is not installed
    iperf3_runners: List[NetperfRunner]
        all the iperf3 udp flows generated
    workers: List[multiprocessing.Process]
        Processes to run iperf3 udp flows
    """
    iperf3_runners = []
    workers = []
    if dependency == 0:
        print('Warning: Iperf3 not found. Udp flows cannot be generated')
        # To avoid duplicate warning messages
        dependency = 2
    elif dependency == 1:
        # Get flow attributes
        [src_ns, dst_ns, dst_addr, start_t, stop_t,
         n_flows, options] = flow._get_props()  # pylint: disable=protected-access
        src_name = TopologyMap.get_namespace(src_ns)['name']
        IperfRunner(dst_ns).run_server()

        print('Running {} udp flows from {} to {}...'.format(
            n_flows, src_name, dst_addr))

        runner_obj = IperfRunner(src_ns)
        iperf3_runners.append(runner_obj)
        workers.append(
            Process(target=runner_obj.run_client,
                    args=[dst_addr, start_t, stop_t-start_t, n_flows, options['target_bw']])
        )
    return dependency, iperf3_runners, workers


def setup_ss_runners(dependency, ss_schedules):
    """
    setup SsRunners for collecting tcp socket statistics

    Parameters
    ----------
    dependency: int
        whether ss is installed
    ss_schedules: dict
        start time and end time for SsRunners

    Returns
    -------
    workers: List[multiprocessing.Process]
        Processes to run ss at nodes
    runners: List[SsRunners]
    """
    runners = []
    workers = []
    if dependency == 1:
        print('Running ss on nodes...')
        print()
        for ns_id, timings in ss_schedules.items():
            ss_runner = SsRunner(ns_id[0], ns_id[1], timings[0],
                                 timings[1] - timings[0])
            runners.append(ss_runner)
            workers.append(Process(target=ss_runner.run))
    else:
        print('Warning: ss not found. Sockets stats will not be collected')
    return workers, runners


def setup_tc_runners(dependency, qdisc_stats, exp_end):
    """
    setup TcRunners for collecting qdisc statistics

    Parameters
    ----------
    dependency: int
        whether tc is installed
    qdisc_stats: dict
        info regarding nodes to run tc on
    exp_end: float
        time to stop running tc
    Returns
    -------
    workers: List[multiprocessing.Process]
        Processes to run tc at nodes
    runners: List[TcRunners]
    """
    runners = []
    workers = []
    if dependency == 1 and len(qdisc_stats) > 0:
        print('Running tc on requested interfaces...')
        print()
        for qdisc_stat in qdisc_stats:
            tc_runner = TcRunner(
                qdisc_stat['ns_id'], qdisc_stat['int_id'], exp_end)
            runners.append(
                tc_runner)
            workers.append(Process(target=tc_runner.run))
    elif dependency != 1:
        print('Warning: tc not found. Qdisc stats will not be collected')
    return workers, runners


def setup_ping_runners(dependency, ping_schedules):
    """
    setup PingRunners for collecting latency

    Parameters
    ----------
    dependency: int
        whether ping is installed
    ping_schedules: dict
        start time and end time for PingRunners

    Returns
    -------
    workers: List[multiprocessing.Process]
        Processes to run ss at nodes
    runners: List[SsRunners]
    """
    runners = []
    workers = []
    if dependency == 1:
        for ns_id, timings in ping_schedules.items():
            ping_runner = PingRunner(
                ns_id[0], ns_id[1], timings[0], timings[1]-timings[0])
            runners.append(ping_runner)
            workers.append(Process(target=ping_runner.run))
    else:
        print('Warning: ping not found')
    return workers, runners


def cleanup():
    """
    Clean up
    """
    # Remove results of the experiment
    SsResults.remove_all_results()
    NetperfResults.remove_all_results()
    TcResults.remove_all_results()
    PingResults.remove_all_results()

    # Kill any running processes in namespaces
    for namespace in TopologyMap.get_namespaces():
        engine.kill_all_processes(namespace['id'])
