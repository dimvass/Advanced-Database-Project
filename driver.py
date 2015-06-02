#!/usr/bin/env python3

import auctioneers
import bidder
import synchronisation
import threading
import queue
import sys
import time
import multiprocessing
import signal
import logging

def handler(signum, frame):
    a1.change_state(4)
    a2.change_state(4)
    sys.exit()

if __name__ == "__main__":
    signal.signal(signal.SIGINT, handler)
    if len(sys.argv) < 5:
        sys.exit('Usage: %s configuration_file database_info run_configuration log_file' % sys.argv[0])
    conf = sys.argv[1]
    db_info = sys.argv[2]
    run_conf = sys.argv[3]
    log_file = sys.argv[4]

    if len(sys.argv) == 6 and sys.argv[5] == '-d':
        logging.basicConfig(level=logging.DEBUG, format='(%(threadName)-3s) %(message)s')
    else:
        logging.basicConfig(filename=log_file, filemode='w', level=logging.DEBUG, format='(%(threadName)-3s) %(message)s')

    (db1,db2) = auctioneers.prepare_database_connection(db_info)
    sync = synchronisation.Synchronisation()
    qbid = queue.Queue()
    log = open(log_file,'w')
    f1=open('auct_num_1','w')
    f2=open('auct_num_2','w')

    a1 = auctioneers.Auctioneer(8888,f1,'advdb1',sync,conf,db1)
    a2 = auctioneers.Auctioneer(8889,f2,'advdb2',sync,conf,db2)

    sync.addObservers(a1,a2)
    t1 = threading.Thread(target=a1.serviceloop,name="auctioneer1")
    t2 = threading.Thread(target=a2.serviceloop,name="auctioneer2")
    t1.start()
    t2.start()

    fd = open(run_conf,'r')
    N = int(fd.readline().split()[0])
    bidders = []
    for i in range(0,N):
        line = fd.readline()
        line = line.split()
        ip = line[0]
        port = int(line[1])
        name = line[2]
        budget = float(line[3])
        bidr = bidder.Bidder(ip,port,name,budget,qbid)
        bidders.append(bidr)
        t1 = threading.Thread(target=bidr.cmdloop,name=name)
        t1.start()
        time.sleep(1)
        if qbid.qsize() > 0:
            data = qbid.get()
            if data == 2:
                bidders.remove(bidr)
                
    while True:
        msg = 0
        for i in bidders:
            data = qbid.get()
            if data == 3:
                quit += 3
            msg += data
        if msg == 0:
            interested_list = []
            line = fd.readline()
            line = line.split()
            for i in line:
                interested_list.append(int(i))
            for bidid in interested_list:
                time.sleep(1)
                bidders[bidid].i_am_interested()
        msg = 0
        for i in interested_list:
            data = qbid.get()
            if data == 3:
                quit += 3
            msg += data
        if msg == len(interested_list):
            bid_list = []
            while line != []:
                line = fd.readline()
                line = line.split()
                if line != []:
                    bid_list.append([int(line[0]),int(line[1]),float(line[2])])
            for b in bid_list:
                time.sleep(b[0])
                bidders[b[1]].bid(bidders[b[1]].sock,b[2])