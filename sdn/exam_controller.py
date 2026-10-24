import ipaddress
import socket
import threading
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

        self.mac_to_port = {}
        self.datapaths = {}

        # Manually blocked IP addresses
        self.blocked_ips = set()

        # IP addresses blocked automatically by traffic detection
        self.auto_blocked_ips = set()

        # Flow statistics
        self.stats_interval = 2.0
        self.previous_flow_stats = {}

        # Automatic blocking threshold, in packets per second
        self.source_rate_threshold = 1000.0

        # Start background services
        hub.spawn(self._run_control_server)
        hub.spawn(self._poll_flow_stats)

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
        for ip in self.blocked_ips:
            self._install_block_rule(datapath, ip)

    @set_ev_cls(
        ofp_event.EventOFPStateChange,
        [MAIN_DISPATCHER, DEAD_DISPATCHER],
    )
    def state_change_handler(self, ev):
        datapath = ev.datapath

        if ev.state == MAIN_DISPATCHER:
            if datapath.id not in self.datapaths:
                self.logger.info(
                    "Registering datapath: %s",
                    datapath.id,
                )
            self.datapaths[datapath.id] = datapath

        elif ev.state == DEAD_DISPATCHER:
            if datapath.id in self.datapaths:
                del self.datapaths[datapath.id]

            # Remove previous flow snapshots for this switch
            stale_keys = [
                key
                for key in self.previous_flow_stats
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
                if ip_header.src in self.blocked_ips:
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

        self.blocked_ips.add(ip_address)

        for datapath in self.datapaths.values():
            self._install_block_rule(datapath, ip_address)

        self.logger.warning("BLOCKED IP: %s", ip_address)
        return True

    def unblock_ip(self, ip_address):
        try:
            ip_address = str(ipaddress.IPv4Address(ip_address))
        except ipaddress.AddressValueError:
            self.logger.error("Invalid IPv4 address: %s", ip_address)
            return False

        for datapath in self.datapaths.values():
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

        self.blocked_ips.discard(ip_address)
        self.auto_blocked_ips.discard(ip_address)

        self.logger.info("UNBLOCKED IP: %s", ip_address)
        return True

    # ---------------------------------------------------------
    # Flow statistics polling
    # ---------------------------------------------------------

    def _poll_flow_stats(self):
        while True:
            for datapath in list(self.datapaths.values()):
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

            previous = self.previous_flow_stats.get(key)

            self.previous_flow_stats[key] = (
                now,
                packet_count,
                byte_count,
            )

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
                if (
                    src_ip not in self.auto_blocked_ips
                    and src_ip not in self.blocked_ips
                ):
                    self.logger.warning(
                        "HIGH TRAFFIC DETECTED: "
                        "IP=%s rate=%.2f packets/s threshold=%.2f",
                        src_ip,
                        packet_rate,
                        self.source_rate_threshold,
                    )

                    if self.block_ip(src_ip):
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
                (self.CONTROL_HOST, self.CONTROL_PORT)
            )
            server_socket.listen(5)

            self.logger.info(
                "IP control interface listening on %s:%s",
                self.CONTROL_HOST,
                self.CONTROL_PORT,
            )

            while True:
                connection, _ = server_socket.accept()

                # Handle each request without blocking the listener
                threading.Thread(
                    target=self._handle_control_connection,
                    args=(connection,),
                    daemon=True,
                ).start()

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
                data = connection.recv(1024).decode().strip()

                if not data:
                    return

                parts = data.split()
                command = parts[0].upper()

                if command == "STATUS":
                    response = (
                        f"Blocked IPs: "
                        f"{', '.join(sorted(self.blocked_ips)) or 'none'}\n"
                        f"Automatically blocked IPs: "
                        f"{', '.join(sorted(self.auto_blocked_ips)) or 'none'}\n"
                        f"Connected switches: {len(self.datapaths)}\n"
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
