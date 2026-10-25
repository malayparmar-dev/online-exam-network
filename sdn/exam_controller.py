import ipaddress
import os
import socket
import time

from os_ken.base import app_manager
from os_ken.controller import ofp_event
from os_ken.controller.handler import (
    CONFIG_DISPATCHER,
    MAIN_DISPATCHER,
    DEAD_DISPATCHER,
    set_ev_cls,
)
from os_ken.lib import hub
from os_ken.lib.packet import packet, ethernet, ipv4
from os_ken.ofproto import ofproto_v1_3


class ExamController(app_manager.OSKenApp):
    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]

    # Configuration
    SERVER_IP = "10.0.0.10"
    CONTROL_HOST = "127.0.0.1"
    CONTROL_PORT = 8765

    def __init__(self, *args, **kwargs):
        super(ExamController, self).__init__(*args, **kwargs)

        self.state_lock = hub.Semaphore(1)
        self.mac_to_port = {}
        self.datapaths = {}

        # Manually blocked IP addresses
        self.blocked_ips = set()

        # IP addresses blocked automatically by traffic detection
        self.auto_blocked_ips = set()

        # Flow statistics
        self.stats_interval = self._positive_float_env(
            "EXAM_STATS_INTERVAL", 2.0, 0.25, 60.0
        )
        self.previous_flow_stats = {}

        # A higher threshold avoids blocking normal exam traffic on the 10 Mbps
        # host links while still detecting high-rate small-packet bursts.
        self.source_rate_threshold = self._positive_float_env(
            "EXAM_AUTO_BLOCK_PPS", 5000.0, 1.0, 10000000.0
        )
        self.control_port = self._positive_int_env(
            "EXAM_CONTROL_PORT", self.CONTROL_PORT, 1, 65535
        )

        # Start background services
        hub.spawn(self._run_control_server)
        hub.spawn(self._poll_flow_stats)

    @staticmethod
    def _positive_float_env(name, default, minimum, maximum):
        value = os.getenv(name)
        if value is None:
            return default
        try:
            parsed = float(value)
        except ValueError as exc:
            raise ValueError(f"{name} must be numeric") from exc
        if not minimum <= parsed <= maximum:
            raise ValueError(f"{name} must be between {minimum} and {maximum}")
        return parsed

    @staticmethod
    def _positive_int_env(name, default, minimum, maximum):
        value = os.getenv(name)
        if value is None:
            return default
        try:
            parsed = int(value)
        except ValueError as exc:
            raise ValueError(f"{name} must be an integer") from exc
        if not minimum <= parsed <= maximum:
            raise ValueError(f"{name} must be between {minimum} and {maximum}")
        return parsed

    # ---------------------------------------------------------
    # Switch connection and initialization
    # ---------------------------------------------------------

    @set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
    def switch_features_handler(self, ev):
        datapath = ev.msg.datapath
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser

        # Clear existing flows when the switch connects
        delete_all = parser.OFPFlowMod(
            datapath=datapath,
            command=ofproto.OFPFC_DELETE,
            out_port=ofproto.OFPP_ANY,
            out_group=ofproto.OFPG_ANY,
            match=parser.OFPMatch(),
        )
        datapath.send_msg(delete_all)

        # Install the table-miss rule
        match = parser.OFPMatch()
        actions = [
            parser.OFPActionOutput(
                ofproto.OFPP_CONTROLLER,
                ofproto.OFPCML_NO_BUFFER,
            )
        ]

        instructions = [
            parser.OFPInstructionActions(
                ofproto.OFPIT_APPLY_ACTIONS,
                actions,
            )
        ]

        flow_mod = parser.OFPFlowMod(
            datapath=datapath,
            priority=0,
            match=match,
            instructions=instructions,
        )
        datapath.send_msg(flow_mod)

        self.logger.info(
            "Switch connected: datapath_id=%s",
            datapath.id,
        )

        # Reapply manually or automatically blocked IP rules
        with self.state_lock:
            blocked_ips = tuple(self.blocked_ips)
        for ip in blocked_ips:
            self._install_block_rule(datapath, ip)

    @set_ev_cls(
        ofp_event.EventOFPStateChange,
        [MAIN_DISPATCHER, DEAD_DISPATCHER],
    )
    def state_change_handler(self, ev):
        datapath = ev.datapath

        if ev.state == MAIN_DISPATCHER:
            with self.state_lock:
                if datapath.id not in self.datapaths:
                    self.logger.info(
                        "Registering datapath: %s",
                        datapath.id,
                    )
                self.datapaths[datapath.id] = datapath

        elif ev.state == DEAD_DISPATCHER:
            with self.state_lock:
                self.datapaths.pop(datapath.id, None)

                stale_keys = [
                    key for key in self.previous_flow_stats
                    if key[0] == datapath.id
                ]
                for key in stale_keys:
                    del self.previous_flow_stats[key]

    # ---------------------------------------------------------
    # Packet forwarding
    # ---------------------------------------------------------

    @set_ev_cls(ofp_event.EventOFPPacketIn, MAIN_DISPATCHER)
    def packet_in_handler(self, ev):
        msg = ev.msg
        datapath = msg.datapath
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser

        in_port = msg.match["in_port"]

        pkt = packet.Packet(msg.data)
        eth = pkt.get_protocol(ethernet.ethernet)

        if eth is None:
            return

        # Ignore LLDP packets
        if eth.ethertype == 0x88CC:
            return

        dpid = datapath.id
        self.mac_to_port.setdefault(dpid, {})

        src_mac = eth.src
        dst_mac = eth.dst

        # Learn the source MAC address
        self.mac_to_port[dpid][src_mac] = in_port

        # Determine the destination port
        out_port = self.mac_to_port[dpid].get(
            dst_mac,
            ofproto.OFPP_FLOOD,
        )

        actions = [parser.OFPActionOutput(out_port)]

        # Install a source-IP-specific forwarding rule for IPv4
        if out_port != ofproto.OFPP_FLOOD:
            ip_header = pkt.get_protocol(ipv4.ipv4)

            if ip_header is not None:
                with self.state_lock:
                    blocked = ip_header.src in self.blocked_ips
                if blocked:
                    return

                match = parser.OFPMatch(
                    in_port=in_port,
                    eth_dst=dst_mac,
                    eth_type=0x0800,
                    ipv4_src=ip_header.src,
                )

                instructions = [
                    parser.OFPInstructionActions(
                        ofproto.OFPIT_APPLY_ACTIONS,
                        actions,
                    )
                ]

                flow_mod = parser.OFPFlowMod(
                    datapath=datapath,
                    priority=10,
                    match=match,
                    instructions=instructions,
                    idle_timeout=60,
                )
                datapath.send_msg(flow_mod)

            else:
                # Generic forwarding rule for non-IPv4 traffic
                match = parser.OFPMatch(
                    in_port=in_port,
                    eth_dst=dst_mac,
                )

                instructions = [
                    parser.OFPInstructionActions(
                        ofproto.OFPIT_APPLY_ACTIONS,
                        actions,
                    )
                ]

                flow_mod = parser.OFPFlowMod(
                    datapath=datapath,
                    priority=1,
                    match=match,
                    instructions=instructions,
                    idle_timeout=60,
                )
                datapath.send_msg(flow_mod)

        # Forward the packet
        data = None
        if msg.buffer_id == ofproto.OFP_NO_BUFFER:
            data = msg.data

        out = parser.OFPPacketOut(
            datapath=datapath,
            buffer_id=msg.buffer_id,
            in_port=in_port,
            actions=actions,
            data=data,
        )
        datapath.send_msg(out)

    # ---------------------------------------------------------
    # IP blocking
    # ---------------------------------------------------------

    def _install_block_rule(self, datapath, ip_address):
        parser = datapath.ofproto_parser

        match = parser.OFPMatch(
            eth_type=0x0800,
            ipv4_src=ip_address,
        )

        flow_mod = parser.OFPFlowMod(
            datapath=datapath,
            priority=100,
            match=match,
            instructions=[],
        )

        datapath.send_msg(flow_mod)

    def block_ip(self, ip_address):
        try:
            ip_address = str(ipaddress.IPv4Address(ip_address))
        except ipaddress.AddressValueError:
            self.logger.error("Invalid IPv4 address: %s", ip_address)
            return False

        if ip_address == self.SERVER_IP:
            self.logger.warning(
                "Refusing to block exam server IP=%s",
                ip_address,
            )
            return False

        with self.state_lock:
            self.blocked_ips.add(ip_address)
            datapaths = tuple(self.datapaths.values())

        for datapath in datapaths:
            self._install_block_rule(datapath, ip_address)

        self.logger.warning("BLOCKED IP: %s", ip_address)
        return True

    def unblock_ip(self, ip_address):
        try:
            ip_address = str(ipaddress.IPv4Address(ip_address))
        except ipaddress.AddressValueError:
            self.logger.error("Invalid IPv4 address: %s", ip_address)
            return False

        with self.state_lock:
            datapaths = tuple(self.datapaths.values())
            self.blocked_ips.discard(ip_address)
            self.auto_blocked_ips.discard(ip_address)

        for datapath in datapaths:
            parser = datapath.ofproto_parser
            ofproto = datapath.ofproto

            match = parser.OFPMatch(
                eth_type=0x0800,
                ipv4_src=ip_address,
            )

            flow_mod = parser.OFPFlowMod(
                datapath=datapath,
                command=ofproto.OFPFC_DELETE,
                out_port=ofproto.OFPP_ANY,
                out_group=ofproto.OFPG_ANY,
                match=match,
            )

            datapath.send_msg(flow_mod)

        self.logger.info("UNBLOCKED IP: %s", ip_address)
        return True

    # ---------------------------------------------------------
    # Flow statistics polling
    # ---------------------------------------------------------

    def _poll_flow_stats(self):
        while True:
            with self.state_lock:
                datapaths = tuple(self.datapaths.values())
            for datapath in datapaths:
                try:
                    parser = datapath.ofproto_parser

                    request = parser.OFPFlowStatsRequest(
                        datapath=datapath,
                    )

                    datapath.send_msg(request)

                except Exception as exc:
                    self.logger.error(
                        "Could not request flow stats from switch %s: %s",
                        datapath.id,
                        exc,
                    )

            hub.sleep(self.stats_interval)

    @set_ev_cls(
        ofp_event.EventOFPFlowStatsReply,
        MAIN_DISPATCHER,
    )
    def flow_stats_reply_handler(self, ev):
        msg = ev.msg
        datapath = msg.datapath
        dpid = datapath.id
        now = time.monotonic()

        for stat in msg.body:
            # Only analyze IPv4 forwarding rules installed by this controller
            if stat.priority != 10:
                continue

            src_ip = stat.match.get("ipv4_src")

            if not src_ip:
                continue

            # Never use server traffic to trigger automatic blocking
            if src_ip == self.SERVER_IP:
                continue

            key = (
                dpid,
                src_ip,
                stat.match.get("in_port"),
                stat.match.get("eth_dst"),
            )

            packet_count = stat.packet_count
            byte_count = stat.byte_count

            with self.state_lock:
                previous = self.previous_flow_stats.get(key)
                self.previous_flow_stats[key] = (now, packet_count, byte_count)

            if previous is None:
                continue

            previous_time, previous_packets, previous_bytes = previous
            elapsed = now - previous_time

            if elapsed <= 0:
                continue

            packet_rate = max(
                0,
                packet_count - previous_packets,
            ) / elapsed

            byte_rate = max(
                0,
                byte_count - previous_bytes,
            ) / elapsed

            self.logger.info(
                "CLIENT STATS: IP=%s switch=%s "
                "packets/s=%.2f bytes/s=%.2f",
                src_ip,
                dpid,
                packet_rate,
                byte_rate,
            )

            # Automatic blocking for high-rate clients only
            if packet_rate >= self.source_rate_threshold:
                with self.state_lock:
                    should_block = (
                        src_ip not in self.auto_blocked_ips
                        and src_ip not in self.blocked_ips
                    )
                if should_block:
                    self.logger.warning(
                        "HIGH TRAFFIC DETECTED: "
                        "IP=%s rate=%.2f packets/s threshold=%.2f",
                        src_ip,
                        packet_rate,
                        self.source_rate_threshold,
                    )

                    if self.block_ip(src_ip):
                        with self.state_lock:
                            self.auto_blocked_ips.add(src_ip)

    # ---------------------------------------------------------
    # Local TCP control interface
    # ---------------------------------------------------------

    def _run_control_server(self):
        server_socket = socket.socket(
            socket.AF_INET,
            socket.SOCK_STREAM,
        )

        server_socket.setsockopt(
            socket.SOL_SOCKET,
            socket.SO_REUSEADDR,
            1,
        )

        try:
            server_socket.bind(
                (self.CONTROL_HOST, self.control_port)
            )
            server_socket.listen(5)

            self.logger.info(
                "IP control interface listening on %s:%s",
                self.CONTROL_HOST,
                self.control_port,
            )

            while True:
                connection, _ = server_socket.accept()

                # Run each request cooperatively without blocking the listener.
                hub.spawn(self._handle_control_connection, connection)

        except Exception as exc:
            self.logger.exception(
                "Control server error: %s",
                exc,
            )
        finally:
            server_socket.close()

    def _handle_control_connection(self, connection):
        with connection:
            try:
                connection.settimeout(5.0)
                chunks = bytearray()
                while b"\n" not in chunks and len(chunks) <= 1024:
                    chunk = connection.recv(1025 - len(chunks))
                    if not chunk:
                        break
                    chunks.extend(chunk)
                if len(chunks) > 1024:
                    connection.sendall(b"ERROR: Command too long\n")
                    return
                data = chunks.decode(errors="replace").split("\n", 1)[0].strip()

                if not data:
                    return

                parts = data.split()
                command = parts[0].upper()

                if command == "STATUS":
                    with self.state_lock:
                        blocked_ips = tuple(sorted(self.blocked_ips))
                        auto_blocked_ips = tuple(sorted(self.auto_blocked_ips))
                        connected_switches = len(self.datapaths)
                    response = (
                        f"Blocked IPs: "
                        f"{', '.join(blocked_ips) or 'none'}\n"
                        f"Automatically blocked IPs: "
                        f"{', '.join(auto_blocked_ips) or 'none'}\n"
                        f"Connected switches: {connected_switches}\n"
                        f"Statistics interval: {self.stats_interval}s\n"
                        f"Packet-rate threshold: "
                        f"{self.source_rate_threshold} packets/s\n"
                        f"Excluded server IP: {self.SERVER_IP}\n"
                    )

                elif command in ("BLOCK", "UNBLOCK") and len(parts) == 2:
                    try:
                        ip_address = str(
                            ipaddress.IPv4Address(parts[1])
                        )
                    except ipaddress.AddressValueError:
                        response = "ERROR: Invalid IPv4 address\n"
                    else:
                        if command == "BLOCK":
                            if self.block_ip(ip_address):
                                response = f"OK: Blocked {ip_address}\n"
                            else:
                                response = (
                                    f"ERROR: Could not block {ip_address}\n"
                                )
                        else:
                            if self.unblock_ip(ip_address):
                                response = f"OK: Unblocked {ip_address}\n"
                            else:
                                response = (
                                    f"ERROR: Could not unblock {ip_address}\n"
                                )

                else:
                    response = (
                        "ERROR: Use BLOCK <IPv4>, "
                        "UNBLOCK <IPv4>, or STATUS\n"
                    )

                connection.sendall(response.encode())

            except Exception as exc:
                self.logger.error(
                    "Control connection error: %s",
                    exc,
                )
                try:
                    connection.sendall(
                        b"ERROR: Control request failed\n"
                    )
                except OSError:
                    pass
