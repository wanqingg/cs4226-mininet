'''
Please add your name: Nicholas Lum Aik Yong
Please add your matric number: A0108358B
'''

import sys
import os
from sets import Set

from pox.core import core

import pox.openflow.libopenflow_01 as of
import pox.openflow.discovery
import pox.openflow.spanning_tree

from pox.lib.revent import *
from pox.lib.util import dpid_to_str
from pox.lib.addresses import IPAddr, EthAddr

log = core.getLogger()

class Controller(EventMixin):
    def __init__(self):
        self.listenTo(core.openflow)
        core.openflow_discovery.addListeners(self)

        # macmap is a 2d map, each switch has its own mac mapping
        self.macmap = {}
        return

    def _handle_PacketIn (self, event):
        packet = event.parsed
        dpid = event.dpid
        src = packet.src
        dst = packet.dst
        inport = event.port

	# install entries to the route table
        def install_enqueue(event, packet, outport, q_id = None):
            log.debug("# S%i: Installing flow %s.%i -> %s.%i", dpid, src, inport, dst, outport)
            msg = of.ofp_flow_mod()
            msg.match = of.ofp_match.from_packet(packet, inport)
            msg.actions.append(of.ofp_action_output(port = outport))
            msg.data = event.ofp
            event.connection.send(msg)
            log.debug("# S%i: Message sent via port %i\n", dpid, outport)
            return

	# Check the packet and decide how to route the packet
        def forward(message = None):
            log.debug("# S%i: Recv %s via port %i", dpid, packet, inport)

            # Store the incoming port
            self.macmap[dpid][src] = inport
            #print("# S%i: %s" % (dpid, self.macmap))

            # If multicast, flood
            if dst.is_multicast:
                flood("# S%i: Multicast to %s -- flooding" % (dpid, dst))
                return

            # If dst port not found, flood
            if dst not in self.macmap[dpid]:
                flood("# S%i: Port for %s unknown -- flooding" % (dpid, dst))
                return

            # get port and send out
            outport = self.macmap[dpid][dst]
            install_enqueue(event, packet, outport, 0)
            return

        # When it knows nothing about the destination, flood but don't install the rule
        def flood (message = None):
            log.debug(message)
            msg = of.ofp_packet_out()
            msg.actions.append(of.ofp_action_output(port = of.OFPP_FLOOD))
            msg.data = event.ofp
            msg.in_port = inport
            event.connection.send(msg)
            log.debug("# S%i: Message sent via port %i\n", dpid, of.OFPP_FLOOD)
            return

        # Ensure own macmap is initialised
        if dpid not in self.macmap: self.macmap[dpid] = {}

        # Begin
        forward()
        return

    def _handle_ConnectionUp(self, event):
        dpid = event.dpid
        log.debug("# S%i: Switch %i has come up.", dpid, dpid)

        f = open('policy.in')
        firstline = f.readline().split(' ')

        numFw = int(firstline[0])
        numVpn = int(firstline[1])

        # get the firewall rules
        fw = []
        for i in xrange(numFw):
            line = f.readline().strip().split(', ')

            src = line[0]
            dst = line[1]
            port = line[2]
            fw.append((src, dst, port))

        # get the vpns
        vpns = []
        for i in xrange(numVpn):
            line = f.readline().strip().split(', ')
            vpn = []
            for host in line:
                vpn.append(host)
                vpns.append(vpn)

	# Send the firewall policies to the switch
        def sendFirewallPolicy(connection, policy):

            # from first host to second host
            src = policy[0]
            dst = policy[1]
            port = policy[2]

            msg1 = of.ofp_flow_mod()
            msg1.actions.append(of.ofp_action_output(port = of.OFPP_NONE))
            msg1.match.dl_type = 0x800
            msg1.match.nw_proto = 6
            msg1.match.nw_src = IPAddr(src)
            msg1.match.nw_dst = IPAddr(dst)
            msg1.match.tp_dst = int(port)
            log.debug("# S%i, Firewall rule: src=%s, dst=%s:%s", dpid, src, dst, port)
            connection.send(msg1)
            log.debug("# S%i, Rule sent", dpid)

            # from second host to first host
            src = policy[1]
            dst = policy[0]
            port = policy[2]

            msg2 = of.ofp_flow_mod()
            msg2.actions.append(of.ofp_action_output(port = of.OFPP_NONE))
            msg2.match.dl_type = 0x800
            msg2.match.nw_proto = 6
            msg2.match.nw_src = IPAddr(src)
            msg2.match.nw_dst = IPAddr(dst)
            msg2.match.tp_dst = int(port)
            log.debug("# S%i, Firewall rule: src=%s, dst=%s:%s", dpid, src, dst, port)
            connection.send(msg1)
            log.debug("# S%i, Rule sent", dpid)

            return

        for policy in fw:
            sendFirewallPolicy(event.connection, policy)

        return

def launch():
    # Run discovery and spanning tree modules
    pox.openflow.discovery.launch()
    pox.openflow.spanning_tree.launch()

    # Starting the controller module
    core.registerNew(Controller)
